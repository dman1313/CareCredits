import csv
import io
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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, or_, update, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from database import Base, engine, get_db, SessionLocal
from portal_models import (
    Account, LoginSession, Course, Record, RecordHistory, Job, Candidate, Audit, SchemaVersion,
    DigestPreference, AffiliationCertificate,
    SCHEMA_VERSION, FILTER_FIELDS, fill_course,
)
from security import current_user, operator, worker, password_hash, password_matches, digest, throttle
from shared.contracts import Training, validate_evidence
from catalogue import (
    source_key, course_public, exact_course, near_neighbours,
    save_new_candidate, link_existing, publish_new_event,
)
from jev import decide_existence, JevError, api_key as typesafe_key
from schedule import enqueue_daily, load_topics, local_today
from digest import (
    ensure_preference, preference_json, run_due_digests,
)
from certificates import issue_certificate, certificate_json, render_html as certificate_html
from suggestions import suggestions_for
from errors import envelope, http_exception_handler, validation_exception_handler, request_id
from oauth import authorize_url, configured as google_oauth, exchange_code, issue_session, upsert_account, OAuthError


def today():
    return datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()


def initialize():
    if os.getenv('DEMO_MODE') == 'true' and os.getenv('APP_ENV') == 'production':
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
    if current == 0:
        db.add(SchemaVersion(version=SCHEMA_VERSION))
        db.commit()
        return
    if current == 1:
        _add_course_filter_columns(db)
        for course in db.query(Course).all():
            fill_course(course, course.data or {})
        db.add(SchemaVersion(version=2))
        current = 2
    if current == 2:
        _add_candidate_review_reason(db)
        db.add(SchemaVersion(version=3))
        current = 3
        db.commit()
    if current == 3:
        # DigestPreference / DigestSend / AffiliationCertificate created via create_all.
        db.add(SchemaVersion(version=4))
        current = 4
        db.commit()
    if current == 4:
        _add_signup_status(db)
        db.add(SchemaVersion(version=5))
        current = 5
        db.commit()
    if current != SCHEMA_VERSION:
        raise RuntimeError('Unsupported portal schema. Apply the matching migration.')


def _add_course_filter_columns(db):
    existing = {column['name'] for column in inspect(db.get_bind()).get_columns('courses')}
    statements = [
        ('title', "VARCHAR DEFAULT '' NOT NULL"),
        ('provider', "VARCHAR DEFAULT '' NOT NULL"),
        ('description', "VARCHAR DEFAULT '' NOT NULL"),
        ('start_date', 'VARCHAR'),
        ('city', 'VARCHAR'),
        ('state', 'VARCHAR'),
        ('country', "VARCHAR DEFAULT 'MY' NOT NULL"),
        ('mode', "VARCHAR DEFAULT 'online' NOT NULL"),
        ('latitude', 'FLOAT'),
        ('longitude', 'FLOAT'),
        ('fee', 'FLOAT'),
        ('currency', 'VARCHAR'),
        ('points', 'FLOAT'),
        ('credit_label', 'VARCHAR'),
        ('difficulty', 'VARCHAR'),
    ]
    for name, definition in statements:
        if name not in existing:
            db.execute(text(f'ALTER TABLE courses ADD COLUMN {name} {definition}'))
    db.commit()


def _add_candidate_review_reason(db):
    existing = {column['name'] for column in inspect(db.get_bind()).get_columns('course_candidates')}
    if 'review_reason' not in existing:
        db.execute(text("ALTER TABLE course_candidates ADD COLUMN review_reason VARCHAR DEFAULT '' NOT NULL"))
    db.commit()


def _add_signup_status(db):
    existing = {column['name'] for column in inspect(db.get_bind()).get_columns('doctor_records')}
    if 'signup_status' not in existing:
        db.execute(text("ALTER TABLE doctor_records ADD COLUMN signup_status VARCHAR DEFAULT 'not_recorded' NOT NULL"))
        db.execute(text("UPDATE doctor_records SET signup_status = 'signed_up' WHERE signed_up = 1"))
    db.commit()


