import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scraper import firehose as f
from scraper.worker import merge_sources, run_job


SSE = (
    'event: connected\n'
    'data: {}\n'
    '\n'
    'event: update\n'
    'data: {"document":{"url":"https://example.org/cme#one","title":"Malaysia CME course","markdown":"CPD course in Kuala Lumpur"}}\n'
    '\n'
    'event: update\n'
    'data: {"document":{"url":"https://example.org/cme#two","title":"Malaysia CME course","markdown":"same page"}}\n'
    '\n'
    'event: end\n'
    'data: {}\n'
    '\n'
)


class FirehoseTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'FIREHOSE_MGMT_KEY': 'fhm_test-only-key'}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_missing_key_makes_no_call(self):
        with patch.dict(os.environ, {'FIREHOSE_MGMT_KEY': '', 'FIREHOSE_MANAGEMENT_KEY': ''}), patch.object(f, 'urlopen') as call:
            self.assertFalse(f.configured())
            with self.assertRaises(f.FirehoseError) as error:
                f.discover('GP CPD')
            self.assertEqual(error.exception.status_code, 503)
            call.assert_not_called()

    def test_ensure_tap_reuse_and_stream_dedupe(self):
        replies = [
            {'taps': [{'name': 'CareCredits CPD', 'token': 'fh_tap-token'}]},
            {'rules': [{'tag': 'my-cpd'}, {'tag': 'my-events'}]},
            {'sse': SSE},
        ]

        def fake_request(method, path, token, payload=None, query=None, timeout=20):
            self.assertTrue(token.startswith('fhm_') or token.startswith('fh_'))
            if path == '/v1/taps' and method == 'GET':
                return replies[0]
            if path == '/v1/rules' and method == 'GET':
                return replies[1]
            if path == '/v1/stream':
                self.assertEqual(query['since'], '24h')
                return replies[2]
            raise AssertionError(path)

        with patch.object(f, 'firehose_request', side_effect=fake_request):
            result = f.discover('Malaysia CME course', 5)
        self.assertEqual(result['provider'], 'firehose')
        self.assertEqual(len(result['sources']), 1)
        self.assertEqual(result['sources'][0]['url'], 'https://example.org/cme')
        self.assertEqual(result['sources'][0]['extraction_status'], 'success')
        self.assertNotIn('fhm_test-only-key', json.dumps(result))

    def test_upstream_errors_sanitized(self):
        error = HTTPError('https://api.firehose.com/v1/taps', 401, 'secret-provider-body', {}, None)
        with patch.object(f, 'urlopen', side_effect=error):
            with self.assertRaises(f.FirehoseError) as caught:
                f.firehose_request('GET', '/v1/taps', 'fhm_test-only-key')
            self.assertEqual(caught.exception.status_code, 503)
            self.assertNotIn('secret', caught.exception.detail)

    def test_worker_merges_firehose_when_configured(self):
        tavily = {
            'sources': [{
                'url': 'https://example.org/tavily',
                'title': 'Tavily',
                'snippet': 'Snippet',
                'raw_content': 'Page text',
                'extraction_status': 'success',
                'verification_status': 'unverified',
            }],
            'warnings': [],
        }
        extra = {
            'sources': [{
                'url': 'https://example.org/firehose',
                'title': 'Firehose CME',
                'snippet': 'Malaysia CME',
                'raw_content': 'Malaysia CME course',
                'extraction_status': 'success',
                'verification_status': 'unverified',
            }],
            'warnings': [],
        }
        with patch('scraper.worker.discover', return_value=tavily), patch('scraper.worker.firehose_configured', return_value=True), patch('scraper.worker.firehose_discover', return_value=extra) as firehose, patch.dict(os.environ, {'MODEL_API_KEY': ''}):
            result = run_job({'query': 'GP', 'lease_token': 'test'}, lambda: None)
        urls = [item['url'] for item in result['sources']]
        self.assertIn('https://example.org/tavily', urls)
        self.assertIn('https://example.org/firehose', urls)
        firehose.assert_called_once_with('GP', 4)

    def test_worker_skips_firehose_when_tavily_filled_the_job_limit(self):
        tavily = {
            'sources': [
                {
                    'url': f'https://example.org/tavily-{i}',
                    'title': 'Tavily',
                    'snippet': 'Snippet',
                    'raw_content': 'Page text',
                    'extraction_status': 'success',
                    'verification_status': 'unverified',
                }
                for i in range(5)
            ],
            'warnings': [],
        }
        with patch('scraper.worker.discover', return_value=tavily), patch(
            'scraper.worker.firehose_configured', return_value=True
        ), patch('scraper.worker.firehose_discover') as firehose, patch.dict(os.environ, {'MODEL_API_KEY': ''}):
            result = run_job({'query': 'GP', 'lease_token': 'test', 'max_results': 5}, lambda: None)
        firehose.assert_not_called()
        self.assertEqual(len(result['sources']), 5)

    def test_merge_sources_dedupes(self):
        merged = merge_sources(
            [{'url': 'https://example.org/a'}],
            [{'url': 'https://example.org/a'}, {'url': 'https://example.org/b'}],
            limit=5,
        )
        self.assertEqual([item['url'] for item in merged], ['https://example.org/a', 'https://example.org/b'])

    def test_merge_sources_stays_within_job_limit(self):
        extra = [{'url': f'https://example.org/{i}'} for i in range(8)]
        merged = merge_sources([{'url': 'https://example.org/seed'}], extra, limit=5)
        self.assertEqual(len(merged), 5)


if __name__ == '__main__':
    unittest.main()
