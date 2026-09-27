"""Daily scrape enqueue for the owned-catalogue agent (OPS-02 / DEC-09)."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from portal_models import Account, Job
from security import digest


ROOT = Path(__file__).resolve().parents[1]
TOPICS_PATH = Path(os.getenv('SCRAPE_TOPICS_FILE') or ROOT / 'config' / 'scrape_topics.json')
TZ = ZoneInfo('Asia/Kuala_Lumpur')


def local_today() -> str:
    return datetime.now(TZ).date().isoformat()


def load_topics() -> list[dict]:
    if not TOPICS_PATH.exists():
        return [{'query': 'GP CPD courses Kuala Lumpur', 'max_results': 5}]
    data = json.loads(TOPICS_PATH.read_text())
    if not isinstance(data, list):
        raise ValueError('scrape_topics.json must be a list of {query,max_results}')
    topics = []
    for item in data:
        query = str(item.get('query') or '').strip()
        if 3 <= len(query) <= 300:
            topics.append({'query': query, 'max_results': int(item.get('max_results') or 5)})
    return topics[:20]


def daily_ceiling() -> int:
    try:
        return max(1, int(os.getenv('DAILY_SCRAPE_JOB_CEILING', '10')))
    except ValueError:
        return 10


def operator_account(db: Session) -> Account | None:
    return db.query(Account).filter_by(role='operator').order_by(Account.email).first()


def enqueue_daily(db: Session, force: bool = False) -> dict:
    """Enqueue one job per curated topic for today, respecting the daily ceiling."""
    op = operator_account(db)
    if not op:
        return {'enqueued': 0, 'skipped': 0, 'day': local_today(), 'error': 'No operator account to own scheduled jobs.'}
    day = local_today()
    topics = load_topics()
    ceiling = daily_ceiling()
    enqueued = 0
    skipped = 0
    used_today = 0
    for topic in topics:
        request_key = digest('daily:' + day + ':' + topic['query'])
        existing = db.query(Job).filter_by(request_key=request_key).first()
        if existing and not force:
            used_today += 1
            skipped += 1
            continue
        if existing and force and existing.status in ('queued', 'running'):
            used_today += 1
            skipped += 1
            continue
        if used_today >= ceiling:
            skipped += 1
            continue
        max_results = max(1, min(int(topic['max_results']), 5))
        if existing and force:
            existing.status = 'queued'
            existing.max_results = max_results
            existing.lease_token = None
            existing.lease_until = None
            existing.started_at = None
            existing.result = None
            used_today += 1
            enqueued += 1
            continue
        db.add(
            Job(
                account_id=op.id,
                request_key=request_key,
                query=topic['query'],
                max_results=max_results,
                status='queued',
                created_at=time.time(),
            )
        )
        used_today += 1
        enqueued += 1
    db.commit()
    return {'enqueued': enqueued, 'skipped': skipped, 'day': day, 'ceiling': ceiling, 'topics': len(topics)}
