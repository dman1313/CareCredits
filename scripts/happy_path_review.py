"""Walk ingestion → hold → publish without spending Tavily or model credits.

Run from the repository root with the backend virtualenv:

    python3 scripts/happy_path_review.py

Uses the local database and demo operator account. Live discovery is unchanged.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'backend')]
load_dotenv(root / '.env')
os.environ.setdefault('APP_ENV', 'development')
os.environ.setdefault('DEMO_MODE', 'true')
os.environ.setdefault('ALLOW_SIGNUP', 'true')
os.environ.setdefault('SCRAPER_SERVICE_TOKEN', 'happy-path-local-token')

from fastapi.testclient import TestClient
from main import app, initialize
from database import SessionLocal
from portal_models import Account, Candidate, Job
from shared.contracts import Training

QUOTE = (
    'Happy-path GP training by Learning Institute in Malaysia Kuala Lumpur online. '
    '2026-03-01. CPD points 2. Demonstration source only.'
)
EMAIL = 'demo@carecredits.local'
PASSWORD = 'CareCredits-demo-2026'


def sample():
    training = Training(
        title='Happy-path GP training',
        provider='Learning Institute',
        description='Operator review rehearsal. Not a live Tavily result.',
        start_date='2026-03-01',
        city='Kuala Lumpur',
        mode='online',
        country='MY',
        points=2,
        credit_label='CPD',
        source_url='https://example.org/carecredits-happy-path',
        source_text=QUOTE,
        evidence={key: QUOTE for key in ('title', 'provider', 'mode', 'country', 'start_date', 'city', 'points', 'credit_label')},
    )
    return training.model_dump(mode='json')


def main():
    initialize()
    with SessionLocal() as db:
        operator = db.query(Account).filter_by(email=EMAIL).first()
        if not operator or operator.role != 'operator':
            raise SystemExit('Demo operator is missing. Run python3 scripts/dev.py --demo first.')
        job = Job(account_id=operator.id, request_key='happy-path-review', query='Happy-path review rehearsal')
        existing = db.query(Job).filter_by(request_key=job.request_key).first()
        if existing:
            db.query(Candidate).filter_by(job_id=existing.id).delete()
            db.delete(existing)
            db.flush()
        db.add(job)
        db.flush()
        candidate = Candidate(job_id=job.id, source_key='happy-path-source', data=sample())
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id
    with TestClient(app, headers={'X-Care-Client': '1'}) as client:
        login = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': PASSWORD})
        if login.status_code != 200:
            raise SystemExit('Demo operator login failed. Check DEMO_MODE and the local database.')
        held = client.post('/api/v1/admin/candidates/' + candidate_id + '/review', json={'action': 'hold', 'reason': 'Need MMC confirmation'})
        if held.status_code != 200:
            raise SystemExit('Hold failed: ' + held.text)
        published = client.post(
            '/api/v1/admin/candidates/' + candidate_id + '/review',
            json={'action': 'publish', 'reason': 'Source excerpt confirmed on the labelled demo page'},
        )
        if published.status_code != 200:
            raise SystemExit('Publish failed: ' + published.text)
        queue = client.get('/api/v1/admin/candidates').json()['items']
        if any(item['id'] == candidate_id for item in queue):
            raise SystemExit('Published candidate is still in the review queue.')
    print('Hold and publish succeeded for the labelled happy-path candidate. No Tavily or model credits were used.')


if __name__ == '__main__':
    main()