@asynccontextmanager
async def lifespan(app):
    initialize()
    import asyncio

    stop = asyncio.Event()
    tasks = []

    async def daily_scrape_loop():
        while not stop.is_set():
            try:
                with SessionLocal() as db:
                    enqueue_daily(db)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=3600)
            except asyncio.TimeoutError:
                continue

    async def digest_loop():
        while not stop.is_set():
            try:
                with SessionLocal() as db:
                    run_due_digests(db)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=3600)
            except asyncio.TimeoutError:
                continue

    if os.getenv('DAILY_SCRAPE_ENABLED', 'true').lower() == 'true':
        tasks.append(asyncio.create_task(daily_scrape_loop()))
    if os.getenv('DIGEST_ENABLED', 'true').lower() == 'true':
        tasks.append(asyncio.create_task(digest_loop()))
    yield
    stop.set()
    for task in tasks:
        try:
            await asyncio.wait_for(task, timeout=2)
        except Exception:
            task.cancel()


app = FastAPI(title='CareCredits', version='0.5.0', lifespan=lifespan)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.middleware('http')
async def request_boundary(request: Request, call_next):
    request.state.request_id = secrets.token_hex(8)
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not request.url.path.startswith('/internal/'):
        origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
        if request.headers.get('x-care-client') != '1' or (request.headers.get('origin') and request.headers['origin'] not in origins):
            return envelope(403, 'Request origin not allowed.', request)
    result = await call_next(request)
    result.headers['Cache-Control'] = 'no-store'
    result.headers['X-Content-Type-Options'] = 'nosniff'
    result.headers['X-Request-Id'] = request_id(request)
    return result


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default='Doctor', min_length=2, max_length=100)

    @field_validator('email')
    @classmethod
    def email_check(cls, value):
        value = value.strip().lower()
        if '@' not in value or '.' not in value.split('@')[-1] or any(c.isspace() for c in value):
            raise ValueError('Enter a valid email address')
        return value


class ProfileChange(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    city: str = Field(max_length=100)
    bio: str = Field(max_length=1000)
    public_enabled: bool


class RecordChange(BaseModel):
    signed_up: bool = False
    signup_status: Literal['not_recorded', 'signed_up', 'cancelled'] | None = None
    attended: bool = False
    attended_on: date | None = None
    points: float | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)
    credit_label: str = Field(default='CPD', min_length=1, max_length=30)
    notes: str = Field(default='', max_length=5000)
    public: bool = False
    version: int = Field(default=0, ge=0)


