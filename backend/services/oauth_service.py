import os
from urllib.parse import urlencode
import httpx

GOOGLE_AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
GOOGLE_ISSUERS = {'https://accounts.google.com', 'accounts.google.com'}


class OAuthError(Exception):
    def __init__(self, detail: str, status_code: int = 401):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def configured() -> bool:
    return bool((os.getenv('GOOGLE_CLIENT_ID') or '').strip() and 
                (os.getenv('GOOGLE_CLIENT_SECRET') or '').strip())


def public_frontend_base() -> str:
    return (os.getenv('PUBLIC_FRONTEND_BASE') or '').strip().rstrip('/') or 'http://127.0.0.1:3000'


def redirect_uri() -> str:
    explicit = (os.getenv('GOOGLE_REDIRECT_URI') or '').strip()
    if explicit:
        return explicit
    return public_frontend_base() + '/api/v1/auth/oauth/google/callback'


def authorize_url(state: str) -> str:
    if not configured():
        raise OAuthError('Google sign-in is not configured.', 503)
    return GOOGLE_AUTH + '?' + urlencode({
        'client_id': os.environ['GOOGLE_CLIENT_ID'].strip(),
        'redirect_uri': redirect_uri(),
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    })


def exchange_code(code: str, client: httpx.Client | None = None) -> dict:
    """Exchanges authorization code for verified Google identity claims."""
    if not configured():
        raise OAuthError('Google sign-in is not configured.', 503)
    
    owns = client is None
    client = client or httpx.Client(timeout=20.0)
    try:
        response = client.post(
            GOOGLE_TOKEN,
            data={
                'code': code,
                'client_id': os.environ['GOOGLE_CLIENT_ID'].strip(),
                'client_secret': os.environ['GOOGLE_CLIENT_SECRET'].strip(),
                'redirect_uri': redirect_uri(),
                'grant_type': 'authorization_code',
            },
        )
        if response.status_code >= 400:
            raise OAuthError('Google rejected the sign-in request.', 401)
            
        payload = response.json()
        token = payload.get('id_token')
        if not token:
            raise OAuthError('Google did not return an identity token.', 401)
            
        info = client.get('https://oauth2.googleapis.com/tokeninfo', params={'id_token': token})
        if info.status_code >= 400:
            raise OAuthError('Google identity token could not be verified.', 401)
            
        claims = info.json()
    finally:
        if owns:
            client.close()

    # Validate claims
    if claims.get('aud') != os.environ['GOOGLE_CLIENT_ID'].strip():
        raise OAuthError('Google identity token audience did not match.', 401)
    if claims.get('iss') not in GOOGLE_ISSUERS:
        raise OAuthError('Google identity token issuer is not trusted.', 401)
        
    email = (claims.get('email') or '').strip().lower()
    if not email or claims.get('email_verified') in ('false', False):
        raise OAuthError('Google account email is missing or unverified.', 401)

    return {
        'email': email,
        'name': (claims.get('name') or email.split('@')[0])[:100],
        'subject': str(claims.get('sub') or '')[:200],
    }