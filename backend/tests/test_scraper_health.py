import os
import unittest
from unittest.mock import patch
from scraper.health import ready


class ScraperHealthTests(unittest.TestCase):
    def test_ready_fails_closed_without_required_config(self):
        with patch.dict(os.environ, {'SCRAPER_SERVICE_TOKEN': '', 'BACKEND_INTERNAL_URL': '', 'TAVILY_API_KEY': ''}, clear=False):
            payload = ready()
            self.assertEqual(payload['status'], 'not_ready')
            self.assertIn('SCRAPER_SERVICE_TOKEN', payload['missing'])

    def test_ready_does_not_call_paid_providers(self):
        with patch.dict(os.environ, {'SCRAPER_SERVICE_TOKEN': 'token', 'BACKEND_INTERNAL_URL': 'http://127.0.0.1:8000', 'TAVILY_API_KEY': 'set'}, clear=False):
            payload = ready()
            self.assertEqual(payload['status'], 'ready')
            self.assertTrue(payload['tavily_configured'])
