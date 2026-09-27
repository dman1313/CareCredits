"""Explicit fictional fixtures. Loaded only with DEMO_MODE=true outside production."""
from datetime import timedelta
from portal_models import Account, Candidate, Course, Job, Record, fill_course
from security import password_hash
from shared.contracts import Training


REVIEW_QUOTE = (
    'Fictional demo CME: Asthma updates for GPs by Demo CME Network in Malaysia Kuala Lumpur online. '
    '2026-06-15. CPD points 3. Demonstration source only — not a live Tavily or model result.'
)


def _candidate_payload(title, start_date, source_key_suffix):
    training = Training(
        title=title,
        provider='Demo CME Network',
        description='Fictional candidate for operator review rehearsal. Not a live discovery result.',
        start_date=start_date,
        city='Kuala Lumpur',
        mode='online',
        country='MY',
        points=3,
        credit_label='CPD',
        difficulty='intermediate',
        fee=120,
        currency='MYR',
        source_url='https://example.org/carecredits-demo-candidate-' + source_key_suffix,
        registration_url='https://example.org/carecredits-demo-candidate-' + source_key_suffix + '/register',
        source_text=REVIEW_QUOTE,
        evidence={
            key: REVIEW_QUOTE
            for key in (
                'title',
                'provider',
                'mode',
                'country',
                'start_date',
                'city',
                'points',
                'credit_label',
                'difficulty',
                'fee',
                'currency',
            )
        },
    )
    return training.model_dump(mode='json')