class NewJob(BaseModel):
    query: str = Field(min_length=3, max_length=300)

    @field_validator('query')
    @classmethod
    def trim(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('Enter a search topic')
        return value.strip()


class TavilySource(BaseModel):
    url: str = Field(max_length=2000)
    title: str = Field(default='', max_length=300)
    snippet: str = Field(default='', max_length=2000)
    extraction_status: str = Field(default='failed', max_length=40)
    verification_status: str = Field(default='unverified', max_length=40)


class CompleteJob(BaseModel):
    lease_token: str
    candidates: list[Training] = Field(default_factory=list, max_length=20)
    sources: list[TavilySource] = Field(default_factory=list, max_length=5)
    warnings: list[str] = Field(default_factory=list, max_length=30)
    status: Literal['succeeded', 'partial', 'failed']
    usage: dict = Field(default_factory=dict)


class Review(BaseModel):
    action: Literal['publish', 'reject', 'hold']
    reason: str = Field(default='', max_length=500)

    @model_validator(mode='after')
    def require_hold_reason(self):
        if self.action == 'hold' and len(self.reason.strip()) < 3:
            raise ValueError('Hold requires a reason of at least 3 characters.')
        return self


def profile(account):
    return {k: getattr(account, k) for k in ('id', 'email', 'name', 'city', 'role', 'bio', 'public_enabled', 'public_slug')}


def record_json(record):
    if not record:
        return None
    return {
        k: getattr(record, k)
        for k in ('signed_up', 'signup_status', 'attended', 'attended_on', 'points', 'credit_label', 'notes', 'public', 'version')
    }


def course_json(course, record=None):
    # Full source text and model configuration stay in operator review only.
    data = {k: v for k, v in (course.data or {}).items() if k not in ('source_text', 'model_weights_url', 'model_license_url')}
    for field in FILTER_FIELDS:
        data[field] = getattr(course, field)
    return {'id': course.id, **data, 'demo': course.demo, 'verification_status': 'unverified', 'record': record_json(record)}


def audit(db, account_id, action, entity, changed):
    db.add(Audit(account_id=account_id, action=action, entity_id=entity, changed=changed))


class CatalogueLookup(BaseModel):
    candidate: Training


class CatalogueDecide(BaseModel):
    candidate: Training
    matches: list[dict] | None = Field(default=None, max_length=5)


class CatalogueSave(BaseModel):
    candidate: Training
    judgment: dict = Field(default_factory=dict)
    job_id: str | None = None


@app.get('/health')
@app.get('/health/live')
def health():
    return {'status': 'ok'}


@app.get('/health/ready')
def ready(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ready'}


@app.get('/api/v1/config')
def config():
    return {
        'demo': os.getenv('DEMO_MODE') == 'true',
        'signup_enabled': os.getenv('ALLOW_SIGNUP') == 'true',
        'typesafe_configured': bool(typesafe_key()),
        'daily_scrape_topics': len(load_topics()),
        'local_day': local_today(),
        'digest_enabled': os.getenv('DIGEST_ENABLED', 'true').lower() == 'true',
        'mail_provider': (os.getenv('MAIL_PROVIDER') or 'log').strip().lower(),
        'oauth_google': google_oauth(),
    }


@app.post('/api/v1/auth/register', status_code=201)
def register(body: Credentials, request: Request, db: Session = Depends(get_db)):
    if os.getenv('ALLOW_SIGNUP') != 'true':
        raise HTTPException(403, 'Registration is disabled. Contact the application operator.')
    throttle(db, 'register:' + request.client.host, 10, 3600)
    account = Account(email=body.email, name=body.name, password_hash=password_hash(body.password))
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'This address cannot be registered. Try signing in.')
    return {'message': 'Account created. Please sign in.'}


_DUMMY = password_hash('not-an-account-password')


@app.post('/api/v1/auth/login')
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(db, 'login-ip:' + request.client.host, 30, 300)
    throttle(db, 'login-email:' + body.email, 10, 300)
    account = db.query(Account).filter_by(email=body.email).first()
    valid = password_matches(body.password, account.password_hash if account else _DUMMY)
    if not account or not valid:
        raise HTTPException(401, 'Email or password is incorrect.')
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=digest(token), account_id=account.id, expires_at=time.time() + 28800))
    db.commit()
    response.set_cookie('care_session', token, httponly=True, secure=os.getenv('APP_ENV') == 'production', samesite='lax', max_age=28800, path='/')
    return profile(account)


@app.get('/api/v1/auth/oauth/google')
def google_start(response: Response):
    state = secrets.token_urlsafe(24)
    try:
        url = authorize_url(state)
    except OAuthError as exc:
        raise HTTPException(exc.status_code, exc.detail)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie('oauth_state', state, httponly=True, samesite='lax', max_age=600, path='/')
    return response


@app.get('/api/v1/auth/oauth/google/callback')
def google_callback(request: Request, db: Session = Depends(get_db), code: str = '', state: str = '', error: str = ''):
    expected = request.cookies.get('oauth_state', '')
    frontend = (os.getenv('PUBLIC_FRONTEND_BASE') or 'http://127.0.0.1:3000').rstrip('/')
    if error:
        return RedirectResponse(frontend + '/live?oauth=denied', status_code=302)
    if not code or not state or not expected or not secrets.compare_digest(state, expected):
        raise HTTPException(401, 'Google sign-in state did not match. Try again.')
    try:
        identity = exchange_code(code)
        account = upsert_account(db, identity, os.getenv('ALLOW_SIGNUP') == 'true')
        token = issue_session(db, account)
    except OAuthError as exc:
        raise HTTPException(exc.status_code, exc.detail)
    dest = RedirectResponse(frontend + '/live', status_code=302)
    dest.set_cookie('care_session', token, httponly=True, secure=os.getenv('APP_ENV') == 'production', samesite='lax', max_age=28800, path='/')
    dest.delete_cookie('oauth_state', path='/')
    return dest


@app.post('/api/v1/auth/logout')
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    db.query(LoginSession).filter_by(token_hash=digest(request.cookies.get('care_session', ''))).delete()
    db.commit()
    response.delete_cookie('care_session', path='/')
    return {'ok': True}


