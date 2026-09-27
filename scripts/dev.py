"""Run the three local services, optionally with explicit fictional fixtures."""
import argparse
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
from dotenv import dotenv_values


def free_port(preferred):
    preferred = int(preferred)
    for port in (preferred, *range(preferred + 1, preferred + 20)):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                continue
        return port
    raise RuntimeError('No free local port near ' + str(preferred))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--backend-port', type=int, default=int(os.getenv('BACKEND_PORT') or 8000))
    parser.add_argument('--frontend-port', type=int, default=int(os.getenv('FRONTEND_PORT') or 3000))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    settings = {k: v for k, v in dotenv_values(root / '.env').items() if v is not None}
    backend_port = free_port(args.backend_port)
    frontend_port = free_port(args.frontend_port)
    frontend = 'http://127.0.0.1:' + str(frontend_port)
    api = 'http://127.0.0.1:' + str(backend_port)
    common = {**os.environ, 'NEXT_TELEMETRY_DISABLED': '1', 'PYTHONPATH': str(root) + os.pathsep + str(root / 'backend')}
    # Scope provider and DB secrets explicitly to their owning process.
    for key in list(common):
        if key.startswith(('MODEL_', 'TAVILY_', 'TYPESAFE_', 'JEV_', 'DAILY_', 'SCRAPE_', 'FIREHOSE_', 'GOOGLE_')) or key in ('DATABASE_URL', 'POSTGRES_PASSWORD', 'SCRAPER_SERVICE_TOKEN'):
            common.pop(key)
    token = settings.get('SCRAPER_SERVICE_TOKEN') or secrets.token_urlsafe(32)
    (root / '.data').mkdir(exist_ok=True)
    db_url = os.getenv('DATABASE_URL') or settings.get('DATABASE_URL') or 'sqlite:///' + str(root / '.data' / ('demo.db' if args.demo else 'carecredits.db'))
    backend = {
        **common,
        'DATABASE_URL': db_url,
        'APP_ENV': 'development',
        'DEMO_MODE': str(args.demo).lower(),
        'ALLOW_SIGNUP': 'true' if args.demo else settings.get('ALLOW_SIGNUP', 'false'),
        'SCRAPER_SERVICE_TOKEN': token,
        'DAILY_SCRAPE_ENABLED': settings.get('DAILY_SCRAPE_ENABLED', 'true'),
        'PUBLIC_API_BASE': api,
        'PUBLIC_FRONTEND_BASE': frontend,
        'ALLOWED_ORIGINS': 'http://localhost:' + str(frontend_port) + ',' + frontend,
    }
    for key in ('TYPESAFE_API_KEY', 'JEV_CONFIDENCE_FLOOR', 'DAILY_SCRAPE_JOB_CEILING', 'SCRAPE_TOPICS_FILE', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI'):
        if settings.get(key):
            backend[key] = settings[key]
    if not (backend.get('TYPESAFE_API_KEY') or '').strip():
        keyfile = Path.home() / '.typesafe' / 'key'
        try:
            if keyfile.is_file():
                file_key = keyfile.read_text().strip()
                if file_key:
                    backend['TYPESAFE_API_KEY'] = file_key
        except OSError:
            pass
    scraper = {
        **common,
        **{k: v for k, v in settings.items() if k.startswith(('MODEL_', 'TAVILY_', 'FIREHOSE_'))},
        'SCRAPER_SERVICE_TOKEN': token,
        'BACKEND_INTERNAL_URL': api,
    }
    frontend_env = {**common, 'BACKEND_URL': api}
    processes = []
    try:
        for command, env, cwd in [
            ([sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(backend_port)], backend, root),
            ([sys.executable, '-m', 'scraper.worker'], scraper, root),
            (['npm', 'run', 'dev', '--', '--hostname', '127.0.0.1', '--port', str(frontend_port)], frontend_env, root / 'frontend'),
        ]:
            processes.append(subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True))
        print('CareCredits: ' + frontend + ' — API ' + api + ' — Ctrl+C stops all three services.', flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in processes:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)


if __name__ == '__main__':
    main()
