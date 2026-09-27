"""Sanitized request/job logs. Never log secrets, notes, or identity tokens."""
from __future__ import annotations

import logging

log = logging.getLogger('carecredits')


def setup():
    if log.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def request_line(request_id: str, method: str, path: str, status: int, duration_ms: int):
    log.info(
        'request id=%s method=%s path=%s status=%s duration_ms=%s',
        request_id,
        method,
        path,
        status,
        duration_ms,
    )


def failure_line(request_id: str, status: int, message: str):
    log.warning('failure id=%s status=%s message=%s', request_id, status, str(message)[:200])


def job_line(job_id: str, status: str, candidate_count: int, source_count: int, usage, warning_count: int):
    usage = usage if isinstance(usage, dict) else {}
    log.info(
        'job id=%s status=%s candidates=%s sources=%s tavily_credits=%s model_tokens=%s warnings=%s',
        job_id,
        status,
        candidate_count,
        source_count,
        usage.get('tavily_credits'),
        usage.get('model_tokens'),
        warning_count,
    )
