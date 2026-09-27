import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

FOLDER = tempfile.TemporaryDirectory()
os.environ['APP_ENV'] = 'test'
os.environ['DEMO_MODE'] = 'false'
os.environ['ALLOW_SIGNUP'] = 'true'
os.environ['SCRAPER_SERVICE_TOKEN'] = 'test-service-token'
os.environ['DAILY_SCRAPE_ENABLED'] = 'false'
os.environ['DIGEST_ENABLED'] = 'false'
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(FOLDER.name) / 'oauth.db')
os.environ.pop('GOOGLE_CLIENT_ID', None)
os.environ.pop('GOOGLE_CLIENT_SECRET', None)

from main import app


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, headers={'X-Care-Client': '1'})

    def test_unconfigured_start_is_unavailable(self):
        result = self.client.get('/api/v1/auth/oauth/google', follow_redirects=False)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()['error']['code'], 'unavailable')

    def test_callback_rejects_bad_state(self):
        result = self.client.get('/api/v1/auth/oauth/google/callback?code=abc&state=nope', follow_redirects=False)
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.json()['error']['code'], 'unauthenticated')

    def test_start_redirects_when_configured(self):
        with patch.dict(os.environ, {'GOOGLE_CLIENT_ID': 'cid.apps.googleusercontent.com', 'GOOGLE_CLIENT_SECRET': 'secret'}):
            result = self.client.get('/api/v1/auth/oauth/google', follow_redirects=False)
        self.assertEqual(result.status_code, 302)
        self.assertIn('accounts.google.com', result.headers['location'])
        self.assertIn('oauth_state', result.headers.get('set-cookie', ''))

    def test_upsert_stores_google_subject(self):
        from database import Base, SessionLocal, engine
        from oauth import upsert_account
        from portal_models import Account
        from security import password_hash
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            if not db.query(Account).first():
                db.add(Account(email='seed@example.com', name='Seed', password_hash=password_hash('Testing-strong-password')))
                db.commit()
            created = upsert_account(db, {'email': 'gp@example.com', 'name': 'Dr GP', 'subject': 'google-sub-1'}, True)
            db.commit()
            stored = db.query(Account).filter_by(email='gp@example.com').one()
            self.assertEqual(stored.id, created.id)
            self.assertEqual(stored.identity_issuer, 'https://accounts.google.com')
            self.assertEqual(stored.identity_subject, 'google-sub-1')
            again = upsert_account(db, {'email': 'other@example.com', 'name': 'Other', 'subject': 'google-sub-1'}, True)
            self.assertEqual(again.id, stored.id)


if __name__ == '__main__':
    unittest.main()
