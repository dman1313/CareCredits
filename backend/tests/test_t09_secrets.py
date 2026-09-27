"""T-09: secrets stay off the client; origins and unauthenticated user routes stay closed."""
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / 'frontend'


class SecretSurfaceTests(unittest.TestCase):
    def test_frontend_has_no_service_secrets(self):
        needles = (
            'TAVILY_API_KEY',
            'MODEL_API_KEY',
            'TYPESAFE_API_KEY',
            'SCRAPER_SERVICE_TOKEN',
            'POSTGRES_PASSWORD',
            'GOOGLE_CLIENT_SECRET',
        )
        hits = []
        for path in FRONTEND.rglob('*'):
            if not path.is_file() or any(part in path.parts for part in ('node_modules', '.next', 'dist')):
                continue
            if path.suffix.lower() not in {'.ts', '.tsx', '.js', '.jsx', '.json', '.env', '.md'}:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            for needle in needles:
                if needle in text:
                    hits.append(f'{path.relative_to(ROOT)}:{needle}')
        self.assertEqual(hits, [])

    def test_default_origins_are_local_only(self):
        default = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000')
        self.assertNotIn('*', default)
        self.assertTrue(all(item.startswith('http://localhost') or item.startswith('http://127.0.0.1') for item in default.split(',')))

    def test_built_frontend_assets_omit_service_secret_names(self):
        built = FRONTEND / '.next'
        if not built.exists():
            self.skipTest('No built frontend assets in this checkout')
        needles = ('TAVILY_API_KEY', 'MODEL_API_KEY', 'TYPESAFE_API_KEY', 'SCRAPER_SERVICE_TOKEN', 'POSTGRES_PASSWORD', 'GOOGLE_CLIENT_SECRET')
        hits = []
        for path in built.rglob('*'):
            if not path.is_file() or path.suffix.lower() not in {'.js', '.json', '.html', '.map'}:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            for needle in needles:
                if needle in text:
                    hits.append(f'{path.relative_to(ROOT)}:{needle}')
        self.assertEqual(hits, [])
