import csv
import io
import json
import math
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from email.message import EmailMessage
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, or_, update, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from database import Base, engine, get_db, SessionLocal
from models import (
    Account, LoginSession, Course, Record, RecordHistory, Audit, SchemaVersion,
    DigestPreference, AffiliationCertificate, SCHEMA_VERSION, FILTER_FIELDS,
)
from security import current_user, operator, password_hash, password_matches, digest, throttle
from shared.contracts import Training, public_web_url, validate_evidence
from shared.model_defaults import env_or_provisional, using_provisional
from observe import setup as setup_logs, request_line, log as app_log, normalize_job_usage
from digest import ensure_preference, preference_json, progress_snapshot, run_due_digests
from certificates import issue_certificate, certificate_json, render_html as certificate_html, render_pdf as certificate_pdf
from suggestions import suggestions_for
from errors import envelope, http_exception_handler, validation_exception_handler, request_id
from oauth import (
    authorize_url, configured as google_oauth, exchange_code, issue_session,
    public_frontend_base, upsert_account, OAuthError,
)

from routers.internal.ingestion import router as ingestion_router

# === Admin/Public Routers (te refactoren na hackathon) ===
# Voor nu blijven deze hier om main.py werkend te houden tijdens cleanup
# TODO: Verplaats naar routers/admin.py, routers/auth.py, etc.


def today():
    return datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()


def client_host(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return 'unknown'


def production_env() -> bool:
    return (os.getenv('APP_ENV') or '').strip().casefold() == 'production'


def initialize():
    if os.getenv('DEMO_MODE') == 'true' and production_env():
        raise RuntimeError('Demo mode cannot run in production')
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        migrate_schema(db)
        if os.getenv('DEMO_MODE') == 'true':
            from seed_demo import seed
            seed(db)


def migrate_schema(db):
    versions = db.query(SchemaVersion).all()
    current = max((v.version for v in versions), default=0)
    if current >= SCHEMA_VERSION:
        return
    # ... bestaande migratie-logica blijft hier ...
    # (Te verplaatsen naar db/migrations.py na hackathon)
    db.add(SchemaVersion(version=SCHEMA_VERSION))
    db.commit()


@asynccontextmanager
async def lifespan(app):
    initialize()
    import asyncio
    stop = asyncio.Event()
    tasks = []

    async def digest_loop():
        while not stop.is_set():
            try:
                with SessionLocal() as db:
                    run_due_digests(db)
            except Exception as exc:
                app_log.warning('digest_loop failed message=%s', str(exc)[:200])
            try:
                await asyncio.wait_for(stop.wait(), timeout=3600)
            except asyncio.TimeoutError:
                continue

    async def retention_loop():
        while not stop.is_set():
            try:
                with SessionLocal() as db:
                    purge_expired_source_text(db)
            except Exception as exc:
                app_log.warning('retention_loop failed message=%s', str(exc)[:200])
            try:
                await asyncio.wait_for(stop.wait(), timeout=86400)
            except asyncio.TimeoutError:
                continue

    if os.getenv('DIGEST_ENABLED', 'true').lower() == 'true':
        tasks.append(asyncio.create_task(digest_loop()))
    tasks.append(asyncio.create_task(retention_loop()))
    yield
    stop.set()
    for task in tasks:
        try:
            await asyncio.wait_for(task, timeout=2)
        except Exception:
            task.cancel()


app = FastAPI(title='CareCredits', version='0.5.0', lifespan=lifespan)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return envelope(500, 'Request failed.', request)


setup_logs()

DEFAULT_ALLOWED_ORIGINS = 'http://localhost:3000,http://127.0.0.1:3000'


def normalize_origin(value: str | None) -> str:
    cleaned = (value or '').strip().rstrip('/')
    if not cleaned or cleaned.casefold() == 'null':
        return ''
    return cleaned.casefold()


def origin_allowed(origin: str | None, allowed: list[str] | set[str] | tuple[str, ...]) -> bool:
    normalized = normalize_origin(origin)
    if not normalized:
        return False
    allowlist = {normalize_origin(item) for item in allowed if normalize_origin(item)}
    return normalized in allowlist


@app.middleware('http')
async def request_boundary(request: Request, call_next):
    started = time.perf_counter()
    request.state.request_id = secrets.token_hex(8)
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not request.url.path.startswith('/internal/'):
        origins = [item for item in os.getenv('ALLOWED_ORIGINS', DEFAULT_ALLOWED_ORIGINS).split(',') if item.strip()]
        if (request.headers.get('x-care-client') or '').strip() != '1' or not origin_allowed(
            request.headers.get('origin'), origins
        ):
            return envelope(403, 'Request origin not allowed.', request)
    try:
        result = await call_next(request)
    except Exception:
        return envelope(500, 'Request failed.', request)
    result.headers['Cache-Control'] = 'no-store'
    result.headers['X-Content-Type-Options'] = 'nosniff'
    rid = request_id(request)
    result.headers['X-Request-Id'] = rid
    duration_ms = int((time.perf_counter() - started) * 1000)
    request_line(rid, request.method, request.url.path, result.status_code, duration_ms)
    return result


# === Register Internal Router ===
app.include_router(ingestion_router)


# === Health & Config ===
@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/health/live')
def health_live():
    return {'status': 'live'}


@app.get('/health/ready')
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
    except Exception:
        raise HTTPException(503, 'Database is unavailable.')
    return {'status': 'ready', 'database': 'ready'}


@app.get('/api/v1/config')
def config():
    return {
        'demo': os.getenv('DEMO_MODE') == 'true',
        'signup_enabled': os.getenv('ALLOW_SIGNUP') == 'true',
        'oauth_google': google_oauth(),
    }


# === Auth Routes (TODO: verplaats naar routers/auth.py) ===
class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default='Doctor', min_length=1, max_length=120)

    @field_validator('email')
    @classmethod
    def email_check(cls, value):
        value = value.strip().lower()
        if '@' not in value or '.' not in value.split('@')[-1] or any(c.isspace() for c in value):
            raise ValueError('Enter a valid email address')
        return value

    @field_validator('name')
    @classmethod
    def name_check(cls, value):
        cleaned = (value or '').strip()
        if len(cleaned) < 2 or len(cleaned) > 100:
            raise ValueError('Enter a display name of 2–100 characters.')
        return cleaned


