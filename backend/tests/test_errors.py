import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

FOLDER = tempfile.TemporaryDirectory()
os.environ['APP_ENV'] = 'test'
os.environ['DEMO_MODE'] = 'false'
os.environ['ALLOW_SIGNUP'] = 'true'
os.environ['SCRAPER_SERVICE_TOKEN'] = 'test-service-token'
os.environ['DAILY_SCRAPE_ENABLED'] = 'false'
os.environ['DIGEST_ENABLED'] = 'false'
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(FOLDER.name) / 'errors.db')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import Base, get_db


class ErrorEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ['DATABASE_URL'])
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)

        def dependency():
            with Session() as db:
                yield db

        app.dependency_overrides[get_db] = dependency
        self.client = TestClient(app, headers={'X-Care-Client': '1', 'Origin': 'http://127.0.0.1:3000'})

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_unauthenticated_uses_envelope(self):
        result = self.client.get('/api/v1/me')
        self.assertEqual(result.status_code, 401)
        body = result.json()['error']
        self.assertEqual(body['code'], 'unauthenticated')
        self.assertTrue(body['message'])
        self.assertTrue(body['request_id'])
        self.assertEqual(result.headers.get('x-request-id'), body['request_id'])

    def test_validation_uses_envelope(self):
        result = self.client.post('/api/v1/auth/login', json={'email': 'bad', 'password': 'short'})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(result.json()['error']['code'], 'invalid')

    def test_unsubscribe_unknown_token_uses_envelope(self):
        result = self.client.get('/api/v1/digest/unsubscribe', params={'token': 'not-a-token'}, headers={'Accept': 'application/json'})
        self.assertEqual(result.status_code, 404)
        body = result.json()['error']
        self.assertEqual(body['code'], 'not_found')
        self.assertTrue(body['request_id'])

    def test_liveness_does_not_require_database(self):
        live = self.client.get('/health/live')
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()['status'], 'ok')

    def test_ready_reports_database_and_fails_closed(self):
        ready = self.client.get('/health/ready')
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertEqual(ready.json(), {'status': 'ready', 'database': 'ready'})

        class Boom:
            def execute(self, *_args, **_kwargs):
                raise RuntimeError('db down')

        def dependency():
            yield Boom()

        app.dependency_overrides[get_db] = dependency
        down = self.client.get('/health/ready')
        self.assertEqual(down.status_code, 503)
        self.assertEqual(down.json()['error']['code'], 'unavailable')
        self.assertNotIn('db down', down.text)


if __name__ == '__main__':
    unittest.main()
