import socket
import tempfile
import unittest
from pathlib import Path

from scripts.dev import free_port, service_environments


class DevPortTests(unittest.TestCase):
    def test_free_port_skips_a_bound_preferred_port(self):
        occupied = socket.socket()
        occupied.bind(('127.0.0.1', 0))
        preferred = occupied.getsockname()[1]
        try:
            chosen = free_port(preferred)
            self.assertNotEqual(chosen, preferred)
            self.assertGreaterEqual(chosen, preferred)
        finally:
            occupied.close()

    def test_service_environments_point_backend_at_scraper_health_without_model_secret(self):
        root = Path(tempfile.mkdtemp())
        settings = {
            'MODEL_API_KEY': 'secret-model-key',
            'MODEL_ID': 'Qwen/Qwen3-test',
            'MODEL_PUBLISHER': 'Qwen',
            'MODEL_WEIGHTS_URL': 'https://example.org/weights',
            'MODEL_LICENSE_URL': 'https://example.org/license',
            'TAVILY_API_KEY': 'secret-tavily',
            'FIREHOSE_MGMT_KEY': 'secret-firehose',
            'TYPESAFE_API_KEY': 'secret-typesafe',
            'CATALOGUE_AUTO_PUBLISH_NEW': 'false',
            'SCRAPE_TOPICS_FILE': '/tmp/topics.json',
        }
        backend, scraper, frontend = service_environments(
            root,
            settings,
            {'MODEL_API_KEY': 'leaked', 'TAVILY_API_KEY': 'leaked', 'HOME': '/tmp'},
            backend_port=8000,
            frontend_port=3000,
            health_port=8002,
            demo=True,
            token='shared-token',
            typesafe_keyfile=root / 'missing-typesafe-key',
        )
        self.assertEqual(backend['SCRAPER_HEALTH_URL'], 'http://127.0.0.1:8002')
        self.assertEqual(backend['MODEL_ID'], 'Qwen/Qwen3-test')
        self.assertEqual(backend['MODEL_PUBLISHER'], 'Qwen')
        self.assertEqual(backend['MODEL_KEY_CONFIGURED'], 'true')
        self.assertEqual(backend['SCRAPE_TOPICS_FILE'], '/tmp/topics.json')
        self.assertNotIn('MODEL_API_KEY', backend)
        self.assertNotIn('TAVILY_API_KEY', backend)
        self.assertNotIn('FIREHOSE_MGMT_KEY', backend)
        self.assertEqual(scraper['MODEL_API_KEY'], 'secret-model-key')
        self.assertEqual(scraper['TAVILY_API_KEY'], 'secret-tavily')
        self.assertEqual(scraper['SCRAPER_HEALTH_PORT'], '8002')
        self.assertEqual(scraper['BACKEND_INTERNAL_URL'], 'http://127.0.0.1:8000')
        self.assertNotIn('TYPESAFE_API_KEY', scraper)
        self.assertEqual(frontend['BACKEND_URL'], 'http://127.0.0.1:8000')
        self.assertNotIn('MODEL_API_KEY', frontend)
