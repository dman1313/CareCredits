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
    records = db.query(Record).filter_by(account_id=account.id).all()
    attended_ids = {r.course_id for r in records if r.attended}
    signed_ids = {r.course_id for r in records if r.signed_up}
    skip = attended_ids | signed_ids
    recent_modes = []
    if attended_ids:
        recent_modes = [
            course.mode
            for course in db.query(Course).filter(Course.id.in_(attended_ids)).all()
            if course.mode
        ]
    preferred_mode = max(set(recent_modes), key=recent_modes.count) if recent_modes else None
    base = db.query(Course).filter(listed_filter(), Course.start_date != None, Course.start_date >= today)
    buckets = []
    if account.city and preferred_mode:
        buckets.append(base.filter(Course.city == account.city, Course.mode == preferred_mode).order_by(Course.start_date).limit(limit).all())
    if account.city:
        buckets.append(base.filter(Course.city == account.city).order_by(Course.start_date).limit(limit * 2).all())
    if preferred_mode:
        buckets.append(base.filter(Course.mode == preferred_mode).order_by(Course.start_date).limit(limit).all())
    buckets.append(base.order_by(Course.start_date).limit(limit * 3).all())
    seen = set()
    ordered = []
    for group in buckets:
        for course in group:
            if course.id in skip or course.id in seen:
                continue
            seen.add(course.id)
            ordered.append(course)
            if len(ordered) >= limit:
                break
        if len(ordered) >= limit:
            break
    items = []
    for course in ordered:
        city_match = bool(account.city and course.city == account.city)
        mode_match = bool(preferred_mode and course.mode == preferred_mode)
        if city_match and mode_match:
            reason = 'Matches your city and recent learning mode'
        elif city_match:
            reason = 'Matches your city'
        elif mode_match:
            reason = 'Matches a recent learning mode'
        else:
            reason = 'Upcoming catalogue listing'
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
            'reason': reason,
        })
    return {'items': items, 'advisory': ADVISORY, 'city': account.city, 'preferred_mode': preferred_mode}
