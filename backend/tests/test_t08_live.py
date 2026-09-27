"""T-08 live walk through the frontend proxy when a local portal is running."""
import json
import os
import unittest
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


FRONTEND = os.getenv('T08_FRONTEND_URL', 'http://127.0.0.1:3010').rstrip('/')


class LivePortalWalkTests(unittest.TestCase):
    def setUp(self):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def _json(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = Request(
            FRONTEND + path,
            data=data,
            method=method,
            headers={'Content-Type': 'application/json', 'X-Care-Client': '1', 'Origin': FRONTEND},
        )
        try:
            with self.opener.open(request, timeout=8) as response:
                return response.status, json.loads(response.read().decode())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode() or '{}')

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
