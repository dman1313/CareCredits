import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.services.auth_service import AuthService
from backend.services.oauth_service import (
    authorize_url,
    configured as google_oauth_configured,
    exchange_code,
    public_frontend_base,
    OAuthError,
)
from security import password_hash, password_matches, throttle


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# === Schemas ===
class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default="Doctor", min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def email_check(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1] or any(c.isspace() for c in value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("name")
    @classmethod
    def name_check(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if len(cleaned) < 2 or len(cleaned) > 100:
            raise ValueError("Enter a display name of 2–100 characters.")
        return cleaned


# === Helpers ===
_DUMMY = password_hash("not-an-account-password")


def _client_host(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def _production_env() -> bool:
    return (os.getenv("APP_ENV") or "").strip().casefold() == "production"


def _session_cookie_kwargs(secure: bool) -> dict:
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": 28800,
        "path": "/",
    }


def _oauth_state_cookie_kwargs(secure: bool) -> dict:
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": 600,
        "path": "/",
    }


def _delete_session_cookie(response: Response, name: str, secure: bool) -> None:
    response.delete_cookie(name, path="/", httponly=True, secure=secure, samesite="lax")


def _profile(account) -> dict:
    """Serialize account to profile dict. Works with ORM object or service result."""
    return {
        k: getattr(account, k)
        for k in ("id", "email", "name", "city", "state", "role", "bio", "public_enabled", "public_slug")
    }


# === Endpoints ===
@router.post("/register", status_code=201)
def register(body: Credentials, request: Request, db: Session = Depends(get_db)):
    if os.getenv("ALLOW_SIGNUP") != "true":
        raise HTTPException(403, "Registration is disabled.")

    throttle(db, "register:" + _client_host(request), 10, 3600)

    from models.account import Account
    account = Account(email=body.email, name=body.name, password_hash=password_hash(body.password))
    db.add(account)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "This address cannot be registered.")
    return {"message": "Account created. Please sign in."}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(db, "login-ip:" + _client_host(request), 30, 300)
    throttle(db, "login-email:" + body.email, 10, 300)

    from models.account import Account
    account = db.query(Account).filter_by(email=body.email).first()
    valid = password_matches(body.password, account.password_hash if account else _DUMMY)
    if not account or not valid:
        raise HTTPException(401, "Email or password is incorrect.")

    # Delegate session creation to service
    auth_service = AuthService(db)
    token = auth_service.issue_session(account, request.cookies.get("care_session"))

    secure = _production_env()
    response.set_cookie("care_session", token, **_session_cookie_kwargs(secure))
    _delete_session_cookie(response, "oauth_state", secure)
    return _profile(account)


@router.get("/oauth/google")
def google_start(request: Request, response: Response):
    state = secrets.token_urlsafe(24)
    try:
        url = authorize_url(state)
    except OAuthError as exc:
        from errors import envelope
        resp = envelope(exc.status_code, exc.detail, request)
        _delete_session_cookie(resp, "oauth_state", _production_env())
        return resp

    dest = Response(status_code=302, headers={"location": url})
    dest.set_cookie("oauth_state", state, **_oauth_state_cookie_kwargs(_production_env()))
    return dest


@router.get("/oauth/google/callback")
def google_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str = "",
    state: str = "",
    error: str = "",
):
    expected = request.cookies.get("oauth_state", "")
    frontend = public_frontend_base()
    secure = _production_env()

    # Handle explicit denial from Google
    if error:
        dest = Response(status_code=302, headers={"location": frontend + "/live?oauth=denied"})
        _delete_session_cookie(dest, "oauth_state", secure)
        return dest

    # Check if OAuth is configured at all
    if not google_oauth_configured():
        from errors import envelope
        resp = envelope(503, "Google sign-in is not configured.", request)
        _delete_session_cookie(resp, "oauth_state", secure)
        return resp

    # Throttle callback attempts
    try:
        throttle(db, "login-ip:" + _client_host(request), 30, 300)
    except HTTPException as exc:
        if exc.status_code == 429:
            dest = Response(status_code=302, headers={"location": frontend + "/live?oauth=failed"})
            _delete_session_cookie(dest, "oauth_state", secure)
            return dest
        raise

    # Validate CSRF state
    if not code or not state or not expected or not secrets.compare_digest(state, expected):
        dest = Response(status_code=302, headers={"location": frontend + "/live?oauth=failed"})
        _delete_session_cookie(dest, "oauth_state", secure)
        return dest

    # Exchange code → identity → account → session
    try:
        identity = exchange_code(code)
        auth_service = AuthService(db)
        account = auth_service.upsert_google_account(identity, os.getenv("ALLOW_SIGNUP") == "true")
        token = auth_service.issue_session(account, request.cookies.get("care_session"))
    except OAuthError as exc:
        if exc.status_code in (401, 403):
            dest = Response(status_code=302, headers={"location": frontend + "/live?oauth=failed"})
            _delete_session_cookie(dest, "oauth_state", secure)
            return dest
        from errors import envelope
        resp = envelope(exc.status_code, exc.detail, request)
        _delete_session_cookie(resp, "oauth_state", secure)
        return resp

    dest = Response(status_code=302, headers={"location": frontend + "/live"})
    dest.set_cookie("care_session", token, **_session_cookie_kwargs(secure))
    _delete_session_cookie(dest, "oauth_state", secure)
    return dest


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    from models.session import LoginSession
    from security import digest

    db.query(LoginSession).filter_by(token_hash=digest(request.cookies.get("care_session", ""))).delete()
    db.commit()

    secure = _production_env()
    _delete_session_cookie(response, "care_session", secure)
    _delete_session_cookie(response, "oauth_state", secure)
    return {"ok": True}

@router.get("/config", tags=["auth-config"])
def auth_config():
    """
    Public configuration for frontend auth flows.
    No authentication required; safe to call before login.
    """
    return {
        "demo": os.getenv("DEMO_MODE") == "true",
        "signup_enabled": os.getenv("ALLOW_SIGNUP") == "true",
        "oauth_google": google_oauth_configured(), 
    }