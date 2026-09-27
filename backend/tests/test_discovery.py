import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from scraper.tavily import ProviderError as HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from scraper import tavily as d
import setup_tavily


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'TAVILY_API_KEY': 'test-only', 'DISCOVERY_API_TOKEN': 'operator'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_search_extract_contract_and_deduplication(self):
        replies = [
            {'results': [
                {'url': 'https://example.org/event#one', 'title': 'Course', 'content': 'Snippet'},
                {'url': 'https://example.org/event#two'},
                {'url': 'file:///etc/passwd'},
            ]},
            {'results': [{'url': 'https://example.org/event', 'raw_content': 'Event details'}]},
        ]
        with patch.object(d, 'urlopen', side_effect=[io.BytesIO(json.dumps(x).encode()) for x in replies]) as call:
            result = d.discover('cardiology', 5)
        self.assertEqual(call.call_count, 2)
        search = call.call_args_list[0].args[0]
        extract = call.call_args_list[1].args[0]
        self.assertEqual(search.full_url, 'https://api.tavily.com/search')
        self.assertIn('Malaysia medical CPD', json.loads(search.data)['query'])
        self.assertEqual(search.get_header('Authorization'), 'Bearer test-only')
        self.assertEqual(extract.full_url, 'https://api.tavily.com/extract')
        self.assertEqual(json.loads(extract.data)['urls'], ['https://example.org/event'])
        self.assertEqual(call.call_args_list[0].kwargs['timeout'], 30)
        self.assertEqual(result['sources'][0]['raw_content'], 'Event details')
        self.assertEqual(result['sources'][0]['verification_status'], 'unverified')
        self.assertEqual(len(result['sources']), 1)
        self.assertEqual(result['warnings'], [])
        self.assertNotIn('test-only', json.dumps(result))

    def test_empty_search_skips_extract(self):
        with patch.object(d, 'tavily_post', return_value={'results': []}) as call:
            self.assertEqual(d.discover('cardiology')['sources'], [])
            call.assert_called_once()

    def test_extraction_failure_keeps_snippets(self):
        source = {'results': [{'url': 'https://example.org/event', 'content': 'Retain me'}]}
        for failure in [HTTPException(504, 'Unavailable'), {'results': [], 'failed_results': [{}]}]:
            with self.subTest(failure=failure), patch.object(d, 'tavily_post', side_effect=[source, failure]):
                result = d.discover('cardiology')
                self.assertEqual(result['sources'][0]['snippet'], 'Retain me')
                self.assertEqual(result['sources'][0]['extraction_status'], 'failed')
                self.assertIsNone(result['sources'][0]['raw_content'])
                self.assertTrue(result['warnings'])

    def test_missing_key_makes_no_call(self):
        with patch.dict(os.environ, {'TAVILY_API_KEY': ''}), patch.object(d, 'urlopen') as call:
            with self.assertRaises(HTTPException) as error:
                d.discover('cardiology')
            self.assertEqual(error.exception.status_code, 503)
            call.assert_not_called()

    def test_url_filter(self):
        for url in ['javascript:alert(1)', 'http://localhost/a', 'https://x.local/a', 'http://127.0.0.1/a', 'https://user:pass@example.org/a', 'http://[::1]/', 'https://example.org:8080/a']:
            self.assertIsNone(d.source_url(url), url)

    def test_upstream_errors_sanitized(self):
        for status, expected in [(401, 503), (403, 503), (429, 429), (432, 429), (433, 429), (500, 502)]:
            error = HTTPError('https://api.tavily.com/search', status, 'secret-provider-body', {}, None)
            with self.subTest(status=status), patch.object(d, 'urlopen', side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    d.tavily_post('search', {}, 'test-only')
                self.assertEqual(caught.exception.status_code, expected)
                self.assertNotIn('secret', caught.exception.detail)
        with patch.object(d, 'urlopen', side_effect=URLError('private-details')):
            with self.assertRaises(HTTPException) as caught:
                d.tavily_post('search', {}, 'test-only')
            self.assertEqual(caught.exception.status_code, 504)

    def test_invalid_provider_response(self):
        for body in [b'not json', b'[]', b'{"results": null}']:
            with patch.object(d, 'urlopen', return_value=io.BytesIO(body)):
                with self.assertRaises(HTTPException) as caught:
                    d.tavily_post('search', {}, 'test-only')
                self.assertEqual(caught.exception.status_code, 502)

    def test_setup_preserves_other_settings_and_token(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.env.sample').write_text('DB_NAME=keep\nTAVILY_API_KEY=\nDISCOVERY_API_TOKEN=\n')
            with patch.object(setup_tavily, '__file__', str(root / 'scripts' / 'setup_tavily.py')), patch.object(setup_tavily.getpass, 'getpass', return_value='tvly-test-only'), patch('sys.stdout', new_callable=io.StringIO) as output:
                setup_tavily.main()
                first = (root / '.env').read_text()
                setup_tavily.main()
                self.assertEqual(first, (root / '.env').read_text())
                self.assertIn('DB_NAME=keep', first)
                self.assertIn('TAVILY_API_KEY=tvly-test-only', first)
                self.assertNotIn('tvly-test-only', output.getvalue())
                self.assertEqual((root / '.env').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