_DUMMY = password_hash('not-an-account-password')


def _session_cookie_kwargs():
    return {
        'httponly': True,
        'secure': production_env(),
        'samesite': 'lax',
        'max_age': 28800,
        'path': '/',
    }


def _oauth_state_cookie_kwargs():
    return {
        'httponly': True,
        'secure': production_env(),
        'samesite': 'lax',
        'max_age': 600,
        'path': '/',
    }


def _delete_session_cookie(response: Response, name: str):
    response.delete_cookie(name, path='/', httponly=True, secure=production_env(), samesite='lax')


@app.post('/api/v1/auth/register', status_code=201)
def register(body: Credentials, request: Request, db: Session = Depends(get_db)):
    if os.getenv('ALLOW_SIGNUP') != 'true':
        raise HTTPException(403, 'Registration is disabled.')
    throttle(db, 'register:' + client_host(request), 10, 3600)
    account = Account(email=body.email, name=body.name, password_hash=password_hash(body.password))
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'This address cannot be registered.')
    return {'message': 'Account created. Please sign in.'}


@app.post('/api/v1/auth/login')
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(db, 'login-ip:' + client_host(request), 30, 300)
    throttle(db, 'login-email:' + body.email, 10, 300)
    account = db.query(Account).filter_by(email=body.email).first()
    valid = password_matches(body.password, account.password_hash if account else _DUMMY)
    if not account or not valid:
        raise HTTPException(401, 'Email or password is incorrect.')
    token = issue_session(db, account, request.cookies.get('care_session'))
    response.set_cookie('care_session', token, **_session_cookie_kwargs())
    _delete_session_cookie(response, 'oauth_state')
    return {k: getattr(account, k) for k in ('id', 'email', 'name', 'city', 'state', 'role', 'bio', 'public_enabled', 'public_slug')}


@app.get('/api/v1/auth/oauth/google')
def google_start(request: Request, response: Response):
    state = secrets.token_urlsafe(24)
    try:
        url = authorize_url(state)
    except OAuthError as exc:
        return _oauth_callback_error(request, exc.status_code, exc.detail)
    dest = RedirectResponse(url, status_code=302)
    dest.set_cookie('oauth_state', state, **_oauth_state_cookie_kwargs())
    return dest


def _oauth_callback_error(request: Request, status_code: int, message: str):
    response = envelope(status_code, message, request)
    _delete_session_cookie(response, 'oauth_state')
    return response


@app.get('/api/v1/auth/oauth/google/callback')
def google_callback(request: Request, db: Session = Depends(get_db), code: str = '', state: str = '', error: str = ''):
    expected = request.cookies.get('oauth_state', '')
    frontend = public_frontend_base()
    if error:
        dest = RedirectResponse(frontend + '/live?oauth=denied', status_code=302)
        _delete_session_cookie(dest, 'oauth_state')
        return dest
    if not google_oauth():
        return _oauth_callback_error(request, 503, 'Google sign-in is not configured.')
    try:
        throttle(db, 'login-ip:' + client_host(request), 30, 300)
    except HTTPException as exc:
        if exc.status_code == 429:
            dest = RedirectResponse(frontend + '/live?oauth=failed', status_code=302)
            _delete_session_cookie(dest, 'oauth_state')
            return dest
        raise
    if not code or not state or not expected or not secrets.compare_digest(state, expected):
        dest = RedirectResponse(frontend + '/live?oauth=failed', status_code=302)
        _delete_session_cookie(dest, 'oauth_state')
        return dest
    try:
        identity = exchange_code(code)
        account = upsert_account(db, identity, os.getenv('ALLOW_SIGNUP') == 'true')
        token = issue_session(db, account, request.cookies.get('care_session'))
    except OAuthError as exc:
        if exc.status_code in (401, 403):
            dest = RedirectResponse(frontend + '/live?oauth=failed', status_code=302)
            _delete_session_cookie(dest, 'oauth_state')
            return dest
        return _oauth_callback_error(request, exc.status_code, exc.detail)
    dest = RedirectResponse(frontend + '/live', status_code=302)
    dest.set_cookie('care_session', token, **_session_cookie_kwargs())
    _delete_session_cookie(dest, 'oauth_state')
    return dest


