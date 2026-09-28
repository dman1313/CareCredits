"""Report DEMO-01 readiness without printing secrets or spending credits.

Run from the repository root with the project virtualenv:

    .venv/bin/python scripts/demo_readiness.py

Exit codes: 0 = live DEMO-01 prerequisites present; 1 = fixture-only / blocked.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'backend')]

from dotenv import load_dotenv  # noqa: E402
from shared.model_defaults import PROVISIONAL_MODEL  # noqa: E402

load_dotenv(root / '.env')


def present(name: str) -> bool:
    current = (os.getenv(name) or '').strip()
    if current:
        return True
    if name in PROVISIONAL_MODEL:
        return bool(PROVISIONAL_MODEL[name])
    return False


def readiness_checks():
    return [
        ('TAVILY_API_KEY', present('TAVILY_API_KEY')),
        ('MODEL_API_KEY', present('MODEL_API_KEY')),
        ('MODEL_ID', present('MODEL_ID')),
        ('MODEL_WEIGHTS_URL', present('MODEL_WEIGHTS_URL')),
        ('MODEL_LICENSE_URL', present('MODEL_LICENSE_URL')),
        ('MODEL_OPEN_WEIGHT_CONFIRMED', (os.getenv('MODEL_OPEN_WEIGHT_CONFIRMED') or '') == 'true'),
        ('MODEL_MAX_INPUT_CHARS', present('MODEL_MAX_INPUT_CHARS')),
        ('MODEL_MAX_OUTPUT_TOKENS', present('MODEL_MAX_OUTPUT_TOKENS')),
        ('SCRAPER_SERVICE_TOKEN', present('SCRAPER_SERVICE_TOKEN')),
    ]


def live_ready() -> bool:
    return all(ok for _, ok in readiness_checks())


def main() -> int:
    checks = readiness_checks()
    # Match scraper/worker.py: unset URL defaults to local backend.
    backend_url = (os.getenv('BACKEND_INTERNAL_URL') or 'http://127.0.0.1:8000').strip()
    print('CareCredits DEMO-01 readiness (no secrets printed, no API calls):')
    for label, ok in checks:
        print(f'  {"OK " if ok else "NO "} {label}')
    print(f'  OK  BACKEND_INTERNAL_URL (effective: {backend_url})')

    fixture = root / 'backend' / 'seed_demo.py'
    live_ui = root / 'frontend' / 'app' / 'live' / 'page.tsx'
    print(f'  {"OK " if fixture.exists() else "NO "} fixture seed module')
    print(f'  {"OK " if live_ui.exists() else "NO "} /live demo shell')

    live_ready_now = live_ready()
    if live_ready_now:
        print('Live DEMO-01 prerequisites look present. Set T10_LIVE=1 and run backend.tests.test_t10_live to spend one bounded Tavily+model call and record redacted evidence.')
        return 0

    missing = [label for label, ok in checks if not ok]
    print('Live DEMO-01 remains owner-blocked until these are set via scripts/setup_integrations.py:')
    for label in missing:
        print(f'  - {label}')
    print('Offline fixture path (DEMO_MODE seed + /live FIXTURE queue) can still demonstrate review and personal tracking without spending credits.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
