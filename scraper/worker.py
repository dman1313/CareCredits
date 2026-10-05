"""Run with python -m scraper.worker; communicates with backend over scoped HTTP."""
import os
from pathlib import Path
import threading
import time
import httpx
from scraper.tavily import discover, ProviderError
from scraper.firehose import discover as firehose_discover, configured as firehose_configured, FirehoseError
from scraper.extraction import configuration, extract_training, heuristic_extract, ExtractionError
from scraper.health import start as start_health
from shared.contracts import public_web_url


def job_result_limit(job):
    """Bound Search size 1–5. Reject JSON booleans so True/False cannot invent spend size 1/0→1."""
    raw = job.get('max_results', 5)
    if isinstance(raw, bool):
        raise ExtractionError('Job max_results must be an integer from 1 to 5.')
    try:
        return max(1, min(int(raw if raw is not None and raw != '' else 5), 5))
    except (TypeError, ValueError):
        raise ExtractionError('Job max_results must be an integer from 1 to 5.')


def merge_sources(primary, extra, limit=5):
    # Skip non-dict rows (parity with public_sources) so junk Firehose/Tavily entries cannot crash fill.
    merged = [item for item in (primary or []) if isinstance(item, dict)][:limit]
    seen = {item.get('url') for item in merged if item.get('url')}
    for item in extra or []:
        if len(merged) >= limit:
            break
        if not isinstance(item, dict):
            continue
        url = item.get('url')
        if not url or url in seen:
            continue
        merged.append(item)
        seen.add(url)
    return merged


def stamp_retrieved_at(sources, retrieved_at):
    """Copy provider-level retrieval ISO onto sources that omit it."""
    if not retrieved_at:
        return sources
    stamp = str(retrieved_at)[:80]
    for source in sources or []:
        if isinstance(source, dict) and not source.get('retrieved_at'):
            source['retrieved_at'] = stamp
    return sources


def public_sources(sources):
    items = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        if len(items) >= 5:
            break
        safe = public_web_url(source.get('url'))
        retrieved = source.get('retrieved_at')
        items.append({
            'url': safe[:2000] if safe else None,
            'title': str(source.get('title') or 'Untitled source')[:300],
            'snippet': str(source.get('snippet') or '')[:2000],
            'extraction_status': str(source.get('extraction_status') or 'failed')[:40],
            'verification_status': str(source.get('verification_status') or 'unverified')[:40],
            'retrieved_at': str(retrieved)[:80] if retrieved else None,
        })
    return items


def api_message(response, fallback):
    """Read SDD `{error.message}` envelopes; keep FastAPI `detail` as a fallback."""
    headers = getattr(response, 'headers', None) or {}
    ctype = headers.get('content-type') if hasattr(headers, 'get') else ''
    if not str(ctype).startswith('application/json'):
        return fallback
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return fallback
    if not isinstance(payload, dict):
        return fallback
    error = payload.get('error')
    if isinstance(error, dict) and error.get('message'):
        return str(error['message'])[:200]
    detail = payload.get('detail')
    if isinstance(detail, str) and detail.strip():
        return detail.strip()[:200]
    return fallback


def _with_judgment(training, judgment):
    """Attach Jev judgment for job-complete fallback without mutating the original payload."""
    if isinstance(training, dict):
        payload = dict(training)
    else:
        payload = dict(training)
    if judgment:
        payload['_judgment'] = judgment
    return payload


def catalogue_pipeline(client, job_id, candidates):
    """Lookup → Jev decide → save new/exists/uncertain via backend connect APIs.

    Returns (saved_count, warnings, unsaved_payloads). Unsaved rows keep `_judgment`
    so job-complete can still hold uncertain / exists refresh evidence.
    """
    warnings = []
    saved = 0
    unsaved = []
    for training in candidates:
        lookup = client.post('/internal/v1/catalogue/lookup', json={'candidate': training})
        if lookup.status_code >= 400:
            warnings.append(api_message(lookup, 'Catalogue lookup failed for one candidate.'))
            unsaved.append(_with_judgment(training, None))
            continue
        data = lookup.json()
        if data.get('exact'):
            judgment = {
                'decision': 'exists',
                'confidence': 1.0,
                'probabilities': {'exists': 1.0, 'new': 0.0, 'uncertain': 0.0},
                'matched_session_id': data['exact']['id'],
            }
        else:
            decide = client.post(
                '/internal/v1/catalogue/decide',
                json={'candidate': training, 'matches': data.get('matches') or []},
            )
            if decide.status_code >= 400:
                warnings.append(api_message(decide, 'Catalogue decide failed.'))
                # Fall back to uncertain hold via save path only if we can craft judgment
                judgment = {
                    'decision': 'uncertain',
                    'confidence': 0.0,
                    'probabilities': {'exists': 0.0, 'new': 0.0, 'uncertain': 1.0},
                    'warning': 'Decide endpoint unavailable; held for review.',
                }
            else:
                judgment = decide.json()
        save = client.post(
            '/internal/v1/catalogue/save',
            json={'candidate': training, 'judgment': judgment, 'job_id': job_id},
        )
        if save.status_code >= 400:
            warnings.append(api_message(save, 'Catalogue save failed.'))
            unsaved.append(_with_judgment(training, judgment))
            continue
        saved += 1
    return saved, warnings, unsaved


