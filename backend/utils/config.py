import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # Adjust path for new location
TOPICS_PATH = Path(os.getenv('SCRAPE_TOPICS_FILE') or ROOT / 'config' / 'scrape_topics.json')


def _topic_max_results(raw) -> int | None:
    """Clamp max_results to 1–5, or None when the row is invalid."""
    if isinstance(raw, bool):
        return None
    if raw in (None, ''):
        return 5
    if isinstance(raw, float) and not math.isfinite(raw):
        return None
    try:
        max_results = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return max(1, min(max_results, 5))


def load_topics() -> list[dict]:
    """Load curated topics for admin display. No job enqueue logic."""
    if not TOPICS_PATH.exists():
        return [{'query': 'GP CPD courses Kuala Lumpur', 'max_results': 5}]
    try:
        data = json.loads(TOPICS_PATH.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('scrape_topics.json is not valid JSON') from exc
    if not isinstance(data, list):
        raise ValueError('scrape_topics.json must be a list of {query,max_results}')
    
    topics = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_query = item.get('query')
        if not isinstance(raw_query, str):
            continue
        query = raw_query.strip()
        if not (3 <= len(query) <= 300):
            continue
        max_results = _topic_max_results(item.get('max_results'))
        if max_results is None:
            continue
        topics.append({'query': query, 'max_results': max_results})
    return topics


def daily_ceiling() -> int:
    """Return configured daily scrape limit for admin display."""
    try:
        return max(1, int(os.getenv('DAILY_SCRAPE_JOB_CEILING', '10')))
    except ValueError:
        return 10