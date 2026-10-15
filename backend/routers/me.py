from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from backend.database.database import get_db
from models import Account, Audit, DigestPreference, AffiliationCertificate
from security import current_user, operator
from shared.contracts import public_web_url
from errors import envelope
import time, csv, io
from email.message import EmailMessage


router = APIRouter(prefix="/api/v1/me", tags=["me"])


# === Schemas ===
class ProfileChange(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    city: str = Field(max_length=100)
    state: str = Field(default="", max_length=100)
    bio: str = Field(max_length=1000)
    public_enabled: bool
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def name_check(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if len(cleaned) < 2 or len(cleaned) > 100:
            raise ValueError("Enter a display name of 2–100 characters.")
        return cleaned

    @field_validator("city", "state", "bio")
    @classmethod
    def trim_text(cls, value):
        return (value or "").strip() if isinstance(value, str) else value

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def coordinates_reject_bool(cls, value):
        if isinstance(value, bool):
            raise ValueError("Coordinates must be numbers.")
        return value

    @model_validator(mode="after")
    def coordinates_together(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together.")
        return self


class DigestChange(BaseModel):
    opted_in: bool
    cadence_days: int | None = Field(default=None, ge=7, le=60)


class CertificateIssue(BaseModel):
    year: int | None = Field(default=None, ge=1900, le=2200)


# === Helpers ===
def _profile(account: Account) -> dict:
    return {
        k: getattr(account, k)
        for k in ("id", "email", "name", "city", "state", "latitude", "longitude",
                   "location_consent_at", "created_at", "role", "bio", "public_enabled", "public_slug")
    }


# === Endpoints ===
@router.get("")
def me(user=Depends(current_user)):
    return _profile(user)


@router.patch("")
def change_profile(body: ProfileChange, user=Depends(current_user), db: Session = Depends(get_db)):
    values = body.model_dump()
    user.latitude = values.pop("latitude")
    user.longitude = values.pop("longitude")
    user.location_consent_at = time.time() if user.latitude is not None else None
    for k, v in values.items():
        setattr(user, k, v)
    db.add(Audit(
        account_id=user.id, action="profile_changed", entity_id=user.id,
        changed={"public_enabled": body.public_enabled}
    ))
    db.commit()
    return _profile(user)


@router.get("/progress")
def progress(year: int | None = None, user=Depends(current_user), db: Session = Depends(get_db)):
    # TODO: Replace with PointProgressService after implementation
    from digest import progress_snapshot
    from zoneinfo import ZoneInfo
    from datetime import datetime
    today_year = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).year
    year = today_year if year is None else year
    if not 1900 <= year <= 2200:
        raise HTTPException(422, "Invalid year.")
    return progress_snapshot(db, user.id, year)


@router.get("/suggestions")
def me_suggestions(user=Depends(current_user), db: Session = Depends(get_db)):
    from suggestions import suggestions_for
    return suggestions_for(db, user)


@router.get("/digest")
def get_digest(user=Depends(current_user), db: Session = Depends(get_db)):
    from digest import ensure_preference, preference_json
    return preference_json(ensure_preference(db, user.id))


@router.patch("/digest")
def patch_digest(body: DigestChange, user=Depends(current_user), db: Session = Depends(get_db)):
    from digest import ensure_preference, preference_json
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


@router.post("/certificates", status_code=201)
def create_certificate(body: CertificateIssue, user=Depends(current_user), db: Session = Depends(get_db)):
    # TODO: Archive certificates.py post-hackathon; keep only audit record
    from archive.certificates import issue_certificate, certificate_json
    from zoneinfo import ZoneInfo
    from datetime import datetime
    today_year = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).year
    year = today_year if body.year is None else body.year
    try:
        row = issue_certificate(db, user, year)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return certificate_json(row)


@router.get("/certificates/{certificate_id}")
def download_certificate(
    certificate_id: str, format: str = "pdf",
    user=Depends(current_user), db: Session = Depends(get_db)
):
    # TODO: Remove after archiving certificates.py
    from archive.certificates import render_html as certificate_html, render_pdf as certificate_pdf
    row = db.get(AffiliationCertificate, certificate_id)
    if not row or row.account_id != user.id:
        raise HTTPException(404, "Certificate not found.")
    kind = (format or "pdf").strip().lower()
    if kind not in ("pdf", "html"):
        raise HTTPException(422, "Certificate format must be pdf or html.")
    if kind == "html":
        return Response(
            certificate_html(user, row), media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'inline; filename="carecredits-{row.year}-{row.id[:8]}.html"'},
        )
    return Response(
        certificate_pdf(user, row), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="carecredits-{row.year}-{row.id[:8]}.pdf"'},
    )