def seed(db):
    from main import today

    demo_hash = password_hash('CareCredits-demo-2026')
    for email, name, role in [
        ('demo@carecredits.local', 'Dr Aisha Rahman', 'operator'),
        ('doctor@carecredits.local', 'Dr Daniel Tan', 'doctor'),
    ]:
        existing = db.query(Account).filter_by(email=email).first()
        if existing:
            existing.password_hash = demo_hash
            existing.name = name
            existing.role = role
        else:
            db.add(
                Account(
                    email=email,
                    name=name,
                    role=role,
                    password_hash=demo_hash,
                    bio='General practitioner · committed to continuing professional development.',
                )
            )
    db.flush()
    operator = db.query(Account).filter_by(email='demo@carecredits.local').one()
    doctor = db.query(Account).filter_by(email='doctor@carecredits.local').one()

    items = [
        ('Diabetes care in general practice', 'Primary Care Learning Lab', 12, 'Kuala Lumpur', 'in_person', 180, 4, 'intermediate', 3.139, 101.687),
        ('Everyday dermatology for GPs', 'Community Medicine Academy', 21, 'Petaling Jaya', 'hybrid', 250, 6, 'beginner', 3.107, 101.606),
        ('ECG essentials: a practical refresher', 'Clinical Skills Collective', 8, None, 'online', 0, 2, 'beginner', None, None),
        ('A better approach to hypertension', 'Primary Care Learning Lab', -10, 'Kuala Lumpur', 'in_person', 150, 3, 'intermediate', 3.15, 101.71),
        ('Communication in primary care', 'Community Medicine Academy', -30, None, 'online', 80, 2, 'beginner', None, None),
        ('Preventive care across the lifespan', 'Clinical Skills Collective', 35, 'Shah Alam', 'in_person', None, None, None, 3.074, 101.518),
    ]
    course_ids = {}
    for i, (title, provider, offset, city, mode, fee, points, difficulty, lat, lon) in enumerate(items):
        key = 'demo-' + str(i)
        registration = 'https://example.org/carecredits-demo-' + str(i) + '/register'
        training = Training(
            title=title,
            provider=provider,
            description='Fictional demonstration training for testing the CareCredits workflow. This is not a real course or accreditation claim.',
            start_date=today() + timedelta(days=offset),
            city=city,
            state='Selangor' if city and city != 'Kuala Lumpur' else None,
            mode=mode,
            latitude=lat,
            longitude=lon,
            fee=fee,
            currency='MYR' if fee is not None else None,
            points=points,
            credit_label='CPD' if points is not None else None,
            difficulty=difficulty,
            prerequisites='For demonstration purposes only',
            source_url='https://example.org/carecredits-demo-' + str(i),
            registration_url=registration,
        )
        payload = training.model_dump(mode='json')
        existing = db.query(Course).filter_by(source_key=key).first()
        if existing:
            # Keep demo IDs stable while refreshing labelled registration links for DEMO-01 step 6.
            fill_course(existing, {**(existing.data or {}), **payload, 'registration_url': registration}, demo=True)
            course_ids[i] = existing.id
            continue
        course = fill_course(Course(source_key=key), payload, demo=True)
        db.add(course)
        db.flush()
        course_ids[i] = course.id

    # Offline DEMO-01 steps 3–4: pending labelled candidates for /live review (no Tavily/model).
    pending = (
        db.query(Candidate)
        .filter(Candidate.status == 'pending', Candidate.source_key.like('demo-candidate-%'))
        .count()
    )
    fixture_result = {
        'extraction_status': 'fixture',
        'candidate_count': 2,
        'warnings': [
            'FIXTURE: fictional demo candidates for offline review. Not a Tavily Search/Extract or model run.',
        ],
        'sources': [
            {
                'url': 'https://example.org/carecredits-demo-candidate-asthma',
                'title': 'Asthma updates for GPs (demo)',
                'snippet': 'Demonstration source only — not a live Tavily or model result.',
                'extraction_status': 'fixture',
                'verification_status': 'unverified',
            },
            {
                'url': 'https://example.org/carecredits-demo-candidate-vaccine',
                'title': 'Adult vaccination clinic skills (demo)',
                'snippet': 'Demonstration source only — not a live Tavily or model result.',
                'extraction_status': 'fixture',
                'verification_status': 'unverified',
            },
        ],
        'usage': {'tavily_credits': None, 'model_tokens': None},
    }
    job = db.query(Job).filter_by(request_key='demo-review-queue').first()
    if not job:
        job = Job(
            account_id=operator.id,
            request_key='demo-review-queue',
            query='Demo review queue (fictional fixtures)',
            status='succeeded',
            max_results=2,
            result=fixture_result,
        )
        db.add(job)
        db.flush()
    else:
        job.result = fixture_result
        job.status = 'succeeded'
        job.query = 'Demo review queue (fictional fixtures)'
    if pending == 0:
        db.query(Candidate).filter_by(job_id=job.id).delete()
        for title, suffix, offset in (
            ('Asthma updates for GPs (demo)', 'asthma', 40),
            ('Adult vaccination clinic skills (demo)', 'vaccine', 55),
        ):
            payload = _candidate_payload(title, str(today() + timedelta(days=offset)), suffix)
            payload['_fixture'] = True
            db.add(
                Candidate(
                    job_id=job.id,
                    source_key='demo-candidate-' + suffix,
                    data=payload,
                    status='pending',
                )
            )

    # Offline DEMO-01 step 7: personal records on both documented accounts (operator for /live review flow,
    # doctor for a pure doctor login). Seed once per account/course.
    past = today() + timedelta(days=-10)
    for account in (operator, doctor):
        if 2 in course_ids and not db.query(Record).filter_by(account_id=account.id, course_id=course_ids[2]).first():
            db.add(
                Record(
                    account_id=account.id,
                    course_id=course_ids[2],
                    signed_up=True,
                    signup_status='signed_up',
                    attendance_status='not_recorded',
                )
            )
        if 3 in course_ids and not db.query(Record).filter_by(account_id=account.id, course_id=course_ids[3]).first():
            db.add(
                Record(
                    account_id=account.id,
                    course_id=course_ids[3],
                    signed_up=True,
                    signup_status='signed_up',
                    attended=True,
                    attendance_status='attended',
                    attended_on=past.isoformat(),
                    points=3,
                    credit_label='CPD',
                    points_origin='self_reported',
                )
            )
    db.commit()
