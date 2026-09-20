"""Run with python -m scraper.worker; communicates with backend over scoped HTTP."""
import os
from pathlib import Path
import time
import httpx
from scraper.tavily import discover, ProviderError
from scraper.extraction import configuration, extract_training, ExtractionError


def run_job(job, heartbeat):
    warnings, candidates = [], []
    try:
        configuration()  # fail before spending Tavily credits when model setup is absent
        result = discover(job['query'], 5)
        warnings.extend(result['warnings'])
        for source in result['sources']:
            heartbeat()
            if not source.get('raw_content'):
                continue
            try:
                candidates.extend(extract_training(source))
            except ExtractionError as exc:
                warnings.append(str(exc))
        return {'lease_token':job['lease_token'], 'candidates':candidates, 'warnings':warnings, 'status':'partial' if warnings else 'succeeded', 'usage':{'tavily_credits':None, 'model_tokens':None}}
    except (ProviderError, ExtractionError) as exc:
        return {'lease_token':job['lease_token'], 'candidates':[], 'warnings':[str(exc)], 'status':'failed', 'usage':{}}


def main():
    base = os.getenv('BACKEND_INTERNAL_URL','http://127.0.0.1:8000').rstrip('/')
    token = os.getenv('SCRAPER_SERVICE_TOKEN','')
    if not token:
        raise SystemExit('Set SCRAPER_SERVICE_TOKEN before starting the scraper.')
    with httpx.Client(base_url=base, headers={'Authorization':'Bearer '+token}, timeout=20) as client:
        while True:
            Path('/tmp/carecredits-worker').touch()
            try:
                response=client.post('/internal/v1/jobs/claim')
                response.raise_for_status()
                if response.status_code==204:
                    time.sleep(3)
                    continue
                job=response.json()
                started=time.monotonic()
                def heartbeat():
                    if time.monotonic()-started>270:
                        raise ExtractionError('Job deadline reached; retry explicitly if needed.')
                    client.post('/internal/v1/jobs/'+job['id']+'/heartbeat',json={'lease_token':job['lease_token']}).raise_for_status()
                # Each provider call is bounded below the 120-second lease.
                payload=run_job(job,heartbeat)
                client.post('/internal/v1/jobs/'+job['id']+'/complete',json=payload).raise_for_status()
                print('Ingestion job '+job['id']+': '+payload['status'],flush=True)
            except (httpx.HTTPError, ValueError):
                # Ambiguous paid work is never automatically replayed; backend expires its lease.
                print('Backend request unavailable; job lease will determine recovery.',flush=True)
                time.sleep(5)


if __name__=='__main__':
    main()
