"""Biweekly digest compose + send (NTF-01 / DEC-10). Never calls Tavily."""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from portal_models import Account, Course, DigestPreference, DigestSend, Record, uid
from security import digest as hash_digest


TZ = ZoneInfo('Asia/Kuala_Lumpur')
DISCLAIMER = (
    'CareCredits digests summarise catalogue listings and your self-reported progress. '
    'They are not MMC, MOH, or APC compliance statements.'
)


def local_now() -> datetime:
    return datetime.now(TZ)


def progress_snapshot(db: Session, account_id: str, year: int | None = None) -> dict:
    year = year or local_now().year
    records = db.query(Record).filter_by(account_id=account_id).all()
    attended = [r for r in records if r.attended and r.attended_on and r.attended_on.startswith(str(year))]
    countable = [r for r in attended if r.points is not None and r.credit_label.strip().upper() == 'CPD']
    return {
        'year': year,
        'signed_up': sum(1 for r in records if r.signed_up and not r.attended),
        'attended': len(attended),
        'points': round(sum(r.points for r in countable), 2),
        'excluded': len(attended) - len(countable),
    }


def upcoming_sessions(db: Session, city: str | None, limit: int = 8) -> list[dict]:
    today = local_now().date().isoformat()
    query = db.query(Course).filter(Course.start_date != None, Course.start_date >= today)
    if city:
        same_city = query.filter(Course.city == city).order_by(Course.start_date).limit(limit).all()
        if same_city:
            rows = same_city
        else:
            rows = query.order_by(Course.start_date).limit(limit).all()
    else:
        rows = query.order_by(Course.start_date).limit(limit).all()
    items = []
    for course in rows:
        fee = course.fee
        items.append({
            'id': course.id,
            'title': course.title,
            'provider': course.provider,
            'start_date': course.start_date,
            'city': course.city,
            'mode': course.mode,
            'fee': fee,
            'currency': course.currency,
            'price_label': (
                f'{int(fee) if float(fee).is_integer() else fee} {course.currency or "MYR"}'
                if fee is not None else 'Price unknown'
            ),
            'points': course.points,
            'credit_label': course.credit_label,
        })
    return items


def compose_digest(db: Session, account: Account) -> dict:
    progress = progress_snapshot(db, account.id)
    sessions = upcoming_sessions(db, account.city)
    return {
        'to': account.email,
        'name': account.name,
        'city': account.city,
        'progress': progress,
        'sessions': sessions,
        'disclaimer': DISCLAIMER,
        'composed_at': local_now().isoformat(),
    }


def render_text(payload: dict, unsubscribe_url: str) -> str:
    progress = payload['progress']
    lines = [
        f"Hi {payload['name']},",
        '',
        f"Your CareCredits digest for {progress['year']}:",
        f"- Recorded CPD points: {progress['points']}",
        f"- Attended this year: {progress['attended']}",
        f"- Signed up (not yet attended): {progress['signed_up']}",
        f"- Excluded from CPD total: {progress['excluded']}",
        '',
        'Upcoming catalogue sessions:',
    ]
    if not payload['sessions']:
        lines.append('- None listed yet. Check the portal after the next daily catalogue refresh.')
    for item in payload['sessions']:
        points = f"{item['points']} {item['credit_label'] or 'CPD'}" if item['points'] is not None else 'points unknown'
        lines.append(
            f"- {item['start_date']} | {item['title']} ({item['provider']}) | "
            f"{item['city'] or item['mode']} | {item['price_label']} | {points}"
        )
    lines.extend(['', DISCLAIMER, '', f'Unsubscribe: {unsubscribe_url}', ''])
    return '\n'.join(lines)


def send_via_provider(to: str, subject: str, body: str) -> dict:
    provider = (os.getenv('MAIL_PROVIDER') or 'log').strip().lower()
    if provider == 'log':
        out = Path(os.getenv('DIGEST_LOG_DIR') or Path(__file__).resolve().parents[1] / '.data' / 'digests')
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(TZ).strftime('%Y%m%d-%H%M%S')
        path = out / f'{stamp}-{hash_digest(to)[:12]}.txt'
        path.write_text(f'To: {to}\nSubject: {subject}\n\n{body}', encoding='utf-8')
        return {'status': 'sent', 'provider_message_id': str(path), 'error': ''}
    if provider == 'smtp':
        import smtplib
        from email.message import EmailMessage

        host = os.getenv('SMTP_HOST') or ''
        port = int(os.getenv('SMTP_PORT') or '587')
        user = os.getenv('SMTP_USER') or ''
        password = os.getenv('SMTP_PASSWORD') or ''
        from_addr = os.getenv('SMTP_FROM') or user
        if not host or not from_addr:
            return {'status': 'failed', 'provider_message_id': None, 'error': 'SMTP is not configured.'}
        message = EmailMessage()
        message['Subject'] = subject
        message['From'] = from_addr
        message['To'] = to
        message.set_content(body)
        with smtplib.SMTP(host, port, timeout=20) as client:
            client.starttls()
            if user:
                client.login(user, password)
            client.send_message(message)
        return {'status': 'sent', 'provider_message_id': f'smtp:{to}', 'error': ''}
    return {'status': 'failed', 'provider_message_id': None, 'error': f'Unknown MAIL_PROVIDER={provider}'}


def ensure_preference(db: Session, account_id: str) -> DigestPreference:
    pref = db.get(DigestPreference, account_id)
    if pref:
        return pref
    pref = DigestPreference(account_id=account_id, unsubscribe_token=uid())
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


def preference_json(pref: DigestPreference) -> dict:
    return {
        'opted_in': pref.opted_in,
        'cadence_days': pref.cadence_days,
        'last_sent_at': pref.last_sent_at,
        'unsubscribed_at': pref.unsubscribed_at,
    }


def due_preferences(db: Session, now: float | None = None) -> list[DigestPreference]:
    now = now if now is not None else time.time()
    rows = db.query(DigestPreference).filter_by(opted_in=True).all()
    due = []
    for pref in rows:
        cadence = max(1, pref.cadence_days or 14) * 86400
        if pref.last_sent_at is None or (now - pref.last_sent_at) >= cadence:
            due.append(pref)
    return due


def send_digest(db: Session, account: Account, pref: DigestPreference, public_base: str) -> DigestSend:
    payload = compose_digest(db, account)
    unsub = f"{public_base.rstrip('/')}/api/v1/digest/unsubscribe?token={pref.unsubscribe_token}"
    body = render_text(payload, unsub)
    subject = f"CareCredits digest — {payload['progress']['year']} progress + upcoming CPD"
    result = send_via_provider(account.email, subject, body)
    row = DigestSend(
        account_id=account.id,
        status=result['status'],
        provider_message_id=result.get('provider_message_id'),
        error=result.get('error') or '',
        payload=payload,
    )
    db.add(row)
    if result['status'] == 'sent':
        pref.last_sent_at = time.time()
    db.commit()
    db.refresh(row)
    return row


def run_due_digests(db: Session, public_base: str | None = None) -> dict:
    base = public_base or os.getenv('PUBLIC_API_BASE') or 'http://127.0.0.1:8000'
    sent = 0
    failed = 0
    for pref in due_preferences(db):
        account = db.get(Account, pref.account_id)
        if not account or account.role != 'doctor':
            continue
        row = send_digest(db, account, pref, base)
        if row.status == 'sent':
            sent += 1
        else:
            failed += 1
    return {'sent': sent, 'failed': failed, 'day': local_now().date().isoformat()}