UNSUBSCRIBE_OK_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>Unsubscribed — CareCredits</title><style>body{font-family:Georgia,serif;color:#10233f;max-width:36rem;margin:3rem auto;padding:0 1.25rem}h1{font-size:1.6rem}p{line-height:1.5;color:#3d536b}</style></head><body><h1>You are unsubscribed</h1><p>CareCredits will not send another biweekly digest unless you opt in again.</p></body></html>"""
UNSUBSCRIBE_INVALID_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>Unsubscribe link invalid — CareCredits</title><style>body{font-family:Georgia,serif;color:#10233f;max-width:36rem;margin:3rem auto;padding:0 1.25rem}h1{font-size:1.6rem}p{line-height:1.5;color:#3d536b}</style></head><body><h1>Unsubscribe link invalid</h1><p>This unsubscribe link is missing, blank, or no longer valid.</p></body></html>"""


def _wants_unsubscribe_json(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "application/json" in accept and "text/html" not in accept


@router.get("/digest/unsubscribe")
def digest_unsubscribe(request: Request, token: str | None = None, db: Session = Depends(get_db)):
    cleaned = (token or "").strip()
    if not cleaned:
        if _wants_unsubscribe_json(request):
            return envelope(404, "Unsubscribe link is invalid or expired.", request)
        return Response(content=UNSUBSCRIBE_INVALID_HTML, media_type="text/html", status_code=404)
    pref = db.query(DigestPreference).filter_by(unsubscribe_token=cleaned).first()
    if not pref:
        if _wants_unsubscribe_json(request):
            return envelope(404, "Unsubscribe link is invalid or expired.", request)
        return Response(content=UNSUBSCRIBE_INVALID_HTML, media_type="text/html", status_code=404)
    pref.opted_in = False
    pref.unsubscribed_at = time.time()
    db.commit()
    payload = {"opted_in": False, "message": "You are unsubscribed from CareCredits digests."}
    if _wants_unsubscribe_json(request):
        return payload
    return Response(content=UNSUBSCRIBE_OK_HTML, media_type="text/html")


@router.get("/export/{kind}")
def export(kind: Literal["csv", "eml"], year: int | None = None, user=Depends(current_user), db: Session = Depends(get_db)):
    # TODO: Move to dedicated export service post-hackathon
    from models import Record, Course
    if year is not None and not 1900 <= year <= 2200:
        raise HTTPException(422, "Invalid year.")
    rows = db.query(Record, Course).join(Course, Record.course_id == Course.id).filter(Record.account_id == user.id).all()
    if year is not None:
        year_key = str(year)
        scoped = []
        for r, c in rows:
            attended = getattr(r, "attendance_status", None) == "attended" or bool(r.attended)
            if attended:
                if r.attended_on and str(r.attended_on).startswith(year_key):
                    scoped.append((r, c))
            elif (c.start_date or "").startswith(year_key):
                scoped.append((r, c))
        rows = scoped

    def cell(value):
        value = str(value or "")
        visible = value.lstrip(" \t\r\n\x0b\x0c\ufeff\u200b\u200c\u200d\u2060\u00a0\u1680\u180e\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u00ad\u034f\u061c")
        starters = ("=", "+", "-", "@", "\uff1d", "\uff0b", "\uff0d", "\uff20", "\u2212", "\ufe63")
        return "'" + value if visible[:1] in starters else value

    suffix = f"-{year}" if year is not None else ""
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
        subject_year = f" ({year})" if year is not None else ""
        message["Subject"] = f"My CPD training record{subject_year}"
        message["X-Unsent"] = "1"
        lines = ["My personal training record (self-reported, not independently verified):", ""]
        if year is not None:
            lines.append(f"Year filter: {year}")
            lines.append("")
        attended_lines = [f"{c.title} | {r.attended_on} | {r.points if r.points is not None else 'Not recorded'} {r.credit_label}" for r, c in rows if getattr(r, "attendance_status", None) == "attended" or r.attended]
        if attended_lines:
            lines.extend(attended_lines)
        else:
            lines.append(f"No attended records for {year}." if year is not None else "No attended records yet.")
        message.set_content("\n".join(lines))
        content, mime = message.as_bytes(), "message/rfc822"
    return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="carecredits-record{suffix}.{kind}"'})


AUDIT_HIDDEN = {"notes", "password", "password_hash", "token", "secret", "api_key"}


def _audit_json(row: Audit) -> dict:
    changed = row.changed if isinstance(row.changed, dict) else {}
    return {
        "id": row.id, "action": row.action, "entity_id": row.entity_id,
        "changed": {key: value for key, value in changed.items() if key not in AUDIT_HIDDEN},
        "at": row.created_at,
    }


@router.get("/audit")
def my_audit(page: int = 1, page_size: int = 20, user=Depends(current_user), db: Session = Depends(get_db)):
    if page < 1 or not 1 <= page_size <= 50:
        raise HTTPException(422, "Invalid pagination.")
    query = db.query(Audit).filter_by(account_id=user.id)
    total = query.count()
    rows = query.order_by(Audit.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_audit_json(row) for row in rows], "total": total, "page": page, "page_size": page_size}