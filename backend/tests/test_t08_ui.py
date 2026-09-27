"""T-08 source-level checks for keyboard, loading, empty, error, and retry UI."""
import unittest
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / 'frontend'


class PortalAccessibilityTests(unittest.TestCase):
    def _read(self, relative):
        return (FRONTEND / relative).read_text(encoding='utf-8')

    def test_sign_in_search_and_detail_are_labelled(self):
        login = self._read('components/LoginForm.tsx')
        page = self._read('app/page.tsx')
        live = self._read('app/live/page.tsx')
        public = self._read('app/p/[slug]/page.tsx')
        discover = self._read('components/DiscoverPanel.tsx')
        detail = self._read('components/TrainingDetail.tsx')
        css = self._read('app/globals.css')
        self.assertIn('Skip to sign in', login)
        self.assertIn('autoComplete="username"', login)
        self.assertIn('role="alert"', login)
        self.assertIn('aria-busy={busy}', login)
        self.assertIn('Skip to content', page)
        self.assertIn('retryRef.current()', page)
        self.assertIn('Retry', page)
        self.assertIn('Opening your workspace', page)
        self.assertIn('Skip to sign in', live)
        self.assertIn('autoComplete="username"', live)
        self.assertIn('Retry', public)
        self.assertIn('aria-label="Search training"', discover)
        self.assertIn('title={tab === \'My learning\' ? \'Your learning story starts here\'', discover)
        ingest = self._read('components/IngestionPanel.tsx')
        self.assertIn('schema ${candidate.schema_version}', ingest)
        self.assertIn('Corrected title', ingest)
        self.assertIn('Title evidence excerpt', ingest)
        self.assertIn('role="dialog"', detail)
        self.assertIn('aria-modal="true"', detail)
        self.assertIn('focus-visible', css)
        self.assertIn('@media(max-width:560px)', css)
        self.assertNotIn('Successfully ingested', page)
        self.assertNotIn('fake success', page.lower())
        proxy = self._read('app/api/v1/[...path]/route.ts')
        self.assertIn('BACKEND_URL', proxy)
        self.assertIn('force-dynamic', proxy)