def keep_lease(heartbeat, interval=30):
    stop = threading.Event()

    def loop():
        while not stop.wait(interval):
            try:
                heartbeat()
            except Exception:
                break

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return stop


def run_job(job, heartbeat, client=None):
    # Material warnings drive partial/failed. Soft Firehose fill warnings stay on the job but do not
    # alone mark a successful Tavily extract as partial (matches empty-search soft-warn honesty).
    warnings, soft_warnings, candidates, sources = [], [], [], []
    tavily_credits = None
    model_usage = {}
    try:
        configuration()
    except ExtractionError as exc:
        return {
            'lease_token': job['lease_token'],
            'candidates': [],
            'sources': [],
            'warnings': [str(exc) + ' Tavily Search was not called until the open-weight model is ready.'],
            'status': 'failed',
            'usage': {'tavily_credits': None, 'model_tokens': None, 'catalogue_saved': 0},
        }
    try:
        try:
            limit = job_result_limit(job)
        except ExtractionError as exc:
            return {
                'lease_token': job['lease_token'],
                'candidates': [],
                'sources': [],
                'warnings': [str(exc) + ' Tavily Search was not called.'],
                'status': 'failed',
                'usage': {'tavily_credits': None, 'model_tokens': None, 'catalogue_saved': 0},
            }
        result = discover(job['query'], limit)
        warnings.extend(result['warnings'])
        sources = stamp_retrieved_at(result['sources'], result.get('retrieved_at'))
        tavily_credits = (result.get('usage') or {}).get('tavily_credits')
        if firehose_configured() and len(sources) < limit:
            try:
                extra = firehose_discover(job['query'], limit - len(sources))
                soft_warnings.extend(extra.get('warnings') or [])
                filled = stamp_retrieved_at(extra.get('sources') or [], extra.get('retrieved_at'))
                sources = merge_sources(sources, filled, limit)
            except FirehoseError as exc:
                soft_warnings.append(str(exc))
        if not sources:
            # Empty Search (+ optional Firehose fill) is succeeded even when Firehose only warned.
            # Soft provider warnings without sources are not a partial extract.
            return {
                'lease_token': job['lease_token'],
                'candidates': [],
                'sources': public_sources(sources),
                'warnings': soft_warnings + warnings,
                'status': 'succeeded',
                'usage': {'tavily_credits': tavily_credits, 'model_tokens': None, 'catalogue_saved': 0},
            }
        held = []
        try:
            for source in sources:
                if not isinstance(source, dict):
                    continue
                heartbeat()
                raw = (source.get('raw_content') or '').strip()
                snippet = (source.get('snippet') or '').strip()
                if not raw and not snippet:
                    title = str(source.get('title') or 'Untitled source')[:80]
                    warnings.append('Source had no extractable text (' + title + ').')
                    continue
                snippet_only = (not raw) or str(source.get('extraction_status') or '') == 'failed'
                hold_for_review = snippet_only
                try:
                    if not snippet_only:
                        try:
                            page_candidates = extract_training(source, usage=model_usage)
                        except ExtractionError as exc:
                            warnings.append(str(exc) + ' Heuristic candidate held for review.')
                            page_candidates = heuristic_extract(source)
                            hold_for_review = True
                    else:
                        page_candidates = heuristic_extract(source)
                except ExtractionError as exc:
                    warnings.append(str(exc))
                    continue
                if hold_for_review:
                    held.extend(page_candidates)
                    if page_candidates and snippet_only:
                        warnings.append('Snippet-only source kept for review; not auto-published.')
                else:
                    candidates.extend(page_candidates)
        except ExtractionError as exc:
            warnings.append(str(exc))
        saved = 0
        unsaved = []
        if client is not None and candidates:
            try:
                connect = client.get('/internal/v1/catalogue/connect')
                if connect.status_code == 200:
                    saved, save_warnings, unsaved = catalogue_pipeline(client, job['id'], candidates)
                    warnings.extend(save_warnings)
                else:
                    warnings.append(
                        api_message(connect, 'Catalogue connect unavailable; candidates were not saved through the API.')
                    )
                    unsaved = list(candidates)
            except httpx.HTTPError:
                warnings.append('Catalogue connect failed; candidates were not saved through the API.')
                unsaved = list(candidates)
        elif candidates:
            # No connect client: keep extract rows on the job for operator review.
            unsaved = list(candidates)
        # Snippet-only rows stay on the job for operator review. Unsaved full-extract rows keep
        # their Jev `_judgment` so complete can hold uncertain / exists refresh evidence.
        complete_candidates = list(held)
        if unsaved:
            complete_candidates.extend(unsaved)
            if saved:
                warnings.append(
                    str(len(unsaved))
                    + ' of '
                    + str(len(candidates))
                    + ' catalogue saves failed; unsaved kept on job.'
                )
            elif candidates:
                warnings.append('Falling back to job-complete candidate insert without Jev decide/save.')
        return {
            'lease_token': job['lease_token'],
            'candidates': complete_candidates,
            'sources': public_sources(sources),
            'warnings': soft_warnings + warnings,
            'status': 'partial' if warnings else 'succeeded',
            'usage': {
                'tavily_credits': tavily_credits,
                'model_tokens': model_usage.get('model_tokens'),
                'catalogue_saved': saved,
            },
        }
    except (ProviderError, ExtractionError) as exc:
        return {
            'lease_token': job['lease_token'], 'candidates': [], 'sources': public_sources(sources),
            'warnings': soft_warnings + [str(exc)], 'status': 'failed',
            # Keep any reported Tavily/model usage from the attempt; never invent spend.
            'usage': {
                'tavily_credits': tavily_credits,
                'model_tokens': model_usage.get('model_tokens'),
                'catalogue_saved': 0,
            },
        }


