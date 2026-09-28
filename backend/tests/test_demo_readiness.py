import json
import unittest
from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from scripts.demo_readiness import (
    classify_backend,
    classify_frontend,
    classify_scraper,
    local_stack,
)


class FakeResponse:
    def __init__(self, body, status=200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def route(url, timeout=None, *args, **kwargs):
    mapping = {
        'http://127.0.0.1:3030/health/live': FakeResponse(b'{"status":"live"}'),
        'http://127.0.0.1:3030/': FakeResponse(b'<a class="skip-link">Skip to content</a>'),
        'http://127.0.0.1:3030/api/v1/config': FakeResponse(b'{"demo":true}'),
        'http://127.0.0.1:3010/health/live': HTTPError(url, 404, 'Not Found', hdrs=None, fp=BytesIO(b'404')),
        'http://127.0.0.1:3010/': FakeResponse(b'<html>CareCredits</html>'),
        'http://127.0.0.1:3010/api/v1/config': FakeResponse(b'{"demo":true}'),
        'http://127.0.0.1:3000/health/live': FakeResponse(b'{"status":"live"}'),
        'http://127.0.0.1:3000/': FakeResponse(b'<a>Skip to content</a>'),
        'http://127.0.0.1:3000/api/v1/config': HTTPError(url, 502, 'Bad Gateway', hdrs=None, fp=BytesIO(b'bad')),
        'http://127.0.0.1:8000/health/live': FakeResponse(b'{"status":"live"}'),
        'http://127.0.0.1:8000/api/v1/config': FakeResponse(b'{"demo":true}'),
        'http://127.0.0.1:8000/api/v1/me': HTTPError(url, 401, 'unauthenticated', hdrs=None, fp=BytesIO(b'{"error":{"code":"unauthenticated"}}')),
        'http://127.0.0.1:8010/health/live': FakeResponse(b'{"status":"ok"}'),
        'http://127.0.0.1:8010/api/v1/config': FakeResponse(b'{"demo":true}'),
        'http://127.0.0.1:8010/api/v1/me': HTTPError(url, 401, 'unauthenticated', hdrs=None, fp=BytesIO(b'{"error":{}}')),
        'http://127.0.0.1:8002/health/live': FakeResponse(b'{"status":"live"}'),
        'http://127.0.0.1:8002/health/ready': FakeResponse(b'{"status":"ready","tavily_configured":false,"model_ready":false}'),
    }
    result = mapping.get(url)
    if result is None:
        raise URLError('connection refused')
    if isinstance(result, Exception):
        raise result
    return result


class DemoReadinessStackTests(unittest.TestCase):
    def test_classifies_current_frontend_backend_and_stale_ports(self):
        with patch('scripts.demo_readiness.urlopen', side_effect=route):
            frontend = classify_frontend(3030)
            stale_ui = classify_frontend(3010)
            other = classify_frontend(3000)
            backend = classify_backend(8000)
            stale_api = classify_backend(8010)
            scraper = classify_scraper(8002)
        self.assertEqual(frontend['state'], 'carecredits-live')
        self.assertTrue(frontend['skip_link'])
        self.assertTrue(frontend['carecredits'])
        self.assertEqual(stale_ui['state'], 'stale-or-other')
        self.assertFalse(stale_ui['health_live'])
        self.assertEqual(other['state'], 'stale-or-other')
        self.assertTrue(other['health_live'])
        self.assertFalse(other['carecredits'])
        self.assertEqual(backend['state'], 'carecredits-live')
        self.assertEqual(stale_api['state'], 'stale-or-other')
        self.assertFalse(stale_api['health_live'])
        self.assertEqual(scraper['state'], 'carecredits-live')
        self.assertFalse(scraper['tavily_configured'])

    def test_local_stack_skips_paid_urls_and_includes_kinds(self):
        with patch('scripts.demo_readiness.urlopen', side_effect=route):
            rows = local_stack()
        kinds = {row['kind'] for row in rows}
        self.assertEqual(kinds, {'frontend', 'backend', 'scraper'})
        live = {(row['kind'], row['port']) for row in rows if row['state'] == 'carecredits-live'}
        self.assertIn(('frontend', 3030), live)
        self.assertIn(('backend', 8000), live)
        self.assertIn(('scraper', 8002), live)
        dumped = json.dumps(rows)
        self.assertNotIn('TAVILY', dumped)
        self.assertNotIn('MODEL_API_KEY', dumped)


if __name__ == '__main__':
    unittest.main()
