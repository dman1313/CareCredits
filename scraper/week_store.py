"""Week-key-first state, request deduplication, and batch partitioning for the CareCredits scraper.

Reverse-engineered from Crawlee's three storage abstractions (RequestQueue deterministic
``unique_key`` + KeyValueStore partition checkpoints + append-only Dataset records) and
Scrapling's adaptive fingerprint matching, but every structure is keyed **at the week_key first**
(``store[week_key]``) so a weekly run never re-extracts a URL already handled that week and never
re-spends Tavily/model credits after an interruption.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from shared.contracts import (
    canonical_web_url,
    compute_source_key,
    week_key_for_date,
    week_window,
)


DEFAULT_STATE_PATH = '/tmp/carecredits-week-store.json'

# Optional training fields that a second page can fill in a null-value merge (Firecrawl
# merge-null-val-objs.ts). Identity fields (title/provider/start_date) are never overwritten.
MERGE_FILL_FIELDS = (
    'end_date', 'timezone', 'venue', 'city', 'state', 'fee', 'currency',
    'points', 'credit_label', 'difficulty', 'prerequisites', 'registration_url',
)
# Fields whose before/after values are recorded in a deriveDiff field-level comparison.
TRACKED_DIFF_FIELDS = (
    'title', 'provider', 'start_date', 'end_date', 'mode', 'city', 'state', 'venue',
    'fee', 'currency', 'points', 'credit_label', 'difficulty', 'prerequisites', 'registration_url',
)
_MAX_SOURCE_TEXT = 50000


def query_unique_key(week_key: str, query: str) -> str:
    """Deterministic per-week topic key so the same query is not re-run twice in a week."""
    norm = ' '.join((query or '').strip().lower().split())
    digest = hashlib.sha256(norm.encode('utf-8')).hexdigest()[:24]
    return f'{week_key}:query:{digest}'


def url_unique_key(week_key: str, url: str) -> str:
    """Deterministic per-week URL fingerprint (``{week_key}:url:{sha256}``) after canonicalization."""
    canon = canonical_web_url(url) or (url or '').split('#')[0].strip()
    digest = hashlib.sha256(canon.encode('utf-8')).hexdigest()[:24]
    return f'{week_key}:url:{digest}'


def is_near_duplicate(candidate: dict[str, Any], existing_events: list[dict[str, Any]], threshold: float = 0.86) -> dict[str, Any] | None:
    """Scrapling-inspired two-stage dedupe against known catalogue events.

    Stage 1 is an exact ``source_key`` short-circuit; stage 2 scores adaptive similarity over
    ``title`` + ``provider`` (gated by matching ``start_date`` when both are known) so a
    near-duplicate already in the catalogue is flagged before a batch is pushed.
    """
    c_key = candidate.get('source_key')
    c_title = (candidate.get('title') or '').strip().lower()
    c_provider = (candidate.get('provider') or '').strip().lower()
    c_date = str(candidate.get('start_date') or '')
    for row in existing_events or []:
        if not isinstance(row, dict):
            continue
        if c_key and row.get('source_key') == c_key:
            return {'reason': 'exact_source_key', 'matched': row}
        r_date = str(row.get('start_date') or '')
        if c_date and r_date and c_date != r_date:
            continue
        r_title = (row.get('title') or '').strip().lower()
        r_provider = (row.get('provider') or '').strip().lower()
        if not c_title or not r_title:
            continue
        title_sim = SequenceMatcher(None, c_title, r_title).ratio()
        prov_sim = SequenceMatcher(None, c_provider, r_provider).ratio() if (c_provider and r_provider) else 1.0
        if title_sim >= threshold and prov_sim >= 0.75:
            return {'reason': 'near_duplicate_fingerprint', 'matched': row, 'similarity': round(title_sim, 3)}
    return None


def content_fingerprint(text: str) -> str:
    """Whitespace-insensitive SHA-256 of page content (Firecrawl `deriveDiff`).

    Collapsing all whitespace means cosmetic reflow (``\\r\\n`` vs ``\\n``, re-indentation) does not
    register as a content change, so ``change_status`` only flips on real edits.
    """
    normalized = re.sub(r'\s+', '', text or '')
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def are_candidates_mergeable(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    """Firecrawl ``areMergeable``: same identity and no conflicting non-null identity fields."""
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return False
    if existing.get('source_key') and existing.get('source_key') == incoming.get('source_key'):
        return True
    if not is_near_duplicate(incoming, [existing]):
        return False
    for field in ('start_date', 'mode', 'city'):
        a, b = existing.get(field), incoming.get(field)
        if a is not None and b is not None and str(a) != str(b):
            return False
    return True


def _merge_supporting_sources(existing: dict[str, Any], incoming: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for url in (existing.get('supporting_sources') or []):
        if url and url not in ordered:
            ordered.append(url)
    if existing.get('source_url') and existing['source_url'] not in ordered:
        ordered.insert(0, existing['source_url'])
    for url in (incoming.get('supporting_sources') or []):
        if url and url not in ordered:
            ordered.append(url)
    if incoming.get('source_url') and incoming['source_url'] not in ordered:
        ordered.append(incoming['source_url'])
    return ordered


def merge_candidate_records(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Firecrawl null-filling merge + SourceTracker provenance.

    Fills ``None`` optional fields (and empty ``description``) in ``existing`` from ``incoming``,
    copies the matching verbatim ``evidence`` excerpt, extends ``source_text`` so the new excerpt
    still validates, and unions ``supporting_sources`` across both contributing pages. Identity and
    already-known fields in ``existing`` are never overwritten.
    """
    merged = dict(existing)
    evidence = dict(existing.get('evidence') or {})
    incoming_evidence = incoming.get('evidence') or {}
    new_excerpts: list[str] = []

    if not (merged.get('description') or '').strip() and (incoming.get('description') or '').strip():
        merged['description'] = incoming['description']

    for field in MERGE_FILL_FIELDS:
        if merged.get(field) is None and incoming.get(field) is not None:
            merged[field] = incoming[field]
            excerpt = incoming_evidence.get(field)
            if excerpt:
                evidence[field] = excerpt
                new_excerpts.append(excerpt)
    merged['evidence'] = evidence

    source_text = existing.get('source_text') or ''
    incoming_text = incoming.get('source_text') or ''
    for excerpt in new_excerpts:
        if excerpt not in source_text and incoming_text and incoming_text not in source_text:
            source_text = (source_text + '\n' + incoming_text)[:_MAX_SOURCE_TEXT]
    merged['source_text'] = source_text[:_MAX_SOURCE_TEXT]

    merged['supporting_sources'] = _merge_supporting_sources(existing, incoming)
    return merged


