"""Walk ingestion → hold → reject → hold → publish without spending Tavily or model credits.

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


def sample(title='Happy-path GP training'):
    training = Training(
        title=title,
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
        for request_key in ('happy-path-review', 'happy-path-reject'):
            existing = db.query(Job).filter_by(request_key=request_key).first()
            if existing:
                db.query(Candidate).filter_by(job_id=existing.id).delete()
                db.delete(existing)
                db.flush()
        publish_job = Job(account_id=operator.id, request_key='happy-path-review', query='Happy-path review rehearsal')
        reject_job = Job(account_id=operator.id, request_key='happy-path-reject', query='Happy-path reject rehearsal')
        db.add_all([publish_job, reject_job])
        db.flush()
        publish_candidate = Candidate(job_id=publish_job.id, source_key='happy-path-source', data=sample())
        reject_candidate = Candidate(job_id=reject_job.id, source_key='happy-path-reject', data=sample('Happy-path reject rehearsal'))
        db.add_all([publish_candidate, reject_candidate])
        db.commit()
        publish_id = publish_candidate.id
        reject_id = reject_candidate.id
    with TestClient(app, headers={'X-Care-Client': '1'}) as client:
        login = client.post('/api/v1/auth/login', json={'email': EMAIL, 'password': PASSWORD})
        if login.status_code != 200:
            raise SystemExit('Demo operator login failed. Check DEMO_MODE and the local database.')
        blank = client.post('/api/v1/admin/candidates/' + reject_id + '/review', json={'action': 'reject'})
        if blank.status_code != 422:
            raise SystemExit('Reject without a reason should return 422.')
        rejected = client.post(
            '/api/v1/admin/candidates/' + reject_id + '/review',
            json={'action': 'reject', 'reason': 'Not a Malaysia CPD event'},
        )
        if rejected.status_code != 200:
            raise SystemExit('Reject failed: ' + rejected.text)
        held = client.post('/api/v1/admin/candidates/' + publish_id + '/review', json={'action': 'hold', 'reason': 'Need MMC confirmation'})
        if held.status_code != 200:
            raise SystemExit('Hold failed: ' + held.text)
        published = client.post(
            '/api/v1/admin/candidates/' + publish_id + '/review',
            json={'action': 'publish', 'reason': 'Source excerpt confirmed on the labelled demo page'},
        )
        if published.status_code != 200:
            raise SystemExit('Publish failed: ' + published.text)
        queue = client.get('/api/v1/admin/candidates').json()['items']
        if any(item['id'] in (publish_id, reject_id) for item in queue):
            raise SystemExit('Reviewed candidates are still in the review queue.')
        titles = [item['title'] for item in client.get('/api/v1/trainings?period=all').json()['items']]
        if 'Happy-path reject rehearsal' in titles:
            raise SystemExit('Rejected candidate appeared in the catalogue.')
        if 'Happy-path GP training' not in titles:
            raise SystemExit('Published candidate is missing from the catalogue.')
    print('Reject, hold, and publish succeeded for the labelled happy-path candidates. No Tavily or model credits were used.')


if __name__ == '__main__':
    main()