@app.get('/api/v1/me')
def me(user=Depends(current_user)):
    return profile(user)


@app.patch('/api/v1/me')
def change_profile(body: ProfileChange, user=Depends(current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump().items():
        setattr(user, k, v)
    audit(db, user.id, 'profile_changed', user.id, {'public_enabled': body.public_enabled})
    db.commit()
    return profile(user)


def distance(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371 * 2 * math.asin(math.sqrt(min(1, d)))


def _contains(column, value):
    escaped = value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return column.ilike(f'%{escaped}%', escape='\\')


@app.get('/api/v1/trainings')
def trainings(q: str = '', city: str = '', state: str = '', mode: str = '', difficulty: str = '', max_fee: float | None = None, max_fee_myr: float | None = None, min_points: float | None = None, period: Literal['upcoming', 'past', 'all'] = 'upcoming', date_from: date | None = None, date_to: date | None = None, include_unknown: bool = False, latitude: float | None = None, longitude: float | None = None, radius_km: int = 25, page: int = 1, page_size: int = 12, user=Depends(current_user), db: Session = Depends(get_db)):
    if page < 1 or not 1 <= page_size <= 50 or radius_km not in (10, 25, 50, 100) or (latitude is None) != (longitude is None):
        raise HTTPException(422, 'Invalid pagination or location filter.')
    if latitude is not None and (not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        raise HTTPException(422, 'Invalid coordinates.')
    if max_fee is not None and max_fee_myr is not None and max_fee != max_fee_myr:
        raise HTTPException(422, 'Use a single fee filter.')
    fee_limit = max_fee_myr if max_fee_myr is not None else max_fee
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'date_from cannot be after date_to.')
    if any(v is not None and (not math.isfinite(v) or v < 0) for v in (fee_limit, min_points)):
        raise HTTPException(422, 'Invalid price or points filter.')
    query = db.query(Course)
    if q:
        like = _contains(Course.title, q) | _contains(Course.provider, q) | _contains(Course.description, q)
        query = query.filter(like)
    if city:
        query = query.filter(_contains(Course.city, city))
    if state:
        query = query.filter(_contains(Course.state, state))
    if mode:
        query = query.filter(Course.mode == mode)
    if difficulty:
        query = query.filter(Course.difficulty == difficulty)
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
        delta_lat = radius_km / 111
        delta_lon = radius_km / (111 * max(0.2, abs(math.cos(math.radians(latitude)))))
        nearby = [
            and_(
                Course.latitude.isnot(None),
                Course.latitude.between(latitude - delta_lat, latitude + delta_lat),
                Course.longitude.between(longitude - delta_lon, longitude + delta_lon),
            )
        ]
        if mode in ('', 'online', 'hybrid'):
            nearby.append(Course.mode == 'online')
        if city or state:
            nearby.append(and_(Course.mode != 'online', Course.latitude.is_(None)))
        query = query.filter(or_(*nearby))
    query = query.order_by(Course.start_date.is_(None), Course.start_date, Course.id)
    records = {r.course_id: r for r in db.query(Record).filter_by(account_id=user.id)}
    if latitude is None:
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        items = [{**course_json(course, records.get(course.id)), 'distance_km': None} for course in rows]
    else:
        items = []
        for course in query.all():
            item = course_json(course, records.get(course.id))
            item['distance_km'] = None
            if course.mode != 'online' and course.latitude is not None and course.longitude is not None:
                item['distance_km'] = round(distance(latitude, longitude, course.latitude, course.longitude), 1)
                if item['distance_km'] > radius_km:
                    continue
            items.append(item)
        total = len(items)
        items = items[(page - 1) * page_size:page * page_size]
    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'applied_filters': {
            'q': q or None, 'city': city or None, 'state': state or None, 'mode': mode or None,
            'difficulty': difficulty or None, 'max_fee_myr': fee_limit, 'min_points': min_points,
            'period': period, 'date_from': date_from.isoformat() if date_from else None,
            'date_to': date_to.isoformat() if date_to else None, 'include_unknown': include_unknown,
            'latitude': latitude, 'longitude': longitude, 'radius_km': radius_km if latitude is not None else None,
        },
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
    if status not in ('not_recorded', 'signed_up', 'cancelled'):
        if values.get('signed_up'):
            status = 'signed_up'
        elif record and record.signup_status == 'signed_up':
            status = 'cancelled'
        else:
            status = 'not_recorded'
    values['signup_status'] = status
    values['signed_up'] = status == 'signed_up'
    if record:
        old = record_json(record)
        comparable = {k: v for k, v in values.items() if k in old}
        if all(old[k] == comparable[k] for k in comparable):
            return old
        changed = db.execute(update(Record).where(Record.id == record.id, Record.version == body.version).values(**values, version=Record.version+1))
        if changed.rowcount != 1:
            db.rollback()
            raise HTTPException(409, 'This record changed. Reopen it before saving.')
        db.add(RecordHistory(record_id=record.id, account_id=user.id, changed={k: old[k] for k in ('signup_status', 'attended', 'attended_on', 'points', 'credit_label')}))
    else:
        if body.version != 0:
            raise HTTPException(409, 'Record version does not match.')
        record = Record(account_id=user.id, course_id=course_id, **values)
        db.add(record)
    try:
        db.flush()
        audit(db, user.id, 'training_record_changed', record.id, {k:v for k,v in values.items() if k != 'notes'})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'This record changed. Refresh and try again.')
    db.refresh(record)
    return record_json(record)


@app.get('/api/v1/me/trainings')
def my_trainings(user=Depends(current_user), db: Session = Depends(get_db)):
    return {'items': [course_json(c, r) for r, c in db.query(Record, Course).join(Course, Record.course_id == Course.id).filter(Record.account_id == user.id).all()]}


@app.get('/api/v1/me/progress')
def progress(year: int | None = None, user=Depends(current_user), db: Session = Depends(get_db)):
    year = year or today().year
    if not 1900 <= year <= 2200:
        raise HTTPException(422, 'Invalid year.')
    records = db.query(Record).filter_by(account_id=user.id).all()
    attended = [r for r in records if r.attended and r.attended_on and r.attended_on.startswith(str(year))]
    countable = [r for r in attended if r.points is not None and r.credit_label.strip().upper() == 'CPD']
    return {'year': year, 'signed_up': sum((getattr(r, 'signup_status', None) == 'signed_up' or r.signed_up) and not r.attended for r in records), 'attended': len(attended), 'points': round(sum(r.points for r in countable), 2), 'excluded': len(attended)-len(countable)}


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


class DigestChange(BaseModel):
    opted_in: bool
    cadence_days: int = Field(14, ge=7, le=60)


@app.get('/api/v1/me/digest')
def get_digest(user=Depends(current_user), db: Session = Depends(get_db)):
    return preference_json(ensure_preference(db, user.id))


@app.patch('/api/v1/me/digest')
def patch_digest(body: DigestChange, user=Depends(current_user), db: Session = Depends(get_db)):
    pref = ensure_preference(db, user.id)
    pref.opted_in = body.opted_in
    pref.cadence_days = body.cadence_days
    if body.opted_in:
        pref.unsubscribed_at = None
    else:
        pref.unsubscribed_at = time.time()
    db.commit()
    return preference_json(pref)


class CertificateIssue(BaseModel):
    year: int | None = None


@app.post('/api/v1/me/certificates', status_code=201)
def create_certificate(body: CertificateIssue, user=Depends(current_user), db: Session = Depends(get_db)):
    year = body.year or today().year
    try:
        row = issue_certificate(db, user, year)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return certificate_json(row)


@app.get('/api/v1/me/certificates/{certificate_id}')
def download_certificate(certificate_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(AffiliationCertificate, certificate_id)
    if not row or row.account_id != user.id:
        raise HTTPException(404, 'Certificate not found.')
    return Response(
        certificate_html(user, row),
        media_type='text/html; charset=utf-8',
        headers={'Content-Disposition': f'inline; filename="carecredits-{row.year}-{row.id[:8]}.html"'},
    )


@app.get('/api/v1/digest/unsubscribe')
def digest_unsubscribe(token: str, db: Session = Depends(get_db)):
    pref = db.query(DigestPreference).filter_by(unsubscribe_token=token).first()
    if not pref:
        raise HTTPException(404, 'Unsubscribe link is invalid or expired.')
    pref.opted_in = False
    pref.unsubscribed_at = time.time()
    db.commit()
    return {'opted_in': False, 'message': 'You are unsubscribed from CareCredits digests.'}


@app.post('/api/v1/admin/digests/run')
def admin_run_digests(user=Depends(operator), db: Session = Depends(get_db)):
    return run_due_digests(db)


@app.get('/api/v1/me/export/{kind}')
def export(kind: Literal['csv', 'eml'], user=Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Record, Course).join(Course, Record.course_id == Course.id).filter(Record.account_id == user.id).all()
    def cell(value):
        value = str(value or '')
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
    if kind == 'csv':
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['Training', 'Provider', 'Signed up', 'Attended', 'Completed on', 'Recorded points', 'Credit label', 'Source', 'Evidence status'])
        for r, c in rows:
            writer.writerow([cell(c.title), cell(c.provider), r.signed_up, r.attended, r.attended_on or '', r.points if r.points is not None else '', cell(r.credit_label), cell((c.data or {}).get('source_url')), 'Self-reported'])
        content, mime = stream.getvalue(), 'text/csv; charset=utf-8'
    else:
        message = EmailMessage()
        message['Subject'] = 'My CPD training record'
        message['X-Unsent'] = '1'
        lines = ['My personal training record (self-reported, not independently verified):', '']
        for r, c in rows:
            if r.attended:
                lines.append(f"{c.title} | {r.attended_on} | {r.points if r.points is not None else 'Not recorded'} {r.credit_label}")
        message.set_content('\n'.join(lines))
        content, mime = message.as_bytes(), 'message/rfc822'
    return Response(content, media_type=mime, headers={'Content-Disposition': f'attachment; filename="carecredits-record.{kind}"'})


@app.get('/api/v1/public/{slug}')
def public_profile(slug: str, db: Session = Depends(get_db)):
    account = db.query(Account).filter_by(public_slug=slug, public_enabled=True).first()
    if not account:
        raise HTTPException(404, 'This training profile is private or unavailable.')
    items = []
    for r, c in db.query(Record, Course).join(Course, Record.course_id == Course.id).filter(Record.account_id == account.id, Record.public.is_(True), Record.attended.is_(True)):
        items.append({'title': c.title, 'provider': c.provider, 'attended_on': r.attended_on, 'source_url': (c.data or {}).get('source_url'), 'demo': c.demo})
    return {'name': account.name, 'bio': account.bio, 'items': items, 'evidence_status': 'Self-reported training history; not independently verified.'}


def job_json(job):
    return {'id':job.id, 'query':job.query, 'status':job.status, 'created_at':job.created_at, 'result':job.result}


@app.post('/api/v1/admin/ingestion-jobs', status_code=202)
def create_job(body: NewJob, request: Request, user=Depends(operator), db: Session = Depends(get_db)):
    key = request.headers.get('Idempotency-Key', '')
    if not 8 <= len(key) <= 100:
        raise HTTPException(422, 'Supply an Idempotency-Key of 8–100 characters.')
    request_key = digest(user.id + ':' + key)
    existing = db.query(Job).filter_by(request_key=request_key).first()
    if existing:
        if existing.query != body.query:
            raise HTTPException(409, 'That request key belongs to another query.')
        return job_json(existing)
    throttle(db, 'jobs:' + user.id, 10, 3600)
    job = Job(account_id=user.id, request_key=request_key, query=body.query)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Request already received; refresh jobs.')
    return job_json(job)


def expire_jobs(db):
    db.execute(update(Job).where(Job.status == 'running', Job.lease_until < time.time()).values(status='interrupted', result={'warnings':['Worker lease expired. Retry explicitly to avoid hidden API spending.']}))
    db.commit()


@app.get('/api/v1/admin/ingestion-jobs')
def jobs(user=Depends(operator), db: Session = Depends(get_db)):
    expire_jobs(db)
    return {'items': [job_json(j) for j in db.query(Job).order_by(Job.created_at.desc()).limit(50)]}


@app.post('/api/v1/admin/ingestion-jobs/{job_id}/retry', status_code=202)
def retry_job(job_id: str, user=Depends(operator), db: Session = Depends(get_db)):
    expire_jobs(db)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, 'Job not found.')
    changed = db.execute(update(Job).where(Job.id == job.id, Job.status == 'interrupted').values(status='queued', lease_token=None, lease_until=None, started_at=None))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'Only interrupted jobs can be retried.')
    db.commit()
    return job_json(db.get(Job, job_id))


