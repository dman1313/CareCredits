"""T-08 live walk through the frontend proxy when a local portal is running."""
import json
import os
import unittest
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


CANDIDATES = [
    os.getenv('T08_FRONTEND_URL', '').rstrip('/'),
    'http://127.0.0.1:3000',
    'http://127.0.0.1:3010',
]


def _carecredits_frontend():
    seen = []
    for candidate in CANDIDATES:
        if not candidate or candidate in seen:
            continue
        seen.append(candidate)
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        request = Request(
            candidate + '/api/v1/config',
            method='GET',
            headers={'X-Care-Client': '1', 'Origin': candidate},
        )
        try:
            with opener.open(request, timeout=3) as response:
                payload = json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            continue
        if isinstance(payload, dict) and {'demo', 'signup_enabled'} <= set(payload):
            return candidate
    return None


FRONTEND = _carecredits_frontend()


class LivePortalWalkTests(unittest.TestCase):
    def setUp(self):
        if not FRONTEND:
            self.skipTest('CareCredits frontend is not running on :3000 or :3010')
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def _open(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = Request(
            FRONTEND + path,
            data=data,
            method=method,
            headers={'Content-Type': 'application/json', 'X-Care-Client': '1', 'Origin': FRONTEND},
        )
        try:
            with self.opener.open(request, timeout=8) as response:
                return response.status, response.headers.get('Content-Type') or '', response.read()
        except HTTPError as exc:
            return exc.code, exc.headers.get('Content-Type') or '', exc.read()

    def _json(self, method, path, body=None):
        status, _ctype, raw = self._open(method, path, body)
        try:
            return status, json.loads(raw.decode() or '{}')
        except ValueError:
            return status, raw

    def test_sign_in_search_and_detail_through_frontend_proxy(self):
        try:
            status, user = self._json(
                'POST',
                '/api/v1/auth/login',
                {'email': 'demo@carecredits.local', 'password': 'CareCredits-demo-2026'},
            )
        except URLError:
            self.skipTest('Frontend is not running at ' + FRONTEND)
        self.assertEqual(status, 200, user)
        self.assertTrue(user.get('name'))
        progress = self._json('GET', '/api/v1/me/progress')
        self.assertEqual(progress[0], 200, progress[1])
        self.assertIn('excluded_reasons', progress[1])
        suggestions = self._json('GET', '/api/v1/me/suggestions')
        self.assertEqual(suggestions[0], 200, suggestions[1])
        digest = self._json('GET', '/api/v1/me/digest')
        self.assertEqual(digest[0], 200, digest[1])
        self.assertIn('opted_in', digest[1])
        export_status, export_type, _raw = self._open('GET', '/api/v1/me/export/csv')
        self.assertEqual(export_status, 200)
        self.assertIn('text/csv', export_type)
        listed = self._json('GET', '/api/v1/trainings?period=upcoming&q=GP&page_size=5')
        self.assertEqual(listed[0], 200, listed[1])
        items = listed[1].get('items') or []
        if not items:
            listed = self._json('GET', '/api/v1/trainings?period=all&q=GP&page_size=5')
            self.assertEqual(listed[0], 200, listed[1])
            items = listed[1].get('items') or []
        self.assertTrue(items, 'Catalogue search returned no trainings')
        course_id = items[0]['id']
        before = self._json('GET', '/api/v1/me/trainings')
        detail = self._json('GET', '/api/v1/trainings/' + course_id)
        self.assertEqual(detail[0], 200, detail[1])
        self.assertIn('title', detail[1])
        self.assertIsNone(detail[1].get('record'))
        after = self._json('GET', '/api/v1/me/trainings')
        self.assertEqual(before[1].get('total'), after[1].get('total'))
