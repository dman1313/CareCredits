"""Suggested upcoming catalogue sessions (PROG-02). Advisory only."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from portal_models import Account, Course, Record, listed_filter


TZ = ZoneInfo('Asia/Kuala_Lumpur')
ADVISORY = (
    'Suggestions are advisory only. CareCredits does not decide MMC/MOH/APC compliance.'
)


def suggestions_for(db: Session, account: Account, limit: int = 10) -> dict:
    today = datetime.now(TZ).date().isoformat()
    attended_ids = {
        r.course_id
        for r in db.query(Record).filter_by(account_id=account.id, attended=True).all()
    }
    signed_ids = {
        r.course_id
        for r in db.query(Record).filter_by(account_id=account.id, signed_up=True).all()
    }
    skip = attended_ids | signed_ids
    base = db.query(Course).filter(listed_filter(), Course.start_date != None, Course.start_date >= today)
    city_rows = []
    if account.city:
        city_rows = (
            base.filter(Course.city == account.city)
            .order_by(Course.start_date)
            .limit(limit * 2)
            .all()
        )
    other = base.order_by(Course.start_date).limit(limit * 3).all()
    seen = set()
    ordered = []
    for course in city_rows + other:
        if course.id in skip or course.id in seen:
            continue
        seen.add(course.id)
        ordered.append(course)
        if len(ordered) >= limit:
            break
    items = []
    for course in ordered:
        items.append({
            'id': course.id,
            'title': course.title,
            'provider': course.provider,
            'start_date': course.start_date,
            'city': course.city,
            'mode': course.mode,
            'fee': course.fee,
            'currency': course.currency,
            'points': course.points,
            'credit_label': course.credit_label,
            'reason': 'Matches your city' if account.city and course.city == account.city else 'Upcoming catalogue listing',
        })
    return {'items': items, 'advisory': ADVISORY, 'city': account.city}