def compare_candidate_fields(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Firecrawl ``compareExtractedData``: ``{field: {previous, current}}`` for changed fields."""
    diffs: dict[str, Any] = {}
    for field in TRACKED_DIFF_FIELDS:
        before, after = (previous or {}).get(field), (current or {}).get(field)
        if before != after:
            diffs[field] = {'previous': before, 'current': after}
    return diffs


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WeekPartitionStore:
    """A week-key-first request queue, source cache, and candidate dataset.

    The outer key is ALWAYS the scrape ``week_key`` (``store.data[week_key]``). Every public
    operation takes ``week_key`` as its first argument. Inside each scrape week, extracted
    candidates are bucketed again by their own event ``week_key`` first
    (``events_by_week[event_week_key][source_key]``), while remaining flat-indexable for batch push.
    """

    def __init__(self, path: str | os.PathLike | None = DEFAULT_STATE_PATH, data: dict | None = None, autoload: bool = True):
        env_path = (os.getenv('SCRAPER_STATE_PATH') or '').strip()
        if path is DEFAULT_STATE_PATH and env_path:
            path = env_path
        self.path = Path(path) if path else None
        self.data: dict[str, Any] = data if data is not None else {}
        if data is None and autoload:
            self.load()

    # -- persistence -------------------------------------------------------
    def load(self) -> 'WeekPartitionStore':
        if not self.path or not self.path.exists():
            return self
        try:
            loaded = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict):
                self.data = loaded
        except (OSError, ValueError):
            # A corrupt or unreadable checkpoint must never crash a weekly run; start clean.
            self.data = {}
        return self

    def persist(self) -> 'WeekPartitionStore':
        if not self.path:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace so an interrupted write cannot leave a half-serialized checkpoint.
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix='.weekstore-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(self.data, handle, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return self

    # -- week bucket -------------------------------------------------------
    def week(self, week_key: str) -> dict[str, Any]:
        """Return (creating if needed) the week bucket, always keyed at ``week_key`` first."""
        window_start, window_end = week_window(week_key)
        bucket = self.data.setdefault(week_key, {})
        bucket.setdefault('week_key', week_key)
        bucket.setdefault('window_start', window_start)
        bucket.setdefault('window_end', window_end)
        bucket.setdefault('topics', {})
        bucket.setdefault('sources', {})
        bucket.setdefault('requests_seen', {})
        bucket.setdefault('events_by_week', {})
        bucket.setdefault('negative_cache', {})
        bucket.setdefault('url_traces', {})
        bucket.setdefault('usage', {
            'tavily_credits': 0.0,
            'model_tokens': 0,
            'batches_pushed': 0,
            'accepted_count': 0,
            'rejected_count': 0,
        })
        bucket['updated_at'] = _now_iso()
        return bucket

    def weeks(self) -> list[str]:
        return sorted(key for key in self.data if isinstance(self.data.get(key), dict))

    # -- request queue (topics + urls) ------------------------------------
    def topic_seen(self, week_key: str, query: str) -> bool:
        bucket = self.week(week_key)
        return query_unique_key(week_key, query) in bucket['requests_seen']

    def mark_topic_seen(self, week_key: str, query: str, status: str = 'pending', source_urls: list[str] | None = None, topic_id: str | None = None) -> None:
        bucket = self.week(week_key)
        unique = query_unique_key(week_key, query)
        bucket['requests_seen'][unique] = 'query'
        bucket['topics'][topic_id or unique] = {
            'query': query,
            'status': status,
            'retrieved_at': _now_iso(),
            'source_urls': list(source_urls or []),
        }

    def url_seen(self, week_key: str, url: str) -> bool:
        bucket = self.week(week_key)
        return url_unique_key(week_key, url) in bucket['requests_seen']

    def mark_url_seen(self, week_key: str, url: str) -> None:
        bucket = self.week(week_key)
        bucket['requests_seen'][url_unique_key(week_key, url)] = 'url'

    # -- source cache (KeyValueStore) -------------------------------------
    def get_cached_source(self, week_key: str, url: str) -> dict | None:
        bucket = self.week(week_key)
        canon = canonical_web_url(url) or (url or '').split('#')[0].strip()
        return bucket['sources'].get(canon)

    def put_source(self, week_key: str, source: dict) -> str | None:
        bucket = self.week(week_key)
        url = source.get('url') if isinstance(source, dict) else None
        canon = canonical_web_url(url) or (url or '').split('#')[0].strip() if url else None
        if not canon:
            return None
        # Firecrawl deriveDiff change tracking: compare the whitespace-insensitive content hash with
        # the previously cached version of this URL in the same week.
        text = source.get('raw_content') or source.get('snippet') or ''
        fingerprint = content_fingerprint(text)
        previous = bucket['sources'].get(canon)
        if previous is None:
            change_status = 'new'
        elif previous.get('content_fingerprint') == fingerprint:
            change_status = 'same'
        else:
            change_status = 'changed'
        record = dict(source)
        record['url'] = canon
        record['content_fingerprint'] = fingerprint
        record['change_status'] = change_status
        record.setdefault('retrieved_at', _now_iso())
        bucket['sources'][canon] = record
        self.mark_url_seen(week_key, canon)
        return change_status

    # -- candidate dataset (events, bucketed by event week first) ----------
    def put_candidate(self, week_key: str, candidate: dict) -> str | None:
        """Store a candidate at ``events_by_week[event_week_key][source_key]`` first.

        ``week_key`` is the scrape-window bucket; the candidate's own ``week_key`` (its event
        week) is the inner partition key, so every event is indexed by its week key first.
        """
        if not isinstance(candidate, dict):
            return None
        source_key = candidate.get('source_key') or compute_source_key(
            candidate.get('source_url') or '', candidate.get('title') or '', candidate.get('start_date')
        )
        event_week = candidate.get('week_key') or week_key_for_date(candidate.get('start_date'))
        record = dict(candidate)
        record.setdefault('source_key', source_key)
        record.setdefault('week_key', event_week)
        record.setdefault('scrape_week_key', week_key)
        if not record.get('supporting_sources') and record.get('source_url'):
            record['supporting_sources'] = [record['source_url']]
        bucket = self.week(week_key)
        events = bucket['events_by_week'].setdefault(event_week, {})
        existing = events.get(source_key)
        if existing is None:
            # Firecrawl null-filling merge against a near-duplicate already stored this event week.
            for stored_key, stored in events.items():
                if are_candidates_mergeable(stored, record):
                    existing = stored
                    source_key = stored_key
                    break
        if existing is not None:
            merged = merge_candidate_records(existing, record)
            field_diffs = compare_candidate_fields(existing, merged)
            merged['source_key'] = existing.get('source_key') or source_key
            merged['_change_status'] = 'changed' if field_diffs else 'same'
            merged['_field_diffs'] = field_diffs
            events[source_key] = merged
        else:
            record['_change_status'] = 'new'
            record['_field_diffs'] = {}
            events[source_key] = record
        # Firecrawl index-cache: a positive write invalidates any negative marker for this URL.
        self._invalidate_negative(week_key, candidate.get('source_url'))
        return source_key

    def events_for_week(self, week_key: str) -> list[dict]:
        """Flat, deterministically ordered list of every candidate under this scrape week."""
        bucket = self.week(week_key)
        rows: list[dict] = []
        for event_week in sorted(bucket['events_by_week']):
            for source_key in sorted(bucket['events_by_week'][event_week]):
                rows.append(bucket['events_by_week'][event_week][source_key])
        return rows

    def candidates_by_week(self, week_key: str) -> dict[str, list[dict]]:
        """Event candidates grouped by their own event ``week_key`` first."""
        bucket = self.week(week_key)
        grouped: dict[str, list[dict]] = {}
        for event_week in sorted(bucket['events_by_week']):
            grouped[event_week] = [
                bucket['events_by_week'][event_week][key]
                for key in sorted(bucket['events_by_week'][event_week])
            ]
        return grouped

    def export_batch_payload(self, week_key: str, operator_id: str = 'scraper-worker') -> dict:
        """Build the ``/internal/v1/ingestion/batches/push`` body, week-key ordered.

        Every event keeps ``week_key`` and ``source_key`` so the backend dedupes on the same
        deterministic identity the scraper computed.
        """
        events = []
        for row in self.events_for_week(week_key):
            # Strip internal change-tracking keys (``_change_status``/``_field_diffs``) so the push
            # body stays a clean Training payload; supporting_sources/week_key/source_key are kept.
            event = {key: value for key, value in row.items() if not str(key).startswith('_')}
            event.setdefault('scrape_week_key', week_key)
            if event.get('source_key'):
                events.append(event)
        return {'operator_id': operator_id, 'events': events}

    def record_usage(self, week_key: str, *, tavily_credits: float | None = None, model_tokens: int | None = None, batches_pushed: int = 0, accepted: int = 0, rejected: int = 0) -> None:
        usage = self.week(week_key)['usage']
        if tavily_credits is not None:
            usage['tavily_credits'] = round((usage.get('tavily_credits') or 0.0) + tavily_credits, 6)
        if model_tokens is not None:
            usage['model_tokens'] = (usage.get('model_tokens') or 0) + model_tokens
        usage['batches_pushed'] = (usage.get('batches_pushed') or 0) + batches_pushed
        usage['accepted_count'] = (usage.get('accepted_count') or 0) + accepted
        usage['rejected_count'] = (usage.get('rejected_count') or 0) + rejected

    # -- negative cache (Firecrawl idxcneg markers) -----------------------
    @staticmethod
    def _neg_key(key: str) -> str:
        canon = canonical_web_url(key) or ' '.join((key or '').strip().lower().split())
        return 'idxcneg:' + hashlib.sha256(canon.encode('utf-8')).hexdigest()[:24]

    @staticmethod
    def is_negative_still_valid(entry: dict, max_age_seconds: float, now: float) -> bool:
        """A negative marker is valid while it is within its TTL window from when it was recorded."""
        recorded = entry.get('recorded_at')
        if recorded is None:
            recorded = entry.get('empty_from') or 0
        return (now - recorded) <= max_age_seconds

    def set_negative(self, week_key: str, url_or_query: str, reason: str = 'no_events', empty_from: float | None = None, now: float | None = None) -> None:
        bucket = self.week(week_key)
        now = now if now is not None else time.time()
        bucket['negative_cache'][self._neg_key(url_or_query)] = {
            'key': url_or_query,
            'reason': reason,
            'empty_from': empty_from if empty_from is not None else now,
            'recorded_at': now,
        }

    def get_negative(self, week_key: str, url_or_query: str, max_age_seconds: float = 86400, now: float | None = None) -> dict | None:
        bucket = self.week(week_key)
        neg = bucket.get('negative_cache', {})
        marker = self._neg_key(url_or_query)
        entry = neg.get(marker)
        if not entry:
            return None
        now = now if now is not None else time.time()
        if self.is_negative_still_valid(entry, max_age_seconds, now):
            return entry
        neg.pop(marker, None)
        return None

    def _invalidate_negative(self, week_key: str, url_or_query: str | None) -> None:
        if not url_or_query:
            return
        bucket = self.week(week_key)
        bucket.get('negative_cache', {}).pop(self._neg_key(url_or_query), None)

    # -- URL traces (Firecrawl URLTrace lifecycle) ------------------------
    def record_url_trace(self, week_key: str, url: str, *, status: str, relevance_score: float | None = None, reason: str | None = None, used_in_completion: bool = False) -> None:
        bucket = self.week(week_key)
        canon = canonical_web_url(url) or (url or '').split('#')[0].strip()
        if not canon:
            return
        trace = bucket['url_traces'].get(canon, {'url': canon, 'history': []})
        trace['url'] = canon
        trace['status'] = status
        trace['updated_at'] = _now_iso()
        if relevance_score is not None:
            trace['relevance_score'] = relevance_score
        if reason is not None:
            trace['reason'] = reason
        trace['used_in_completion'] = used_in_completion or trace.get('used_in_completion', False)
        trace.setdefault('history', []).append({'status': status, 'at': _now_iso()})
        bucket['url_traces'][canon] = trace
