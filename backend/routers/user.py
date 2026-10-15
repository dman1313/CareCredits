from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.repository.user_repository import UserRepository
from backend.services.point_progress_service import PointProgressService
from security import current_user
from shared.contracts import public_web_url
import csv, io
from email.message import EmailMessage


router = APIRouter(prefix="/api/v1/me", tags=["user"])

# === Endpoints ===
@router.get("")
def me(user=Depends(current_user), db: Session = Depends(get_db)):
    repo = UserRepository(db)
    profile = repo.get_profile(user.id)
    if not profile:
        raise HTTPException(404, "User profile not found.")
    return profile

@router.get("/progress")
def progress(
    year: int | None = None,
    timezone: str = "UTC",
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    """
    Returns CPD progress using PointProgressService.
    Year defaults to current year in user's timezone.
    """
    from zoneinfo import ZoneInfo, available_timezones
    from datetime import datetime
    
    tz_name = timezone if timezone in available_timezones() else "UTC"
    tz = ZoneInfo(tz_name)
    current_year_in_tz = datetime.now(tz).year
    effective_year = year if year is not None else current_year_in_tz
    
    if not 1900 <= effective_year <= 2200:
        raise HTTPException(422, "Invalid year.")
    
    service = PointProgressService(db)
    return service.get_yearly_snapshot(user.id, effective_year)


# TECHNICAL DEBT: Cross-domain export logic in router.
# Post-hackathon: Extract to ExportService with RecordRepository + CourseRepository coordination.
@router.get("/export/{kind}")
def export(
    kind: Literal["csv", "eml"],
    year: int | None = None,
    timezone: str = "UTC",
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    from models.record import Record
    from models.course import Course
    from zoneinfo import ZoneInfo, available_timezones
    from datetime import datetime
    
    tz_name = timezone if timezone in available_timezones() else "UTC"
    tz = ZoneInfo(tz_name)
    current_year_in_tz = datetime.now(tz).year
    effective_year = year if year is not None else current_year_in_tz
    
    if year is not None and not 1900 <= year <= 2200:
        raise HTTPException(422, "Invalid year.")
    
    rows = db.query(Record, Course).join(Course, Record.course_id == Course.id).filter(Record.account_id == user.id).all()
    
    if effective_year is not None:
        year_key = str(effective_year)
        scoped = []
        for r, c in rows:
            attended = getattr(r, "attendance_status", None) == "attended" or bool(r.attended)
            if attended:
                if r.attended_on:
                    attended_dt = datetime.fromtimestamp(r.attended_on, tz=tz)
                    if str(attended_dt.year) == year_key:
                        scoped.append((r, c))
            else:
                if (c.start_date or "").startswith(year_key):
                    scoped.append((r, c))
        rows = scoped

    def cell(value):
        value = str(value or "")
        visible = value.lstrip(" \t\r\n\x0b\x0c\ufeff\u200b\u200c\u200d\u2060\u00a0\u1680\u180e\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u00ad\u034f\u061c")
        starters = ("=", "+", "-", "@", "\uff1d", "\uff0b", "\uff0d", "\uff20", "\u2212", "\ufe63")
        return "'" + value if visible[:1] in starters else value

    suffix = f"-{effective_year}" if effective_year is not None else ""
    if kind == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["Training", "Provider", "Session date", "Signed up", "Signup status", "Attended", "Attendance status", "Completed on", "Recorded points", "Credit label", "Source", "Evidence status"])
        for r, c in rows:
            signup_status = getattr(r, "signup_status", None) or ("signed_up" if r.signed_up else "not_recorded")
            attendance_status = getattr(r, "attendance_status", None) or ("attended" if r.attended else "not_recorded")
            attended = attendance_status == "attended" or bool(r.attended)
            signed_up = signup_status != "cancelled" and (signup_status == "signed_up" or bool(r.signed_up))
            writer.writerow([cell(c.title), cell(c.provider), cell(c.start_date or ""), signed_up, cell(signup_status), attended, cell(attendance_status), cell(r.attended_on or ""), r.points if r.points is not None else "", cell(r.credit_label), cell(public_web_url((c.data or {}).get("source_url")) or ""), "Self-reported"])
        content, mime = stream.getvalue(), "text/csv; charset=utf-8"
    else:
        message = EmailMessage()
        subject_year = f" ({effective_year})" if effective_year is not None else ""
        message["Subject"] = f"My CPD training record{subject_year}"
        message["X-Unsent"] = "1"
        lines = ["My personal training record (self-reported, not independently verified):", ""]
        if effective_year is not None:
            lines.append(f"Year filter: {effective_year}")
            lines.append("")
        attended_lines = [f"{c.title} | {r.attended_on} | {r.points if r.points is not None else 'Not recorded'} {r.credit_label}" for r, c in rows if getattr(r, "attendance_status", None) == "attended" or r.attended]
        if attended_lines:
            lines.extend(attended_lines)
        else:
            lines.append(f"No attended records for {effective_year}." if effective_year is not None else "No attended records yet.")
        message.set_content("\n".join(lines))
        content, mime = message.as_bytes(), "message/rfc822"
    return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="carecredits-record{suffix}.{kind}"'})


@router.get("/audit")
def my_audit(page: int = 1, page_size: int = 20, user=Depends(current_user), db: Session = Depends(get_db)):
    repo = UserRepository(db)
    try:
        return repo.get_audit_paginated(user.id, page, page_size)
    except ValueError as e:
        raise HTTPException(422, str(e))