@app.get('/api/v1/admin/candidates')
def candidates(user=Depends(operator), db: Session = Depends(get_db)):
    return {'items':[{'id':c.id, 'data':c.data, 'status':c.status, 'reason':c.review_reason or ''} for c in db.query(Candidate).filter(Candidate.status.in_(['pending','held'])).limit(100)]}


@app.post('/api/v1/admin/candidates/{candidate_id}/review')
def review(candidate_id: str, body: Review, user=Depends(operator), db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter_by(id=candidate_id).with_for_update().first()
    if not candidate:
        raise HTTPException(404, 'Candidate not found.')
    if candidate.status not in ('pending', 'held'):
        return {'status': candidate.status, 'reason': candidate.review_reason or ''}
    reason = body.reason.strip()
    if body.action == 'publish':
        try:
            training = validate_evidence(Training(**candidate.data))
        except ValueError:
            raise HTTPException(422, 'Source evidence is incomplete. Reject or ingest a better source.')
        payload = training.model_dump(mode='json')
        course = db.query(Course).filter_by(source_key=candidate.source_key).first()
        if course:
            fill_course(course, payload)
        else:
            db.add(fill_course(Course(source_key=candidate.source_key), payload))
        candidate.status = 'published'
    elif body.action == 'hold':
        candidate.status = 'held'
    else:
        candidate.status = 'rejected'
    candidate.review_reason = reason
    candidate.reviewed_by = user.id
    audit(db, user.id, 'candidate_' + candidate.status, candidate.id, {'reason': reason})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Another review published this session. Refresh.')
    return {'status': candidate.status, 'reason': candidate.review_reason}


@app.post('/internal/v1/jobs/claim', dependencies=[Depends(worker)])
def claim(db: Session = Depends(get_db)):
    expire_jobs(db)
    # One worker process is the default; conditional claims also prevent double ownership.
    job = db.query(Job).filter_by(status='queued').order_by(Job.created_at).first()
    if not job:
        return Response(status_code=204)
    token = secrets.token_urlsafe(24)
    result = db.execute(update(Job).where(Job.id == job.id, Job.status == 'queued').values(status='running', lease_token=token, lease_until=time.time()+120, started_at=time.time()))
    db.commit()
    if result.rowcount != 1:
        return Response(status_code=204)
    return {'id':job.id, 'query':job.query, 'lease_token':token}


@app.post('/internal/v1/jobs/{job_id}/heartbeat', dependencies=[Depends(worker)])
def heartbeat(job_id: str, body: dict, db: Session = Depends(get_db)):
    now = time.time()
    result = db.execute(update(Job).where(Job.id == job_id, Job.status == 'running', Job.lease_token == body.get('lease_token'), Job.lease_until >= now, Job.started_at >= now-300).values(lease_until=now+120))
    db.commit()
    if result.rowcount != 1:
        raise HTTPException(409, 'Job lease is no longer active.')
    return {'ok': True}


@app.post('/internal/v1/jobs/{job_id}/complete', dependencies=[Depends(worker)])
def complete(job_id: str, body: CompleteJob, db: Session = Depends(get_db)):
    job = db.query(Job).filter_by(id=job_id).with_for_update().first()
    if not job or not secrets.compare_digest((job.lease_token or '').encode(), body.lease_token.encode()):
        raise HTTPException(409, 'Job lease does not match.')
    if job.status in ('succeeded', 'partial', 'failed'):
        return {'status': job.status}
    if job.status != 'running' or job.lease_until < time.time() or job.started_at < time.time()-300:
        raise HTTPException(409, 'Job lease expired.')
    changed = db.execute(update(Job).where(Job.id == job.id, Job.status == 'running').values(status=body.status))
    if changed.rowcount != 1:
        db.rollback()
        return {'status': db.get(Job, job_id).status}
    seen = set()
    for training in body.candidates:
        try:
            validate_evidence(training)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        data = training.model_dump(mode='json')
        key = source_key(data)
        if key not in seen:
            db.add(Candidate(job_id=job.id, source_key=key, data=data))
            seen.add(key)
    job.status = body.status
    job.result = {
        'candidate_count': len(seen),
        'warnings': [w[:500] for w in body.warnings],
        'usage': body.usage,
        'sources': [item.model_dump() for item in body.sources],
    }
    db.commit()
    return {'status': job.status}


@app.get('/internal/v1/catalogue/connect', dependencies=[Depends(worker)])
def catalogue_connect(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {
        'status': 'connected',
        'database': 'ready',
        'typesafe_configured': bool(typesafe_key()),
        'local_day': local_today(),
    }


@app.post('/internal/v1/catalogue/lookup', dependencies=[Depends(worker)])
def catalogue_lookup(body: CatalogueLookup, db: Session = Depends(get_db)):
    try:
        training = validate_evidence(body.candidate)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    data = training.model_dump(mode='json')
    key = source_key(data)
    exact = exact_course(db, key)
    neighbours = [] if exact else near_neighbours(db, data)
    return {
        'source_key': key,
        'exact': course_public(exact) if exact else None,
        'matches': [course_public(row) for row in neighbours],
    }


@app.post('/internal/v1/catalogue/decide', dependencies=[Depends(worker)])
def catalogue_decide(body: CatalogueDecide, db: Session = Depends(get_db)):
    try:
        training = validate_evidence(body.candidate)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    data = training.model_dump(mode='json')
    key = source_key(data)
    exact = exact_course(db, key)
    if exact:
        return {
            'decision': 'exists',
            'confidence': 1.0,
            'probabilities': {'exists': 1.0, 'new': 0.0, 'uncertain': 0.0},
            'matched_session_id': exact.id,
            'warning': None,
            'source_key': key,
        }
    matches = body.matches if body.matches is not None else [course_public(row) for row in near_neighbours(db, data)]
    try:
        judgment = decide_existence(data, matches)
    except JevError as exc:
        raise HTTPException(exc.status_code, exc.detail)
    judgment['source_key'] = key
    return judgment


@app.post('/internal/v1/catalogue/save', dependencies=[Depends(worker)])
def catalogue_save(body: CatalogueSave, db: Session = Depends(get_db)):
    try:
        training = validate_evidence(body.candidate)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    judgment = body.judgment or {}
    decision = judgment.get('decision')
    job = db.get(Job, body.job_id) if body.job_id else None
    if body.job_id and not job:
        raise HTTPException(404, 'Job not found.')
    account_id = job.account_id if job else None
    if not account_id:
        op = db.query(Account).filter_by(role='operator').order_by(Account.email).first()
        if not op:
            raise HTTPException(503, 'No operator account available to own catalogue saves.')
        account_id = op.id
    data = training.model_dump(mode='json')
    key = source_key(data)
    if decision == 'exists':
        matched_id = judgment.get('matched_session_id')
        course = db.get(Course, matched_id) if matched_id else exact_course(db, key)
        if not course:
            raise HTTPException(404, 'Matched catalogue session was not found.')
        candidate = link_existing(db, account_id, training, course, judgment, body.job_id)
        db.commit()
        return {'status': 'exists', 'candidate_id': candidate.id, 'course_id': course.id, 'decision': 'exists'}
    if decision == 'uncertain':
        candidate = save_new_candidate(db, account_id, training, judgment, body.job_id)
        db.commit()
        return {'status': 'held', 'candidate_id': candidate.id, 'decision': 'uncertain'}
    if decision != 'new':
        raise HTTPException(422, 'Judgment decision must be exists, new, or uncertain.')
    try:
        candidate, course = publish_new_event(db, account_id, training, judgment, body.job_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return {'status': 'published', 'candidate_id': candidate.id, 'course_id': course.id, 'decision': 'new'}


@app.post('/api/v1/admin/daily-scrape', status_code=202)
def trigger_daily_scrape(force: bool = False, user=Depends(operator), db: Session = Depends(get_db)):
    result = enqueue_daily(db, force=force)
    if result.get('error'):
        raise HTTPException(503, result['error'])
    return result
