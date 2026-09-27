"""Explicit fictional fixtures. Loaded only with DEMO_MODE=true outside production."""
from datetime import timedelta
from portal_models import Account, Course, fill_course
from security import password_hash
from shared.contracts import Training


def seed(db):
    from main import today
    demo_hash = password_hash('CareCredits-demo-2026')
    for email, name, role in [('demo@carecredits.local', 'Dr Aisha Rahman', 'operator'), ('doctor@carecredits.local', 'Dr Daniel Tan', 'doctor')]:
        existing = db.query(Account).filter_by(email=email).first()
        if existing:
            existing.password_hash = demo_hash
            existing.name = name
            existing.role = role
        else:
            db.add(Account(email=email, name=name, role=role, password_hash=demo_hash, bio='General practitioner · committed to continuing professional development.'))
    items = [
        ('Diabetes care in general practice', 'Primary Care Learning Lab', 12, 'Kuala Lumpur', 'in_person', 180, 4, 'intermediate', 3.139, 101.687),
        ('Everyday dermatology for GPs', 'Community Medicine Academy', 21, 'Petaling Jaya', 'hybrid', 250, 6, 'beginner', 3.107, 101.606),
        ('ECG essentials: a practical refresher', 'Clinical Skills Collective', 8, None, 'online', 0, 2, 'beginner', None, None),
        ('A better approach to hypertension', 'Primary Care Learning Lab', -10, 'Kuala Lumpur', 'in_person', 150, 3, 'intermediate', 3.15, 101.71),
        ('Communication in primary care', 'Community Medicine Academy', -30, None, 'online', 80, 2, 'beginner', None, None),
        ('Preventive care across the lifespan', 'Clinical Skills Collective', 35, 'Shah Alam', 'in_person', None, None, None, 3.074, 101.518),
    ]
    for i, (title, provider, offset, city, mode, fee, points, difficulty, lat, lon) in enumerate(items):
        key = 'demo-' + str(i)
        if db.query(Course).filter_by(source_key=key).first():
            continue
        training = Training(title=title, provider=provider, description='Fictional demonstration training for testing the CareCredits workflow. This is not a real course or accreditation claim.', start_date=today()+timedelta(days=offset), city=city, state='Selangor' if city and city != 'Kuala Lumpur' else None, mode=mode, latitude=lat, longitude=lon, fee=fee, currency='MYR' if fee is not None else None, points=points, credit_label='CPD' if points is not None else None, difficulty=difficulty, prerequisites='For demonstration purposes only', source_url='https://example.org/carecredits-demo-'+str(i))
        db.add(fill_course(Course(source_key=key), training.model_dump(mode='json'), demo=True))
    db.commit()
