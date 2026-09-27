import os
import unittest
from unittest.mock import patch
from scraper.health import ready, start


class ScraperHealthTests(unittest.TestCase):
    def test_ready_fails_closed_without_required_config(self):
        with patch.dict(os.environ, {'SCRAPER_SERVICE_TOKEN': '', 'BACKEND_INTERNAL_URL': '', 'TAVILY_API_KEY': ''}, clear=False):
            payload = ready()
            self.assertEqual(payload['status'], 'not_ready')
            self.assertIn('SCRAPER_SERVICE_TOKEN', payload['missing'])

    def test_ready_does_not_call_paid_providers(self):
        with patch.dict(os.environ, {'SCRAPER_SERVICE_TOKEN': 'token', 'BACKEND_INTERNAL_URL': 'http://127.0.0.1:8000', 'TAVILY_API_KEY': 'set', 'MODEL_API_KEY': '', 'MODEL_ID': ''}, clear=False):
            payload = ready()
            self.assertEqual(payload['status'], 'ready')
            self.assertTrue(payload['tavily_configured'])
            self.assertFalse(payload['model_ready'])

    def test_model_ready_requires_caps(self):
        env = {
            'SCRAPER_SERVICE_TOKEN': 'token',
            'BACKEND_INTERNAL_URL': 'http://127.0.0.1:8000',
            'MODEL_API_KEY': 'set',
            'MODEL_ID': 'test/model',
            'MODEL_WEIGHTS_URL': 'https://example.org/weights',
            'MODEL_LICENSE_URL': 'https://example.org/license',
            'MODEL_OPEN_WEIGHT_CONFIRMED': 'true',
            'MODEL_MAX_INPUT_CHARS': '',
            'MODEL_MAX_OUTPUT_TOKENS': '',
        }
        with patch.dict(os.environ, env, clear=False):
            payload = ready()
            self.assertEqual(payload['status'], 'ready')
            self.assertFalse(payload['model_ready'])
            self.assertIn('MODEL_MAX_INPUT_CHARS', payload['missing_model'])
        env['MODEL_MAX_INPUT_CHARS'] = '12000'
        env['MODEL_MAX_OUTPUT_TOKENS'] = '4000'
        with patch.dict(os.environ, env, clear=False):
            self.assertTrue(ready()['model_ready'])

    def test_health_server_defaults_to_localhost(self):
        with patch.dict(os.environ, {'SCRAPER_HEALTH_HOST': '', 'SCRAPER_HEALTH_PORT': '18002'}, clear=False):
            server = start()
        try:
            self.assertEqual(server.server_address[0], '127.0.0.1')
        finally:
            server.shutdown()
            server.server_close()
