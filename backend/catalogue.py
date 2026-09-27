"""Owned-catalogue connect helpers: lookup near neighbours and save new events."""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from portal_models import Candidate, Course, Job, uid, fill_course, CANDIDATE_SCHEMA_VERSION, FILTER_FIELDS
from security import digest
from shared.contracts import Training, validate_evidence

REFRESH_FIELDS = FILTER_FIELDS + ('prerequisites', 'registration_url')


def training_payload(data: dict) -> dict:
    return {key: value for key, value in (data or {}).items() if not str(key).startswith('_')}


def resolve_review_course(db: Session, candidate: Candidate) -> Course | None:
    data = candidate.data or {}
    matched_id = candidate.resulting_course_id or data.get('_matched_course_id')
    if matched_id:
        course = db.get(Course, matched_id)
        if course:
            return course
    return exact_course(db, candidate.source_key)


def course_compare_value(course: Course, field: str):
    if field in ('prerequisites', 'registration_url'):
        return (course.data or {}).get(field)
    return getattr(course, field, None)


def refresh_diff(course: Course, data: dict) -> list[dict]:
    changes = []
    for field in REFRESH_FIELDS:
        published = course_compare_value(course, field)
        proposed = data.get(field)
        if published != proposed:
            changes.append({'field': field, 'published': published, 'proposed': proposed})
    return changes


def source_key(data: dict) -> str:
    return digest(
        data['source_url'].split('#')[0]
        + '|'
        + data['title'].strip().lower()
        + '|'
        + str(data.get('start_date'))
    )


def course_public(course: Course) -> dict:
    data = dict(course.data or {})
    return {
        'id': course.id,
        'title': course.title,
        'provider': course.provider,
        'start_date': course.start_date,
        'city': course.city,
        'mode': course.mode,
        'source_url': data.get('source_url'),
        'source_key': course.source_key,
        'data': {'source_url': data.get('source_url')},
    }


def exact_course(db: Session, key: str) -> Course | None:
    return db.query(Course).filter_by(source_key=key).first()


def near_neighbours(db: Session, candidate: dict, limit: int = 5) -> list[Course]:
    title = (candidate.get('title') or '').strip()
    provider = (candidate.get('provider') or '').strip()
    city = (candidate.get('city') or '').strip()
    start = str(candidate.get('start_date') or '')
    clauses = []
    if provider:
        clauses.append(Course.provider.ilike('%' + provider[:80] + '%'))
    if title:
        token = title.split()[0][:40]
        if len(token) >= 3:
            clauses.append(Course.title.ilike('%' + token + '%'))
    if city:
        clauses.append(Course.city.ilike('%' + city[:80] + '%'))
    if start:
        clauses.append(Course.start_date == start)
    if not clauses:
        return []
    rows = db.query(Course).filter(or_(*clauses)).order_by(Course.updated_at.desc()).limit(limit * 3).all()
    scored = []
    for row in rows:
        score = 0
        if provider and provider.lower() in (row.provider or '').lower():
            score += 3
        if title and title.lower()[:20] in (row.title or '').lower():
            score += 3
        if city and city.lower() == (row.city or '').lower():
            score += 1
        if start and start == (row.start_date or ''):
            score += 2
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], -(item[1].updated_at or 0)))
    # Require a strong overlap (provider+title-ish or title+date) before Jev near-match.
    return [row for score, row in scored if score >= 5][:limit]


def ensure_job(db: Session, account_id: str, query: str = 'catalogue-save') -> Job:
    job = Job(account_id=account_id, request_key='save-' + uid(), query=query)
    db.add(job)
    db.flush()
    return job


def save_new_candidate(db: Session, account_id: str, training: Training, judgment: dict, job_id: str | None = None) -> Candidate:
    data = validate_evidence(training).model_dump(mode='json')
    key = source_key(data)
    if exact_course(db, key):
        raise ValueError('Event already exists in the catalogue.')
    existing = db.query(Candidate).filter_by(source_key=key).filter(Candidate.status.in_(['pending', 'held'])).first()
    if existing:
        existing.data = {**data, '_judgment': judgment}
        return existing
    if not job_id:
        job_id = ensure_job(db, account_id).id
    status = 'pending'
    if judgment.get('decision') == 'uncertain':
        status = 'held'
    candidate = Candidate(
        job_id=job_id,
        source_key=key,
        data={**data, '_judgment': judgment},
        status=status,
        schema_version=CANDIDATE_SCHEMA_VERSION,
        review_reason=('Jev uncertain: ' + str(judgment.get('warning') or 'needs operator review'))[:500]
        if status == 'held'
        else '',
    )
    db.add(candidate)
    db.flush()
    return candidate


def publish_new_event(db: Session, account_id: str, training: Training, judgment: dict, job_id: str | None = None) -> tuple[Candidate, Course]:
    """Persist a Jev `new` decision into the searchable owned catalogue."""
    data = validate_evidence(training).model_dump(mode='json')
    key = source_key(data)
    if exact_course(db, key):
        raise ValueError('Event already exists in the catalogue.')
    if not job_id:
        job_id = ensure_job(db, account_id).id
    course = fill_course(Course(source_key=key), data, demo=False)
    db.add(course)
    candidate = Candidate(
        job_id=job_id,
        source_key=key,
        data={**data, '_judgment': judgment},
        status='published',
        schema_version=CANDIDATE_SCHEMA_VERSION,
        resulting_course_id=course.id,
        review_reason='Published via Jev decision=new',
    )
    db.add(candidate)
    db.flush()
    return candidate, course


def link_existing(db: Session, account_id: str, training: Training, course: Course, judgment: dict, job_id: str | None = None) -> Candidate:
    data = validate_evidence(training).model_dump(mode='json')
    key = source_key(data)
    if not job_id:
        job_id = ensure_job(db, account_id, 'catalogue-refresh').id
    candidate = Candidate(
        job_id=job_id,
        source_key=key,
        data={
            **data,
            '_judgment': judgment,
            '_matched_course_id': course.id,
            '_refresh_diff': refresh_diff(course, data),
        },
        status='held',
        schema_version=CANDIDATE_SCHEMA_VERSION,
        resulting_course_id=course.id,
        review_reason='Jev marked exists; review refresh before overwriting published fields.',
    )
    db.add(candidate)
    db.flush()
    return candidate
