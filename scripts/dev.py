"""Run the three local services, optionally with explicit fictional fixtures."""
import argparse
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from dotenv import dotenv_values


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--demo',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    settings={k:v for k,v in dotenv_values(root/'.env').items() if v is not None}
    common={**os.environ,'NEXT_TELEMETRY_DISABLED':'1','PYTHONPATH':str(root)+os.pathsep+str(root/'backend')}
    # Scope provider and DB secrets explicitly to their owning process.
    for key in list(common):
        if key.startswith(('MODEL_','TAVILY_')) or key in ('DATABASE_URL','POSTGRES_PASSWORD','SCRAPER_SERVICE_TOKEN'):
            common.pop(key)
    token=settings.get('SCRAPER_SERVICE_TOKEN') or secrets.token_urlsafe(32)
    (root/'.data').mkdir(exist_ok=True)
    db_url=os.getenv('DATABASE_URL') or settings.get('DATABASE_URL') or 'sqlite:///'+str(root/'.data'/('demo.db' if args.demo else 'carecredits.db'))
    backend={**common,'DATABASE_URL':db_url,'APP_ENV':'development','DEMO_MODE':str(args.demo).lower(),'ALLOW_SIGNUP':'true' if args.demo else settings.get('ALLOW_SIGNUP','false'),'SCRAPER_SERVICE_TOKEN':token}
    scraper={**common,**{k:v for k,v in settings.items() if k.startswith(('MODEL_','TAVILY_'))},'SCRAPER_SERVICE_TOKEN':token,'BACKEND_INTERNAL_URL':'http://127.0.0.1:8000'}
    processes=[]
    try:
        for command,env,cwd in [([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port','8000'],backend,root),([sys.executable,'-m','scraper.worker'],scraper,root),(['npm','run','dev','--','--hostname','127.0.0.1'],common,root/'frontend')]:
            processes.append(subprocess.Popen(command,cwd=cwd,env=env,start_new_session=True))
        print('CareCredits: http://127.0.0.1:3000 — Ctrl+C stops all three services.',flush=True)
        while all(p.poll() is None for p in processes):time.sleep(1)
    except KeyboardInterrupt:pass
    finally:
        for p in processes:
            if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
        for p in processes:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL)


if __name__=='__main__':main()
