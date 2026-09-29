import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from main import app, today
from database import Base, get_db
from portal_models import Account, Course, fill_course
from security import password_hash

PASSWORD = 'Testing-strong-password'
HASH = password_hash(PASSWORD)


def sample(title='Upcoming GP CPD', start='2099-06-15', city='Kuala Lumpur'):
    quote = f'{title} by Learning Institute in Malaysia {city}. {start}. CPD points 2.'
    return {
        'title': title,
        'provider': 'Learning Institute',
        'mode': 'in_person',
        'country': 'MY',
        'start_date': start,
        'city': city,
        'fee': 350,
        'currency': 'MYR',
        'source_url': 'https://example.org/upcoming',
        'source_text': quote,
        'points': 2,
        'credit_label': 'CPD',
        'evidence': {key: quote for key in ['title', 'provider', 'mode', 'country', 'start_date', 'city', 'points', 'credit_label']},
    }


class DigestCertificateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + self.folder.name + '/test.db', connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        def dependency():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = dependency
        self.env = patch.dict(os.environ, {
            'APP_ENV': 'test',
            'DEMO_MODE': 'false',
            'SCRAPER_SERVICE_TOKEN': 'test-service-token',
            'ALLOW_SIGNUP': 'true',
            'DAILY_SCRAPE_ENABLED': 'false',
            'DIGEST_ENABLED': 'false',
            'MAIL_PROVIDER': 'log',
            'DIGEST_LOG_DIR': self.folder.name + '/digests',
            'PUBLIC_API_BASE': 'http://testserver',
        })
        self.env.start()
        self.client = TestClient(app, headers={'X-Care-Client': '1', 'Origin': 'http://127.0.0.1:3000'})
        with self.Session() as db:
            doc = Account(email='doc@example.com', name='Doctor Dig', password_hash=HASH, city='Kuala Lumpur')
            op = Account(email='op@example.com', name='Operator', password_hash=HASH, role='operator')
            course = fill_course(Course(source_key='upcoming'), sample())
            db.add_all([doc, op, course])
            db.commit()
            self.doc_id = doc.id
            self.course_id = course.id
        self.client.post('/api/v1/auth/login', json={'email': 'doc@example.com', 'password': PASSWORD})

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.env.stop()
        self.engine.dispose()
        self.folder.cleanup()

    def test_suggestions_prefer_city(self):
        result = self.client.get('/api/v1/me/suggestions')
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertTrue(body['items'])
        self.assertEqual(body['items'][0]['city'], 'Kuala Lumpur')
        self.assertIn('advisory', body)
        with self.Session() as db:
            hidden = fill_course(Course(source_key='cancelled-upcoming'), sample('Cancelled GP', start='2099-07-01'))
            hidden.publication_status = 'cancelled'
            hidden.cancellation_status = 'cancelled'
            db.add(hidden)
            db.commit()
        skipped = self.client.get('/api/v1/me/suggestions').json()
        self.assertFalse(any(item['title'] == 'Cancelled GP' for item in skipped['items']))

    def test_suggestions_prefer_recent_mode(self):
        from portal_models import Record
        with self.Session() as db:
            online = fill_course(Course(source_key='kl-online'), sample('KL online CME', start='2099-08-01', city='Kuala Lumpur'))
            online.mode = 'online'
            online.data = {**online.data, 'mode': 'online'}
            later_city = fill_course(Course(source_key='kl-later-inperson'), sample('Later KL workshop', start='2099-09-01', city='Kuala Lumpur'))
            attended = fill_course(Course(source_key='past-online'), sample('Past webinar', start='2020-01-01', city='Penang'))
            attended.mode = 'online'
            attended.data = {**attended.data, 'mode': 'online'}
            db.add_all([online, later_city, attended])
            db.commit()
            db.add(Record(account_id=self.doc_id, course_id=attended.id, attended=True, attendance_status='attended', attended_on='2020-01-01'))
            db.commit()
        body = self.client.get('/api/v1/me/suggestions').json()
        self.assertEqual(body['preferred_mode'], 'online')
        self.assertEqual(body['items'][0]['title'], 'KL online CME')
        self.assertEqual(body['items'][0]['reason'], 'Matches your city and recent learning mode')

    def test_digest_opt_in_and_send(self):
        got = self.client.get('/api/v1/me/digest')
        self.assertEqual(got.status_code, 200)
        self.assertFalse(got.json()['opted_in'])
        patched = self.client.patch('/api/v1/me/digest', json={'opted_in': True, 'cadence_days': 14})
        self.assertEqual(patched.status_code, 200)
        self.assertTrue(patched.json()['opted_in'])
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': PASSWORD})
        run = self.client.post('/api/v1/admin/digests/run')
        self.assertEqual(run.status_code, 200, run.text)
        self.assertEqual(run.json()['sent'], 1)
        from portal_models import DigestSend
        with self.Session() as db:
            send = db.query(DigestSend).one()
            self.assertGreaterEqual(send.event_count, 1)
            self.assertEqual(send.recorded_points_snapshot, 0)
        logs = list(Path(self.folder.name, 'digests').glob('*.txt'))
        self.assertEqual(len(logs), 1)
        text = logs[0].read_text()
        self.assertIn('Upcoming catalogue sessions', text)
        self.assertIn('350 MYR', text)
        self.assertIn('/api/v1/digest/unsubscribe?token=', text)

    def test_unsubscribe_without_login(self):
        self.client.patch('/api/v1/me/digest', json={'opted_in': True})
        from portal_models import DigestPreference
        with self.Session() as db:
            token = db.get(DigestPreference, self.doc_id).unsubscribe_token
        bare = TestClient(app)
        html = bare.get('/api/v1/digest/unsubscribe', params={'token': token})
        self.assertEqual(html.status_code, 200)
        self.assertIn('text/html', html.headers.get('content-type', ''))
        self.assertIn('You are unsubscribed', html.text)
        self.client.post('/api/v1/auth/login', json={'email': 'doc@example.com', 'password': PASSWORD})
        self.assertFalse(self.client.get('/api/v1/me/digest').json()['opted_in'])
        json_again = TestClient(app).get(
            '/api/v1/digest/unsubscribe',
            params={'token': token},
            headers={'Accept': 'application/json'},
        )
        self.assertEqual(json_again.status_code, 200)
        self.assertFalse(json_again.json()['opted_in'])

    def test_digest_failure_uses_bounded_backoff(self):
        self.client.patch('/api/v1/me/digest', json={'opted_in': True})
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': PASSWORD})
        with patch('digest.send_via_provider', return_value={'status': 'failed', 'provider_message_id': None, 'error': 'SMTP down'}):
            first = self.client.post('/api/v1/admin/digests/run')
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()['failed'], 1)
            second = self.client.post('/api/v1/admin/digests/run')
            self.assertEqual(second.json()['failed'], 0)
            self.assertEqual(second.json()['sent'], 0)
        from digest import backoff_seconds
        from portal_models import DigestPreference
        with self.Session() as db:
            pref = db.get(DigestPreference, self.doc_id)
            self.assertEqual(pref.fail_count, 1)
            self.assertGreater(pref.next_retry_at, time.time())
            self.assertEqual(backoff_seconds(1), 15 * 60)
            self.assertEqual(backoff_seconds(8), 24 * 3600)
            pref.next_retry_at = time.time() - 1
            db.commit()
        with patch('digest.send_via_provider', return_value={'status': 'failed', 'provider_message_id': None, 'error': 'SMTP down'}):
            retried = self.client.post('/api/v1/admin/digests/run')
        self.assertEqual(retried.json()['failed'], 1)
        with self.Session() as db:
            pref = db.get(DigestPreference, self.doc_id)
            self.assertEqual(pref.fail_count, 2)

    def test_certificate_issue_and_download(self):
        with self.Session() as db:
            past = fill_course(Course(source_key='past-cme'), sample(title='Past CME', start='2026-01-10', city='Kuala Lumpur'))
            db.add(past)
            db.commit()
            past_id = past.id
        save = self.client.put(
            '/api/v1/me/trainings/' + past_id,
            json={
                'signed_up': True,
                'attended': True,
                'attended_on': '2026-01-15',
                'points': 4,
                'credit_label': 'CPD',
                'notes': '',
                'public': False,
                'version': 0,
            },
        )
        self.assertEqual(save.status_code, 200, save.text)
        issued = self.client.post('/api/v1/me/certificates', json={'year': 2026})
        self.assertEqual(issued.status_code, 201, issued.text)
        body = issued.json()
        self.assertEqual(body['recorded_points_snapshot'], 4)
        self.assertIn('CERT-01', body['disclaimer_version'])
        download = self.client.get(body['download_path'])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.headers['content-type'], 'application/pdf')
        self.assertTrue(download.content.startswith(b'%PDF-1.4'))
        self.assertIn(b'CareCredits', download.content)
        self.assertIn(b'not an MMC', download.content)
        self.assertIn(body['document_hash'].encode(), download.content)
        html = self.client.get(body['download_path'] + '?format=html')
        self.assertEqual(html.status_code, 200)
        self.assertIn('CareCredits', html.text)
        self.assertIn('not an MMC', html.text)
        self.assertIn('MOH', html.text)
        self.assertIn('APC', html.text)
        # Unicode names fold for Helvetica PDF but remain intact in HTML.
        from certificates import _pdf_escape

        self.assertIn('Jose', _pdf_escape('José'))
        self.assertNotIn('\u0301', _pdf_escape('José'))
        self.client.post('/api/v1/auth/login', json={'email': 'op@example.com', 'password': PASSWORD})
        self.assertEqual(self.client.get(body['download_path']).status_code, 404)


if __name__ == '__main__':
    unittest.main()
