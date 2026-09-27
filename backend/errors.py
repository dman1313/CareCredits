"""Stable API error envelopes: {error:{code,message,request_id}}."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


CODES = {
    400: 'bad_request',
    401: 'unauthenticated',
    403: 'forbidden',
    404: 'not_found',
    409: 'conflict',
    422: 'invalid',
    429: 'throttled',
    502: 'upstream',
    503: 'unavailable',
}


def request_id(request: Request) -> str:
    return getattr(request.state, 'request_id', None) or uuid.uuid4().hex


def envelope(status_code: int, message: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            'error': {
                'code': CODES.get(status_code, 'error'),
                'message': message,
                'request_id': request_id(request),
            }
        },
        headers={'X-Request-Id': request_id(request)},
    )


def message_from_detail(detail) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, dict):
            loc = '.'.join(str(part) for part in first.get('loc', []) if part != 'body')
            text = str(first.get('msg') or 'Invalid request.')
            return f'{loc}: {text}' if loc else text
        return str(first)
    if isinstance(detail, dict):
        return str(detail.get('message') or detail.get('msg') or 'Request failed.')
    return 'Request failed.'


async def http_exception_handler(request: Request, exc: HTTPException):
    return envelope(exc.status_code, message_from_detail(exc.detail), request)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return envelope(422, message_from_detail(exc.errors()), request)