def main():
    base = os.getenv('BACKEND_INTERNAL_URL', 'http://127.0.0.1:8000').rstrip('/')
    # Strip so compose/.env padding matches backend security.worker() expected token.
    token = (os.getenv('SCRAPER_SERVICE_TOKEN') or '').strip()
    if not token:
        raise SystemExit('Set SCRAPER_SERVICE_TOKEN before starting the scraper.')
    start_health()
    with httpx.Client(base_url=base, headers={'Authorization': 'Bearer ' + token}, timeout=20) as client:
        while True:
            Path('/tmp/carecredits-worker').touch()
            try:
                response = client.post('/internal/v1/jobs/claim')
                response.raise_for_status()
                if response.status_code == 204:
                    reason = (response.headers.get('x-care-claim-reason') or 'empty').strip().lower()
                    if reason == 'not_ready':
                        print('Claim idle (not_ready): paid scrape not ready; waiting.', flush=True)
                    elif reason == 'lost_lease':
                        print('Claim idle (lost_lease): queued job lost the lease race; waiting.', flush=True)
                    else:
                        print('Claim idle (empty): no queued jobs; waiting.', flush=True)
                    time.sleep(3)
                    continue
                job = response.json()
                started = time.monotonic()

                def heartbeat():
                    if time.monotonic() - started > 270:
                        raise ExtractionError('Job deadline reached; retry explicitly if needed.')
                    client.post(
                        '/internal/v1/jobs/' + job['id'] + '/heartbeat',
                        json={'lease_token': job['lease_token']},
                    ).raise_for_status()

                lease = keep_lease(heartbeat)
                try:
                    payload = run_job(job, heartbeat, client)
                finally:
                    lease.set()
                client.post('/internal/v1/jobs/' + job['id'] + '/complete', json=payload).raise_for_status()
                print('Ingestion job ' + job['id'] + ': ' + payload['status'], flush=True)
            except (httpx.HTTPError, ValueError):
                print('Backend request unavailable; job lease will determine recovery.', flush=True)
                time.sleep(5)


if __name__ == '__main__':
    main()