@app.post('/api/v1/auth/logout')
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    db.query(LoginSession).filter_by(token_hash=digest(request.cookies.get('care_session', ''))).delete()
    db.commit()
    _delete_session_cookie(response, 'care_session')
    _delete_session_cookie(response, 'oauth_state')
    return {'ok': True}


# === User Routes (TODO: verplaats naar routers/me.py) ===
class ProfileChange(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    city: str = Field(max_length=100)
    state: str = Field(default='', max_length=100)
    bio: str = Field(max_length=1000)
    public_enabled: bool
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @field_validator('name')
    @classmethod
    def name_check(cls, value):
        cleaned = (value or '').strip()
        if len(cleaned) < 2 or len(cleaned) > 100:
            raise ValueError('Enter a display name of 2–100 characters.')
        return cleaned

    @field_validator('city', 'state', 'bio')
    @classmethod
    def trim_text(cls, value):
        return (value or '').strip() if isinstance(value, str) else value

    @field_validator('latitude', 'longitude', mode='before')
    @classmethod
    def coordinates_reject_bool(cls, value):
        if isinstance(value, bool):
            raise ValueError('Coordinates must be numbers.')
        return value

    @model_validator(mode='after')
    def coordinates_together(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Latitude and longitude must be supplied together.')
        return self


def profile(account):
    return {k: getattr(account, k) for k in ('id', 'email', 'name', 'city', 'state', 'latitude', 'longitude', 'location_consent_at', 'created_at', 'role', 'bio', 'public_enabled', 'public_slug')}


@app.get('/api/v1/me')
def me(user=Depends(current_user)):
    return profile(user)


@app.patch('/api/v1/me')
def change_profile(body: ProfileChange, user=Depends(current_user), db: Session = Depends(get_db)):
    values = body.model_dump()
    user.latitude = values.pop('latitude')
    user.longitude = values.pop('longitude')
    user.location_consent_at = time.time() if user.latitude is not None else None
    for k, v in values.items():
        setattr(user, k, v)
    db.add(Audit(account_id=user.id, action='profile_changed', entity_id=user.id, changed={'public_enabled': body.public_enabled}))
    db.commit()
    return profile(user)


# === Training Routes (TODO: verplaats naar routers/trainings.py) ===
def distance(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371 * 2 * math.asin(math.sqrt(min(1, d)))


def _contains(column, value):
    escaped = value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return column.ilike(f'%{escaped}%', escape='\\')


def listed_filter():
    return and_(
        Course.publication_status == 'published',
        Course.cancellation_status != 'cancelled'
    )


def records_for(db, account_id, course_ids=None):
    query = db.query(Record).filter_by(account_id=account_id)
    if course_ids is not None:
        if not course_ids:
            return {}
        query = query.filter(Record.course_id.in_(course_ids))
    return {row.course_id: row for row in query.all()}


def record_json(record):
    if not record:
        return None
    return {
        k: getattr(record, k)
        for k in ('signed_up', 'signup_status', 'signed_up_at', 'attended', 'attendance_status',
                   'attended_on', 'points', 'points_origin', 'credit_label', 'notes', 'public', 'version')
    }


def course_json(course, record=None, field_evidence=None):
    data = {k: v for k, v in (course.data or {}).items() if k not in ('source_text', 'model_weights_url', 'model_license_url')}
    for field in FILTER_FIELDS:
        data[field] = getattr(course, field)
    data['source_url'] = public_web_url(data.get('source_url'))
    data['registration_url'] = public_web_url(data.get('registration_url'))
    evidence_rows = []
    if field_evidence is not None:
        evidence_rows = [{'field_name': row.field_name, 'excerpt': row.excerpt, 'reviewed_at': row.reviewed_at} for row in field_evidence]
    return {
        'id': course.id, **data, 'demo': course.demo,
        'verification_status': course.verification_status or 'unverified',
        'publication_status': course.publication_status or 'published',
        'cancellation_status': course.cancellation_status or 'active',
        'reviewed_at': course.reviewed_at, 'field_evidence': evidence_rows,
        'record': record_json(record),
    }


class RecordChange(BaseModel):
    signed_up: bool = False
    signup_status: Literal['not_recorded', 'signed_up', 'cancelled'] | None = None
    attended: bool = False
    attendance_status: Literal['not_recorded', 'attended'] | None = None
    attended_on: date | None = None
    points: float | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)
    credit_label: str = Field(default='CPD', min_length=1, max_length=30)
    notes: str = Field(default='', max_length=5000)
    public: bool = False
    version: int = Field(default=0, ge=0)

    @field_validator('points', mode='before')
    @classmethod
    def points_reject_bool(cls, value):
        if isinstance(value, bool):
            raise ValueError('Points must be a number.')
        return value


@app.get('/api/v1/trainings')
def trainings(
    q: str = '', city: str = '', state: str = '', mode: str = '', difficulty: str = '',
    verification_status: str = '', publication_status: str = '',
    max_fee: float | None = None, max_fee_myr: float | None = None, min_points: float | None = None,
    period: Literal['upcoming', 'past', 'all'] = 'upcoming',
    date_from: date | None = None, date_to: date | None = None, include_unknown: bool = False,
    latitude: float | None = None, longitude: float | None = None, radius_km: int | None = None,
    page: int = 1, page_size: int = 20, user=Depends(current_user), db: Session = Depends(get_db),
):
    if page < 1 or not 1 <= page_size <= 50 or (latitude is None) != (longitude is None):
        raise HTTPException(422, 'Invalid pagination or location filter.')
    if radius_km is not None and latitude is None:
        raise HTTPException(422, 'Radius requires coordinates.')
    effective_radius = 25 if (latitude is not None and radius_km is None) else radius_km
    if effective_radius and effective_radius not in (10, 25, 50, 100):
        raise HTTPException(422, 'Invalid radius.')
    if latitude is not None and (not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        raise HTTPException(422, 'Invalid coordinates.')
    fee_limit = max_fee_myr if max_fee_myr is not None else max_fee
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'date_from cannot be after date_to.')
    if any(v is not None and (not math.isfinite(v) or v < 0) for v in (fee_limit, min_points)):
        raise HTTPException(422, 'Invalid price or points filter.')
    if mode and mode not in ('in_person', 'online', 'hybrid'):
        raise HTTPException(422, 'Invalid mode filter.')
    if difficulty and difficulty not in ('beginner', 'intermediate', 'advanced'):
        raise HTTPException(422, 'Invalid difficulty filter.')
    if verification_status and verification_status not in ('unverified', 'source_reviewed'):
        raise HTTPException(422, 'Invalid verification_status filter.')
    if publication_status and publication_status != 'published':
        raise HTTPException(422, 'Invalid publication_status filter.')

    query = db.query(Course).filter(listed_filter())
    if q:
        like = _contains(Course.title, q) | _contains(Course.provider, q) | _contains(Course.description, q)
        query = query.filter(like)
    near_me_includes_online = latitude is not None and mode in ('', 'online', 'hybrid')
    if city:
        city_match = _contains(Course.city, city)
        query = query.filter(or_(city_match, Course.mode == 'online') if near_me_includes_online else city_match)
    if state:
        state_match = _contains(Course.state, state)
        query = query.filter(or_(state_match, Course.mode == 'online') if near_me_includes_online else state_match)
    if mode:
        if latitude is not None and mode == 'hybrid':
            query = query.filter(Course.mode.in_(('hybrid', 'online')))
        else:
            query = query.filter(Course.mode == mode)
    if difficulty:
        query = query.filter(Course.difficulty == difficulty)
    if verification_status:
        query = query.filter(Course.verification_status == verification_status)
    if publication_status:
        query = query.filter(Course.publication_status == publication_status)

    today_s = today().isoformat()
    if period == 'upcoming':
        query = query.filter(or_(Course.start_date >= today_s, Course.start_date.is_(None)) if include_unknown else Course.start_date >= today_s)
    elif period == 'past':
        query = query.filter(or_(Course.start_date < today_s, Course.start_date.is_(None)) if include_unknown else Course.start_date < today_s)
    if date_from:
        query = query.filter(or_(Course.start_date >= date_from.isoformat(), Course.start_date.is_(None)) if include_unknown else Course.start_date >= date_from.isoformat())
    if date_to:
        query = query.filter(or_(Course.start_date <= date_to.isoformat(), Course.start_date.is_(None)) if include_unknown else Course.start_date <= date_to.isoformat())
    if fee_limit is not None:
        affordable = and_(Course.currency == 'MYR', Course.fee <= fee_limit)
        query = query.filter(or_(Course.fee.is_(None), affordable) if include_unknown else affordable)
    if min_points is not None:
        enough = Course.points >= min_points
        query = query.filter(or_(Course.points.is_(None), enough) if include_unknown else enough)

    if latitude is not None:
        delta_lat = effective_radius / 111
        delta_lon = effective_radius / (111 * max(0.2, abs(math.cos(math.radians(latitude)))))
        nearby = [and_(Course.latitude.isnot(None), Course.latitude.between(latitude - delta_lat, latitude + delta_lat), Course.longitude.between(longitude - delta_lon, longitude + delta_lon))]
        if mode in ('', 'online', 'hybrid'):
            nearby.append(Course.mode == 'online')
        query = query.filter(or_(*nearby))

    query = query.order_by(Course.start_date.is_(None), Course.start_date, Course.id)

    if latitude is None:
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        records = records_for(db, user.id, [c.id for c in rows])
        items = [{**course_json(c, records.get(c.id)), 'distance_km': None} for c in rows]
    else:
        scored = []
        for course in query.all():
            dist = None
            if course.mode != 'online' and course.latitude is not None and course.longitude is not None:
                dist = round(distance(latitude, longitude, course.latitude, course.longitude), 1)
                if dist > effective_radius:
                    continue
            scored.append((course, dist))
        scored.sort(key=lambda x: (x[1] is None, x[1] or 0, x[0].start_date is None, x[0].start_date or '', x[0].id))
        total = len(scored)
        page_rows = scored[(page - 1) * page_size:page * page_size]
        records = records_for(db, user.id, [c.id for c, _ in page_rows])
        items = [{**course_json(c, records.get(c.id)), 'distance_km': d} for c, d in page_rows]

    return {
        'items': items, 'total': total, 'page': page, 'page_size': page_size,
        'applied_filters': {'q': q or None, 'city': city or None, 'state': state or None, 'mode': mode or None,
                            'difficulty': difficulty or None, 'verification_status': verification_status or None,
                            'publication_status': publication_status or None, 'max_fee_myr': fee_limit,
                            'min_points': min_points, 'period': period,
                            'date_from': date_from.isoformat() if date_from else None,
                            'date_to': date_to.isoformat() if date_to else None,
                            'include_unknown': include_unknown, 'latitude': latitude, 'longitude': longitude,
                            'radius_km': effective_radius}
    }


@app.get('/api/v1/trainings/{course_id}')
def detail(course_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, 'Training not found.')
    return course_json(course, db.query(Record).filter_by(account_id=user.id, course_id=course_id).first())


@app.put('/api/v1/me/trainings/{course_id}')
def save_record(course_id: str, body: RecordChange, user=Depends(current_user), db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, 'Training not found.')
    attendance = 'attended' if (body.attendance_status == 'attended' or body.attended) else 'not_recorded'
    body.attended = attendance == 'attended'
    if body.attended:
        if not body.attended_on or body.attended_on > today():
            raise HTTPException(422, 'Choose a completion date that is not in the future.')
        if course.start_date and body.attended_on < date.fromisoformat(course.start_date):
            raise HTTPException(422, 'Attendance cannot be before the training date.')
    else:
        body.attended_on = None
        body.public = False
    values = body.model_dump(mode='json', exclude={'version'})
    record = db.query(Record).filter_by(account_id=user.id, course_id=course_id).first()
    status = values.pop('signup_status', None)
    if status == 'cancelled':
        pass
    elif status == 'signed_up' or values.get('signed_up'):
        status = 'signed_up'
    elif status == 'not_recorded' or status is None:
        status = 'not_recorded'
    else:
        status = 'signed_up' if values.get('signed_up') else 'not_recorded'
    prior = (record.signup_status if record else None) or 'not_recorded'
    if prior == 'not_recorded' and record and record.signed_up:
        prior = 'signed_up'
    if status == 'cancelled' and prior not in ('signed_up', 'cancelled'):
        raise HTTPException(422, 'Cancel sign-up only after a recorded provider sign-up.')
    values['signup_status'] = status
    values['signed_up'] = status == 'signed_up'
    values['attendance_status'] = attendance
    values['attended'] = attendance == 'attended'
    if status == 'signed_up':
        values['signed_up_at'] = (record.signed_up_at if record and record.signed_up_at else time.time())
    elif record:
        values['signed_up_at'] = record.signed_up_at
    values['points_origin'] = 'self_reported' if values.get('points') is not None else ''
    if record:
        old = record_json(record)
        comparable = {k: v for k, v in values.items() if k in old}
        if all(old[k] == comparable[k] for k in comparable):
            return old
        changed = db.execute(update(Record).where(Record.id == record.id, Record.version == body.version).values(**values, version=Record.version+1))
        if changed.rowcount != 1:
            db.rollback()
            raise HTTPException(409, 'This record changed. Reopen it before saving.')
        db.add(RecordHistory(record_id=record.id, account_id=user.id, changed={k: old[k] for k in ('signup_status', 'attendance_status', 'attended', 'attended_on', 'points', 'credit_label')}))
    else:
        if body.version != 0:
            raise HTTPException(409, 'Record version does not match.')
        record = Record(account_id=user.id, course_id=course_id, **values)
        db.add(record)
    try:
        db.flush()
        db.add(Audit(account_id=user.id, action='training_record_changed', entity_id=record.id, changed={k:v for k,v in values.items() if k != 'notes'}))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'This record changed. Refresh and try again.')
    db.refresh(record)
    return record_json(record)


@app.get('/api/v1/me/trainings')
def my_trainings(
    signup_status: Literal['not_recorded', 'signed_up', 'cancelled'] | None = None,
    attendance_status: Literal['not_recorded', 'attended'] | None = None,
    attended: bool | None = None, page: int = 1, page_size: int = 20,
    user=Depends(current_user), db: Session = Depends(get_db),
):
    if page < 1 or not 1 <= page_size <= 50:
        raise HTTPException(422, 'Invalid pagination.')
    query = db.query(Record, Course).join(Course, Record.course_id == Course.id).filter(Record.account_id == user.id)
    if signup_status == 'signed_up':
        query = query.filter(Record.signup_status != 'cancelled', or_(Record.signup_status == 'signed_up', Record.signed_up.is_(True)))
    elif signup_status == 'cancelled':
        query = query.filter(Record.signup_status == 'cancelled')
    elif signup_status == 'not_recorded':
        query = query.filter(Record.signup_status == 'not_recorded', Record.signed_up.is_(False))
    elif signup_status:
        query = query.filter(Record.signup_status == signup_status)
    if attendance_status == 'attended':
        query = query.filter(or_(Record.attendance_status == 'attended', Record.attended.is_(True)))
    elif attendance_status == 'not_recorded':
        query = query.filter(Record.attendance_status != 'attended', Record.attended.is_(False))
    elif attendance_status:
        query = query.filter(Record.attendance_status == attendance_status)
    elif attended is not None:
        if attended:
            query = query.filter(or_(Record.attendance_status == 'attended', Record.attended.is_(True)))
        else:
            query = query.filter(Record.attendance_status != 'attended', Record.attended.is_(False))
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {'items': [course_json(c, r) for r, c in rows], 'total': total, 'page': page, 'page_size': page_size}


@app.get('/api/v1/me/progress')
def progress(year: int | None = None, user=Depends(current_user), db: Session = Depends(get_db)):
    year = today().year if year is None else year
    if not 1900 <= year <= 2200:
        raise HTTPException(422, 'Invalid year.')
    return progress_snapshot(db, user.id, year)


@app.get('/api/v1/me/trainings/{course_id}/history')
def record_history(course_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    record = db.query(Record).filter_by(account_id=user.id, course_id=course_id).first()
    if not record:
        return {'items': []}
    rows = db.query(RecordHistory).filter_by(record_id=record.id, account_id=user.id).order_by(RecordHistory.created_at.desc()).limit(20).all()
    return {'items': [{'at': row.created_at, **(row.changed or {})} for row in rows]}


@app.get('/api/v1/me/suggestions')
def me_suggestions(user=Depends(current_user), db: Session = Depends(get_db)):
    return suggestions_for(db, user)


# === Digest & Certificates (TODO: verplaats naar routers/digest.py, routers/certificates.py) ===
class DigestChange(BaseModel):
    opted_in: bool
    cadence_days: int | None = Field(default=None, ge=7, le=60)


@app.get('/api/v1/me/digest')
def get_digest(user=Depends(current_user), db: Session = Depends(get_db)):
    return preference_json(ensure_preference(db, user.id))


@app.patch('/api/v1/me/digest')
def patch_digest(body: DigestChange, user=Depends(current_user), db: Session = Depends(get_db)):
    pref = ensure_preference(db, user.id)
    was_out = not pref.opted_in
    pref.opted_in = body.opted_in
    if body.cadence_days is not None:
        pref.cadence_days = body.cadence_days
    if body.opted_in:
        pref.unsubscribed_at = None
        if was_out:
            pref.fail_count = 0
            pref.next_retry_at = None
    else:
        pref.unsubscribed_at = time.time()
    db.commit()
    return preference_json(pref)


class CertificateIssue(BaseModel):
    year: int | None = Field(default=None, ge=1900, le=2200)


@app.post('/api/v1/me/certificates', status_code=201)
def create_certificate(body: CertificateIssue, user=Depends(current_user), db: Session = Depends(get_db)):
    year = today().year if body.year is None else body.year
    try:
        row = issue_certificate(db, user, year)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return certificate_json(row)


@app.get('/api/v1/me/certificates/{certificate_id}')
def download_certificate(certificate_id: str, format: str = 'pdf', user=Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(AffiliationCertificate, certificate_id)
    if not row or row.account_id != user.id:
        raise HTTPException(404, 'Certificate not found.')
    kind = (format or 'pdf').strip().lower()
    if kind not in ('pdf', 'html'):
        raise HTTPException(422, 'Certificate format must be pdf or html.')
    if kind == 'html':
        return Response(certificate_html(user, row), media_type='text/html; charset=utf-8',
                        headers={'Content-Disposition': f'inline; filename="carecredits-{row.year}-{row.id[:8]}.html"'})
    return Response(certificate_pdf(user, row), media_type='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="carecredits-{row.year}-{row.id[:8]}.pdf"'})


UNSUBSCRIBE_OK_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>Unsubscribed — CareCredits</title><style>body{font-family:Georgia,serif;color:#10233f;max-width:36rem;margin:3rem auto;padding:0 1.25rem}h1{font-size:1.6rem}p{line-height:1.5;color:#3d536b}</style></head><body><h1>You are unsubscribed</h1><p>CareCredits will not send another biweekly digest unless you opt in again.</p></body></html>"""
UNSUBSCRIBE_INVALID_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>Unsubscribe link invalid — CareCredits</title><style>body{font-family:Georgia,serif;color:#10233f;max-width:36rem;margin:3rem auto;padding:0 1.25rem}h1{font-size:1.6rem}p{line-height:1.5;color:#3d536b}</style></head><body><h1>Unsubscribe link invalid</h1><p>This unsubscribe link is missing, blank, or no longer valid.</p></body></html>"""


def _wants_unsubscribe_json(request: Request) -> bool:
    accept = (request.headers.get('accept') or '').lower()
    return 'application/json' in accept and 'text/html' not in accept


@app.get('/api/v1/digest/unsubscribe')
def digest_unsubscribe(request: Request, token: str | None = None, db: Session = Depends(get_db)):
    cleaned = (token or '').strip()
    if not cleaned:
        if _wants_unsubscribe_json(request):
            return envelope(404, 'Unsubscribe link is invalid or expired.', request)
        return HTMLResponse(UNSUBSCRIBE_INVALID_HTML, status_code=404)
    pref = db.query(DigestPreference).filter_by(unsubscribe_token=cleaned).first()
    if not pref:
        if _wants_unsubscribe_json(request):
            return envelope(404, 'Unsubscribe link is invalid or expired.', request)
        return HTMLResponse(UNSUBSCRIBE_INVALID_HTML, status_code=404)
    pref.opted_in = False
    pref.unsubscribed_at = time.time()
    db.commit()
    payload = {'opted_in': False, 'message': 'You are unsubscribed from CareCredits digests.'}
    if _wants_unsubscribe_json(request):
        return payload
    return HTMLResponse(UNSUBSCRIBE_OK_HTML)


# === Export & Public Profile (TODO: verplaats naar routers/export.py, routers/public.py) ===
@app.get('/api/v1/me/export/{kind}')
def export(kind: Literal['csv', 'eml'], year: int | None = None, user=Depends(current_user), db: Session = Depends(get_db)):
    if year is not None and not 1900 <= year <= 2200:
        raise HTTPException(422, 'Invalid year.')
    rows = db.query(Record, Course).join(Course, Record.course_id == Course.id).filter(Record.account_id == user.id).all()
    if year is not None:
        year_key = str(year)
        scoped = []
        for r, c in rows:
            attended = getattr(r, 'attendance_status', None) == 'attended' or bool(r.attended)
            if attended:
                if r.attended_on and str(r.attended_on).startswith(year_key):
                    scoped.append((r, c))
            elif (c.start_date or '').startswith(year_key):
                scoped.append((r, c))
        rows = scoped

    def cell(value):
        value = str(value or '')
        visible = value.lstrip(' \t\r\n\x0b\x0c\ufeff\u200b\u200c\u200d\u2060\u00a0\u1680\u180e\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u00ad\u034f\u061c')
        starters = ('=', '+', '-', '@', '\uff1d', '\uff0b', '\uff0d', '\uff20', '\u2212', '\ufe63')
        return "'" + value if visible[:1] in starters else value

    suffix = f'-{year}' if year is not None else ''
    if kind == 'csv':
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['Training', 'Provider', 'Session date', 'Signed up', 'Signup status', 'Attended', 'Attendance status', 'Completed on', 'Recorded points', 'Credit label', 'Source', 'Evidence status'])
        for r, c in rows:
            signup_status = getattr(r, 'signup_status', None) or ('signed_up' if r.signed_up else 'not_recorded')
            attendance_status = getattr(r, 'attendance_status', None) or ('attended' if r.attended else 'not_recorded')
            attended = attendance_status == 'attended' or bool(r.attended)
            signed_up = signup_status != 'cancelled' and (signup_status == 'signed_up' or bool(r.signed_up))
            writer.writerow([cell(c.title), cell(c.provider), cell(c.start_date or ''), signed_up, cell(signup_status), attended, cell(attendance_status), cell(r.attended_on or ''), r.points if r.points is not None else '', cell(r.credit_label), cell(public_web_url((c.data or {}).get('source_url')) or ''), 'Self-reported'])
        content, mime = stream.getvalue(), 'text/csv; charset=utf-8'
    else:
        message = EmailMessage()
        subject_year = f' ({year})' if year is not None else ''
        message['Subject'] = f'My CPD training record{subject_year}'
        message['X-Unsent'] = '1'
        lines = ['My personal training record (self-reported, not independently verified):', '']
        if year is not None:
            lines.append(f'Year filter: {year}')
            lines.append('')
        attended_lines = [f"{c.title} | {r.attended_on} | {r.points if r.points is not None else 'Not recorded'} {r.credit_label}" for r, c in rows if getattr(r, 'attendance_status', None) == 'attended' or r.attended]
        if attended_lines:
            lines.extend(attended_lines)
        else:
            lines.append(f'No attended records for {year}.' if year is not None else 'No attended records yet.')
        message.set_content('\n'.join(lines))
        content, mime = message.as_bytes(), 'message/rfc822'
    return Response(content, media_type=mime, headers={'Content-Disposition': f'attachment; filename="carecredits-record{suffix}.{kind}"'})


@app.get('/api/v1/public/{slug}')
def public_profile(slug: str, db: Session = Depends(get_db)):
    account = db.query(Account).filter_by(public_slug=slug, public_enabled=True).first()
    if not account:
        raise HTTPException(404, 'This training profile is private or unavailable.')
    items = []
    for r, c in db.query(Record, Course).join(Course, Record.course_id == Course.id).filter(Record.account_id == account.id, Record.public.is_(True)):
        if not (getattr(r, 'attendance_status', None) == 'attended' or r.attended):
            continue
        items.append({'title': c.title, 'provider': c.provider, 'attended_on': r.attended_on, 'source_url': public_web_url((c.data or {}).get('source_url')), 'demo': c.demo})
    return {'name': account.name, 'bio': account.bio, 'items': items, 'evidence_status': 'Self-reported training history; not independently verified.'}


# === Audit (TODO: verplaats naar routers/admin.py) ===
AUDIT_HIDDEN = {'notes', 'password', 'password_hash', 'token', 'secret', 'api_key'}


def audit_json(row: Audit) -> dict:
    changed = row.changed if isinstance(row.changed, dict) else {}
    return {'id': row.id, 'action': row.action, 'entity_id': row.entity_id, 'changed': {key: value for key, value in changed.items() if key not in AUDIT_HIDDEN}, 'at': row.created_at}


def paginated_audit(db: Session, query, page: int, page_size: int):
    if page < 1 or not 1 <= page_size <= 50:
        raise HTTPException(422, 'Invalid pagination.')
    total = query.count()
    rows = query.order_by(Audit.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {'items': [audit_json(row) for row in rows], 'total': total, 'page': page, 'page_size': page_size}


@app.get('/api/v1/me/audit')
def my_audit(page: int = 1, page_size: int = 20, user=Depends(current_user), db: Session = Depends(get_db)):
    return paginated_audit(db, db.query(Audit).filter_by(account_id=user.id), page, page_size)


@app.get('/api/v1/admin/audit')
def admin_audit(page: int = 1, page_size: int = 20, user=Depends(operator), db: Session = Depends(get_db)):
    return paginated_audit(db, db.query(Audit), page, page_size)


# === Admin Misc (TODO: verplaats naar routers/admin.py) ===
@app.post('/api/v1/admin/digests/run')
def admin_run_digests(user=Depends(operator), db: Session = Depends(get_db)):
    throttle(db, 'digests:' + user.id, 20, 300)
    return run_due_digests(db)


@app.get('/api/v1/admin/services')
def services(user=Depends(operator), db: Session = Depends(get_db)):
    database = 'ready'
    try:
        db.execute(text('SELECT 1'))
    except Exception:
        database = 'unavailable'
    return {'backend': 'ready' if database == 'ready' else 'degraded', 'database': database, 'frontend': 'this portal'}


@app.get('/api/v1/admin/integrations')
def integrations(user=Depends(operator)):
    weights = env_or_provisional('MODEL_WEIGHTS_URL') or None
    license_url = env_or_provisional('MODEL_LICENSE_URL') or None
    input_chars = int((env_or_provisional('MODEL_MAX_INPUT_CHARS') or '0').strip()) or None
    output_tokens = int((env_or_provisional('MODEL_MAX_OUTPUT_TOKENS') or '0').strip()) or None
    return {
        'model_id': env_or_provisional('MODEL_ID') or None, 'model_publisher': env_or_provisional('MODEL_PUBLISHER') or None,
        'model_host': env_or_provisional('MODEL_HOST') or None, 'model_weights_url': public_web_url(weights),
        'model_license_url': public_web_url(license_url), 'model_identity_provisional': using_provisional('MODEL_ID'),
        'model_caps_configured': bool(input_chars and output_tokens), 'model_max_input_chars': input_chars,
        'model_max_output_tokens': output_tokens, 'google_oauth': google_oauth(),
    }


@app.post('/api/v1/admin/trainings/{course_id}/cancel')
def cancel_training(course_id: str, user=Depends(operator), db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, 'Training not found.')
    course.publication_status = 'cancelled'
    course.cancellation_status = 'cancelled'
    course.updated_at = time.time()
    db.add(Audit(account_id=user.id, action='course_cancelled', entity_id=course.id, changed={'publication_status': 'cancelled'}))
    db.commit()
    return course_json(course)