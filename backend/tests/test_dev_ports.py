import socket
import tempfile
import unittest
from pathlib import Path

from scripts.dev import free_port, is_live_body, probe_live, service_environments, wait_for_live
from shared.model_defaults import apply_provisional_model, using_provisional


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
        self.assertEqual(backend['DAILY_SCRAPE_ENABLED'], 'false')
        self.assertNotIn('MODEL_API_KEY', backend)
        self.assertNotIn('TAVILY_API_KEY', backend)
        self.assertNotIn('FIREHOSE_MGMT_KEY', backend)
        self.assertEqual(scraper['MODEL_API_KEY'], 'secret-model-key')
        self.assertEqual(scraper['TAVILY_API_KEY'], 'secret-tavily')
        self.assertEqual(scraper['SCRAPER_HEALTH_PORT'], '8002')
        self.assertEqual(scraper['BACKEND_INTERNAL_URL'], 'http://127.0.0.1:8000')
        self.assertNotIn('TYPESAFE_API_KEY', scraper)
        self.assertEqual(frontend['BACKEND_URL'], 'http://127.0.0.1:8000')
        self.assertEqual(frontend['NEXT_DIST_DIR'], str(root / 'frontend' / '.data' / 'next-dev-3000'))
        self.assertNotIn('MODEL_API_KEY', frontend)
        filled = apply_provisional_model({'MODEL_ID': '', 'TAVILY_API_KEY': 'keep'})
        self.assertEqual(filled['MODEL_ID'], 'Qwen/Qwen3-30B-A3B-Instruct-2507')
        self.assertEqual(filled['TAVILY_API_KEY'], 'keep')
        self.assertNotIn('MODEL_API_KEY', filled)
        self.assertTrue(using_provisional('MODEL_ID', {'MODEL_ID': ''}))
        self.assertFalse(using_provisional('MODEL_ID', {'MODEL_ID': 'Qwen/owner-chosen'}))
        # OPEN-03 samples filled for the scraper must not land on the backend process env.
        filled = apply_provisional_model({})
        backend_empty, scraper_filled, _fe = service_environments(
            root,
            filled,
            {'HOME': '/tmp'},
            backend_port=8010,
            frontend_port=3010,
            health_port=8012,
            demo=True,
            token='shared-token',
            typesafe_keyfile=root / 'missing-typesafe-key',
            owner_settings={},
        )
        self.assertNotIn('MODEL_ID', backend_empty)
        self.assertNotIn('MODEL_PUBLISHER', backend_empty)
        self.assertNotIn('MODEL_HOST', backend_empty)
        self.assertNotIn('MODEL_WEIGHTS_URL', backend_empty)
        self.assertNotIn('MODEL_LICENSE_URL', backend_empty)
        self.assertNotIn('MODEL_MAX_INPUT_CHARS', backend_empty)
        self.assertNotIn('MODEL_MAX_OUTPUT_TOKENS', backend_empty)
        self.assertEqual(scraper_filled['MODEL_ID'], 'Qwen/Qwen3-30B-A3B-Instruct-2507')

    def test_wait_for_live_requires_status_live(self):
        self.assertTrue(is_live_body({'status': 'live'}))
        self.assertFalse(is_live_body({'status': 'ok'}))
        self.assertFalse(is_live_body({'status': 'ready'}))
        from scraper.health import start

        server = start(port=18032)
        try:
            ready, missing = wait_for_live(
                {
                    'scraper': 'http://127.0.0.1:18032/health/live',
                    'missing': 'http://127.0.0.1:9/health/live',
                },
                timeout=2,
                sleep=0.1,
            )
            self.assertTrue(probe_live('http://127.0.0.1:18032/health/live'))
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(ready, ['scraper'])
        self.assertEqual(missing, ['missing'])

