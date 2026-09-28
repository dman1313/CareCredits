import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ['APP_ENV'] = 'development'
os.environ['DEMO_MODE'] = 'false'
os.environ['ALLOW_SIGNUP'] = 'true'
os.environ['SCRAPER_SERVICE_TOKEN'] = 'test-service-token'
os.environ['DAILY_SCRAPE_ENABLED'] = 'false'
os.environ.pop('TYPESAFE_API_KEY', None)

FOLDER = tempfile.TemporaryDirectory()
DB_PATH = Path(FOLDER.name) / 'catalogue-test.db'
os.environ['DATABASE_URL'] = 'sqlite:///' + str(DB_PATH)

from main import app, source_key
from database import Base, get_db, engine
from portal_models import Account, Candidate, Course, Job, fill_course
from security import password_hash
from shared.contracts import Training
from schedule import enqueue_daily, load_topics


QUOTE = (
    'Primary Care Update by Academy of Family Physicians in Malaysia Kuala Lumpur. '
    '2026-06-01 in person. CPD points 2. Source backed excerpt.'
)


def sample(**overrides):
    row = {
        'title': 'Primary Care Update 2026',
        'provider': 'Academy of Family Physicians',
        'mode': 'in_person',
        'country': 'MY',
        'start_date': '2026-06-01',
        'city': 'Kuala Lumpur',
        'points': 2,
        'credit_label': 'CPD',
        'source_url': 'https://example.org/afpm-primary-care-update-2026',
        'source_text': QUOTE,
        'evidence': {key: QUOTE for key in ['title', 'provider', 'mode', 'country', 'start_date', 'city', 'points', 'credit_label']},
    }
    row.update(overrides)
    return Training(**row).model_dump(mode='json')


