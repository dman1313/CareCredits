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
from portal_models import Account, Course, fill_course
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
        self.client = TestClient(app, headers={'X-Care-Client': '1'})
        self.service = {'Authorization': 'Bearer test-service-token'}
        self.keyfile = patch('jev.keyfile_path')
        mocked = self.keyfile.start()
        mocked.return_value.is_file.return_value = False

    def tearDown(self):
        self.keyfile.stop()
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
        self.assertEqual(save.json()['status'], 'published')
        self.assertTrue(save.json().get('course_id'))
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': 'CareCredits-demo-2026'})
        listed = self.client.get('/api/v1/trainings?period=all&include_unknown=true')
        self.assertEqual(listed.status_code, 200, listed.text)
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
        self.assertTrue(load_topics())
        first = enqueue_daily(self.Session())
        self.assertGreaterEqual(first['enqueued'], 1)
        second = enqueue_daily(self.Session())
        self.assertEqual(second['enqueued'], 0)
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': 'CareCredits-demo-2026'})
        forced = self.client.post('/api/v1/admin/daily-scrape?force=true')
        self.assertEqual(forced.status_code, 202, forced.text)

    def test_changed_content_queues_refresh_without_duplicate(self):
        training = sample()
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
        self.assertTrue(any(item['status'] == 'held' and item['id'] == again.json()['candidate_id'] for item in queue))


if __name__ == '__main__':
    unittest.main()
