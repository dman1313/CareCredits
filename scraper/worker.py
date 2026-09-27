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


def merge_sources(primary, extra, limit=10):
    seen = {item.get('url') for item in primary if item.get('url')}
    merged = list(primary)
    for item in extra:
        url = item.get('url')
        if not url or url in seen:
            continue
        merged.append(item)
        seen.add(url)
        if len(merged) >= limit:
            break
    return merged


def public_sources(sources):
    items = []
    for source in sources[:10]:
        items.append({
            'url': str(source.get('url') or '')[:2000],
            'title': str(source.get('title') or 'Untitled source')[:300],
            'snippet': str(source.get('snippet') or '')[:2000],
            'extraction_status': str(source.get('extraction_status') or 'failed')[:40],
            'verification_status': str(source.get('verification_status') or 'unverified')[:40],
        })
    return items


def catalogue_pipeline(client, job_id, candidates):
    """Lookup → Jev decide → save new/exists/uncertain via backend connect APIs."""
    warnings = []
    saved = 0
    for training in candidates:
        lookup = client.post('/internal/v1/catalogue/lookup', json={'candidate': training})
        if lookup.status_code >= 400:
            warnings.append('Catalogue lookup failed for one candidate.')
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
                warnings.append(decide.json().get('detail') if decide.headers.get('content-type', '').startswith('application/json') else 'Catalogue decide failed.')
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
            warnings.append(str(save.json().get('detail') if save.headers.get('content-type', '').startswith('application/json') else 'Catalogue save failed.')[:200])
            continue
        saved += 1
    return saved, warnings


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
    warnings, candidates, sources = [], [], []
    try:
        limit = max(1, min(int(job.get('max_results') or 5), 5))
        result = discover(job['query'], limit)
        warnings.extend(result['warnings'])
        sources = result['sources']
        if firehose_configured():
            try:
                extra = firehose_discover(job['query'], limit)
                warnings.extend(extra.get('warnings') or [])
                sources = merge_sources(sources, extra.get('sources') or [])
            except FirehoseError as exc:
                warnings.append(str(exc))
        model_ready = True
        try:
            configuration()
        except ExtractionError as exc:
            model_ready = False
            warnings.append(str(exc) + ' Using evidence-gated heuristic extraction; Tavily sources are still saved.')
        held = []
        for source in sources:
            heartbeat()
            raw = (source.get('raw_content') or '').strip()
            snippet = (source.get('snippet') or '').strip()
            if not raw and not snippet:
                continue
            snippet_only = (not raw) or str(source.get('extraction_status') or '') == 'failed'
            try:
                if model_ready and not snippet_only:
                    page_candidates = extract_training(source)
                else:
                    page_candidates = heuristic_extract(source)
            except ExtractionError as exc:
                warnings.append(str(exc))
                continue
            if snippet_only:
                held.extend(page_candidates)
                if page_candidates:
                    warnings.append('Snippet-only source kept for review; not auto-published.')
            else:
                candidates.extend(page_candidates)
        saved = 0
        if client is not None and candidates:
            try:
                connect = client.get('/internal/v1/catalogue/connect')
                if connect.status_code == 200:
                    saved, save_warnings = catalogue_pipeline(client, job['id'], candidates)
                    warnings.extend(save_warnings)
                else:
                    warnings.append('Catalogue connect unavailable; candidates were not saved through the API.')
            except httpx.HTTPError:
                warnings.append('Catalogue connect failed; candidates were not saved through the API.')
        # Snippet-only rows stay on the job for operator review. Connect/save owns full-extract rows.
        complete_candidates = list(held)
        if not saved:
            complete_candidates.extend(candidates)
        if candidates and not saved:
            warnings.append('Falling back to job-complete candidate insert without Jev decide/save.')
        return {
            'lease_token': job['lease_token'],
            'candidates': complete_candidates,
            'sources': public_sources(sources),
            'warnings': warnings,
            'status': 'partial' if warnings else 'succeeded',
            'usage': {'tavily_credits': None, 'model_tokens': None, 'catalogue_saved': saved},
        }
    except (ProviderError, ExtractionError) as exc:
        return {
            'lease_token': job['lease_token'], 'candidates': [], 'sources': public_sources(sources),
            'warnings': [str(exc)], 'status': 'failed', 'usage': {},
        }


def main():
    base = os.getenv('BACKEND_INTERNAL_URL', 'http://127.0.0.1:8000').rstrip('/')
    token = os.getenv('SCRAPER_SERVICE_TOKEN', '')
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