class CatalogueApiTests(unittest.TestCase):
    def setUp(self):
        if 'demo.db' in str(engine.url):
            raise RuntimeError('Catalogue tests must not drop the live DEMO_MODE database')
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

        def dependency():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = dependency
        with self.Session() as db:
            op = Account(
                email='op@example.com',
                name='Operator',
                password_hash=password_hash('CareCredits-demo-2026'),
                role='operator',
            )
            db.add(op)
            db.commit()
        self.client = TestClient(app, headers={'X-Care-Client': '1', 'Origin': 'http://127.0.0.1:3000'})
        self.service = {'Authorization': 'Bearer test-service-token'}
        self.env = patch.dict(os.environ, {'TYPESAFE_API_KEY': ''}, clear=False)
        self.env.start()
        self.keyfile = patch('jev.keyfile_path')
        mocked = self.keyfile.start()
        mocked.return_value.is_file.return_value = False

    def tearDown(self):
        self.keyfile.stop()
        self.env.stop()
        app.dependency_overrides.clear()

    def test_connect_and_lookup_exact(self):
        training = sample()
        with self.Session() as db:
            db.add(fill_course(Course(source_key=source_key(training)), training))
            db.commit()
        self.assertEqual(self.client.get('/internal/v1/catalogue/connect', headers=self.service).status_code, 200)
        lookup = self.client.post('/internal/v1/catalogue/lookup', json={'candidate': training}, headers=self.service)
        self.assertEqual(lookup.status_code, 200, lookup.text)
        self.assertIsNotNone(lookup.json()['exact'])
        decide = self.client.post(
            '/internal/v1/catalogue/decide',
            json={'candidate': training, 'matches': []},
            headers=self.service,
        )
        self.assertEqual(decide.json()['decision'], 'exists')

    def test_decide_stores_judgment_on_existing_candidate(self):
        training = sample(title='Held GP Workshop', source_url='https://example.org/held-gp-workshop')
        key = source_key(training)
        with self.Session() as db:
            job = Job(account_id=db.query(Account).first().id, request_key='held-decide', query='GP', status='succeeded')
            db.add(job)
            db.flush()
            candidate = Candidate(job_id=job.id, source_key=key, data=training, status='pending')
            db.add(candidate)
            db.commit()
            candidate_id = candidate.id
        decide = self.client.post(
            '/internal/v1/catalogue/decide',
            json={'candidate': training, 'matches': []},
            headers=self.service,
        )
        self.assertEqual(decide.status_code, 200, decide.text)
        self.assertEqual(decide.json()['decision'], 'new')
        self.assertEqual(decide.json()['candidate_id'], candidate_id)
        with self.Session() as db:
            stored = db.get(Candidate, candidate_id)
            self.assertEqual((stored.data or {}).get('_judgment', {}).get('decision'), 'new')

    def test_decide_new_without_matches_and_save(self):
        training = sample(title='Brand New GP Workshop', source_url='https://example.org/new-gp-workshop')
        decide = self.client.post(
            '/internal/v1/catalogue/decide',
            json={'candidate': training, 'matches': []},
            headers=self.service,
        )
        self.assertEqual(decide.status_code, 200, decide.text)
        self.assertEqual(decide.json()['decision'], 'new')
        save = self.client.post(
            '/internal/v1/catalogue/save',
            json={'candidate': training, 'judgment': decide.json()},
            headers=self.service,
        )
        self.assertEqual(save.status_code, 200, save.text)
        self.assertEqual(save.json()['decision'], 'new')
        self.assertEqual(save.json()['status'], 'pending')
        self.assertFalse(save.json().get('course_id'))
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': 'CareCredits-demo-2026'})
        listed = self.client.get('/api/v1/trainings?period=all&include_unknown=true')
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()['total'], 0)
        queue = self.client.get('/api/v1/admin/candidates').json()
        self.assertEqual(queue['items'][0]['status'], 'pending')

    def test_save_new_auto_publishes_only_when_policy_allows(self):
        training = sample(title='Auto Publish Workshop', source_url='https://example.org/auto-publish-workshop')
        with patch.dict(os.environ, {'CATALOGUE_AUTO_PUBLISH_NEW': 'true'}):
            save = self.client.post(
                '/internal/v1/catalogue/save',
                json={'candidate': training, 'judgment': {'decision': 'new', 'confidence': 1, 'probabilities': {'new': 1}}},
                headers=self.service,
            )
        self.assertEqual(save.status_code, 200, save.text)
        self.assertEqual(save.json()['status'], 'published')
        self.assertTrue(save.json().get('course_id'))
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': 'CareCredits-demo-2026'})
        listed = self.client.get('/api/v1/trainings?period=all&include_unknown=true')
        self.assertGreaterEqual(listed.json()['total'], 1)

    def test_near_match_without_typesafe_is_uncertain(self):
        training = sample()
        with self.Session() as db:
            course = fill_course(Course(source_key='other-key'), training)
            db.add(course)
            db.commit()
            course_id = course.id
        other = sample(title='Primary Care Update Evening', source_url='https://example.org/other')
        decide = self.client.post(
            '/internal/v1/catalogue/decide',
            json={
                'candidate': other,
                'matches': [{'id': course_id, 'title': training['title'], 'provider': training['provider'], 'start_date': training['start_date'], 'city': training['city'], 'mode': training['mode']}],
            },
            headers=self.service,
        )
        self.assertEqual(decide.status_code, 200, decide.text)
        self.assertEqual(decide.json()['decision'], 'uncertain')
        save = self.client.post(
            '/internal/v1/catalogue/save',
            json={'candidate': other, 'judgment': decide.json()},
            headers=self.service,
        )
        self.assertEqual(save.json()['status'], 'held')

    def test_daily_scrape_enqueue(self):
        topics = load_topics()
        self.assertTrue(topics)
        self.assertTrue(any('site:' in item['query'] for item in topics))
        self.assertTrue(any(item['max_results'] != 5 for item in topics), 'at least one topic should exercise non-default max_results')
        first = enqueue_daily(self.Session())
        self.assertGreaterEqual(first['enqueued'], 1)
        self.assertLessEqual(first['enqueued'], first['ceiling'])
        by_query = {item['query']: max(1, min(int(item['max_results']), 5)) for item in topics}
        with self.Session() as db:
            matched = [job for job in db.query(Job).all() if job.query in by_query]
            self.assertTrue(matched)
            for job in matched:
                self.assertEqual(job.max_results, by_query[job.query])
        second = enqueue_daily(self.Session())
        self.assertEqual(second['enqueued'], 0)
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': 'CareCredits-demo-2026'})
        forced = self.client.post('/api/v1/admin/daily-scrape?force=true')
        self.assertEqual(forced.status_code, 202, forced.text)
        listed = self.client.get('/api/v1/admin/scrape-topics')
        self.assertEqual(listed.status_code, 200, listed.text)
        body = listed.json()
        self.assertGreaterEqual(len(body['topics']), 1)
        self.assertEqual(body['topics'][0].keys(), {'query', 'max_results'})
        self.assertGreaterEqual(body['ceiling'], 1)
        self.assertTrue(body['day'])
        with self.Session() as db:
            db.add(
                Account(
                    email='doc@example.com',
                    name='Doctor',
                    password_hash=password_hash('CareCredits-demo-2026'),
                    role='doctor',
                )
            )
            db.commit()
        self.client.post('/api/v1/auth/logout')
        self.client.post('/api/v1/auth/login', json={'email': 'doc@example.com', 'password': 'CareCredits-demo-2026'})
        self.assertEqual(self.client.get('/api/v1/admin/scrape-topics').status_code, 403)

    def test_auto_daily_scrape_stays_off_until_tavily_and_model_ready(self):
        from main import _paid_scrape_ready
        with patch('main._scraper_service_status', return_value={'tavily_configured': True, 'model_ready': False}):
            self.assertFalse(_paid_scrape_ready())
        with patch('main._scraper_service_status', return_value={'tavily_configured': False, 'model_ready': True}):
            self.assertFalse(_paid_scrape_ready())
        with patch('main._scraper_service_status', return_value={'tavily_configured': True, 'model_ready': True}):
            self.assertTrue(_paid_scrape_ready())

    def test_operator_api_blocks_tavily_spend_without_model(self):
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': 'CareCredits-demo-2026'})
        with patch('main._scraper_service_status', return_value={'tavily_configured': True, 'model_ready': False}):
            blocked = self.client.post(
                '/api/v1/admin/ingestion-jobs',
                json={'query': 'GP CPD Kuala Lumpur'},
                headers={'Idempotency-Key': 'tavily-only-block'},
            )
            self.assertEqual(blocked.status_code, 409, blocked.text)
            self.assertEqual(
                blocked.json()['error']['message'],
                'Live discovery stays off until Tavily and the open-weight model are ready.',
            )
            daily = self.client.post('/api/v1/admin/daily-scrape')
            self.assertEqual(daily.status_code, 409, daily.text)
            retry = self.client.post('/api/v1/admin/ingestion-jobs/missing-job/retry')
            self.assertEqual(retry.status_code, 409, retry.text)
        with patch('main._scraper_service_status', return_value={'tavily_configured': True, 'model_ready': True}):
            allowed = self.client.post(
                '/api/v1/admin/ingestion-jobs',
                json={'query': 'GP CPD Kuala Lumpur'},
                headers={'Idempotency-Key': 'tavily-ready-allow'},
            )
            self.assertEqual(allowed.status_code, 202, allowed.text)

    def test_changed_content_queues_refresh_without_duplicate(self):
        training = sample()
        with patch.dict(os.environ, {'CATALOGUE_AUTO_PUBLISH_NEW': 'true'}):
            first = self.client.post(
                '/internal/v1/catalogue/save',
                json={'candidate': training, 'judgment': {'decision': 'new', 'confidence': 1, 'probabilities': {'new': 1}}},
                headers=self.service,
            )
        self.assertEqual(first.status_code, 200, first.text)
        course_id = first.json()['course_id']
        changed = sample()
        changed['description'] = 'Updated brochure copy with a new fee note.'
        changed['fee'] = 150
        changed['currency'] = 'MYR'
        changed['evidence'] = {**changed['evidence'], 'fee': QUOTE, 'currency': QUOTE, 'description': QUOTE}
        again = self.client.post(
            '/internal/v1/catalogue/save',
            json={
                'candidate': changed,
                'judgment': {'decision': 'exists', 'confidence': 1, 'matched_session_id': course_id, 'probabilities': {'exists': 1}},
            },
            headers=self.service,
        )
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()['status'], 'exists')
        self.assertEqual(again.json()['course_id'], course_id)
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': 'CareCredits-demo-2026'})
        listed = self.client.get('/api/v1/trainings?period=all&q=Primary%20Care%20Update').json()
        self.assertEqual(listed['total'], 1)
        queue = self.client.get('/api/v1/admin/candidates').json()['items']
        held = next(item for item in queue if item['id'] == again.json()['candidate_id'])
        self.assertEqual(held['status'], 'held')
        diff = {row['field']: row for row in held['data'].get('_refresh_diff') or []}
        self.assertEqual(diff['fee']['published'], None)
        self.assertEqual(diff['fee']['proposed'], 150)
        self.assertIn('description', diff)
        published = self.client.post(
            '/api/v1/admin/candidates/' + held['id'] + '/review',
            json={'action': 'publish', 'reason': 'Fee change is source-backed', 'version': held['version']},
        )
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()['status'], 'published')
        self.assertEqual(published.json()['resulting_course_id'], course_id)
        listed = self.client.get('/api/v1/trainings?period=all&q=Primary%20Care%20Update').json()
        self.assertEqual(listed['total'], 1)
        self.assertEqual(listed['items'][0]['id'], course_id)
        self.assertEqual(listed['items'][0]['fee'], 150)

    def test_exists_refresh_updates_matched_course_when_source_key_drifts(self):
        training = sample(title='Primary Care Update 2026')
        with patch.dict(os.environ, {'CATALOGUE_AUTO_PUBLISH_NEW': 'true'}):
            first = self.client.post(
                '/internal/v1/catalogue/save',
                json={'candidate': training, 'judgment': {'decision': 'new', 'confidence': 1, 'probabilities': {'new': 1}}},
                headers=self.service,
            )
        course_id = first.json()['course_id']
        renamed = sample(title='Primary Care Update KL 2026')
        renamed['evidence'] = {**renamed['evidence'], 'title': QUOTE}
        renamed['source_text'] = QUOTE
        again = self.client.post(
            '/internal/v1/catalogue/save',
            json={
                'candidate': renamed,
                'judgment': {'decision': 'exists', 'confidence': 1, 'matched_session_id': course_id, 'probabilities': {'exists': 1}},
            },
            headers=self.service,
        )
        self.assertEqual(again.json()['course_id'], course_id)
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': 'CareCredits-demo-2026'})
        held_id = again.json()['candidate_id']
        held = next(item for item in self.client.get('/api/v1/admin/candidates').json()['items'] if item['id'] == held_id)
        published = self.client.post(
            '/api/v1/admin/candidates/' + held_id + '/review',
            json={'action': 'publish', 'reason': 'Same session, updated title', 'version': held['version']},
        )
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()['resulting_course_id'], course_id)
        listed = self.client.get('/api/v1/trainings?period=all&include_unknown=true').json()
        self.assertEqual(listed['total'], 1)
        self.assertEqual(listed['items'][0]['id'], course_id)
        self.assertEqual(listed['items'][0]['title'], 'Primary Care Update KL 2026')


if __name__ == '__main__':
    unittest.main()
