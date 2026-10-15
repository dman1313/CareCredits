from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from backend.database.database import get_db
from models import Account, LoginSession
from security import password_hash, password_matches, digest, throttle, issue_session
from oauth import (
    authorize_url, configured as google_oauth, exchange_code,
    public_frontend_base, upsert_account, OAuthError
)
import secrets


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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


_DUMMY = password_hash("not-an-account-password")


def _session_cookie_kwargs(production_env: bool) -> dict:
    return {
        "httponly": True,
        "secure": production_env,
        "samesite": "lax",
        "max_age": 28800,
        "path": "/",
    }


def _oauth_state_cookie_kwargs(production_env: bool) -> dict:
    return {
        "httponly": True,
        "secure": production_env,
        "samesite": "lax",
        "max_age": 600,
        "path": "/",
    }


def _delete_session_cookie(response: Response, name: str, production_env: bool) -> None:
    response.delete_cookie(name, path="/", httponly=True, secure=production_env, samesite="lax")


def _profile(account: Account) -> dict:
    return {
        k: getattr(account, k)
        for k in ("id", "email", "name", "city", "state", "role", "bio", "public_enabled", "public_slug")
    }


@router.post("/register", status_code=201)
def register(body: Credentials, request: Request, db: Session = Depends(get_db)):
    import os
    if os.getenv("ALLOW_SIGNUP") != "true":
        raise HTTPException(403, "Registration is disabled.")

    def client_host(req: Request) -> str:
        return req.client.host if req.client and req.client.host else "unknown"

    throttle(db, "register:" + client_host(request), 10, 3600)
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
    import os
    def client_host(req: Request) -> str:
        return req.client.host if req.client and req.client.host else "unknown"

    def production_env() -> bool:
        return (os.getenv("APP_ENV") or "").strip().casefold() == "production"

    throttle(db, "login-ip:" + client_host(request), 30, 300)
    throttle(db, "login-email:" + body.email, 10, 300)

    account = db.query(Account).filter_by(email=body.email).first()
    valid = password_matches(body.password, account.password_hash if account else _DUMMY)
    if not account or not valid:
        raise HTTPException(401, "Email or password is incorrect.")

    token = issue_session(db, account, request.cookies.get("care_session"))
    response.set_cookie("care_session", token, **_session_cookie_kwargs(production_env()))
    _delete_session_cookie(response, "oauth_state", production_env())
    return _profile(account)


@router.get("/oauth/google")
def google_start(request: Request, response: Response):
    import os
    def production_env() -> bool:
        return (os.getenv("APP_ENV") or "").strip().casefold() == "production"

    state = secrets.token_urlsafe(24)
    try:
        url = authorize_url(state)
    except OAuthError as exc:
        from errors import envelope
        resp = envelope(exc.status_code, exc.detail, request)
        _delete_session_cookie(resp, "oauth_state", production_env())
        return resp

    dest = Response(status_code=302, headers={"location": url})
    dest.set_cookie("oauth_state", state, **_oauth_state_cookie_kwargs(production_env()))
    return dest


@router.get("/oauth/google/callback")
def google_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str = "",
    state: str = "",
    error: str = "",
):
    import os
    def client_host(req: Request) -> str:
        return req.client.host if req.client and req.client.host else "unknown"

    def production_env() -> bool:
        return (os.getenv("APP_ENV") or "").strip().casefold() == "production"

    expected = request.cookies.get("oauth_state", "")
    frontend = public_frontend_base()

    if error:
        dest = Response(status_code=302, headers={"location": frontend + "/live?oauth=denied"})
        _delete_session_cookie(dest, "oauth_state", production_env())
        return dest

    if not google_oauth():
        from errors import envelope
        resp = envelope(503, "Google sign-in is not configured.", request)
        _delete_session_cookie(resp, "oauth_state", production_env())
        return resp

    try:
        throttle(db, "login-ip:" + client_host(request), 30, 300)
    except HTTPException as exc:
        if exc.status_code == 429:
            dest = Response(status_code=302, headers={"location": frontend + "/live?oauth=failed"})
            _delete_session_cookie(dest, "oauth_state", production_env())
            return dest
        raise

    if not code or not state or not expected or not secrets.compare_digest(state, expected):
        dest = Response(status_code=302, headers={"location": frontend + "/live?oauth=failed"})
        _delete_session_cookie(dest, "oauth_state", production_env())
        return dest

    try:
        identity = exchange_code(code)
        account = upsert_account(db, identity, os.getenv("ALLOW_SIGNUP") == "true")
        token = issue_session(db, account, request.cookies.get("care_session"))
    except OAuthError as exc:
        if exc.status_code in (401, 403):
            dest = Response(status_code=302, headers={"location": frontend + "/live?oauth=failed"})
            _delete_session_cookie(dest, "oauth_state", production_env())
            return dest
        from errors import envelope
        resp = envelope(exc.status_code, exc.detail, request)
        _delete_session_cookie(resp, "oauth_state", production_env())
        return resp

    dest = Response(status_code=302, headers={"location": frontend + "/live"})
    dest.set_cookie("care_session", token, **_session_cookie_kwargs(production_env()))
    _delete_session_cookie(dest, "oauth_state", production_env())
    return dest


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    import os
    def production_env() -> bool:
        return (os.getenv("APP_ENV") or "").strip().casefold() == "production"

    db.query(LoginSession).filter_by(token_hash=digest(request.cookies.get("care_session", ""))).delete()
    db.commit()
    _delete_session_cookie(response, "care_session", production_env())
    _delete_session_cookie(response, "oauth_state", production_env())
    return {"ok": True}