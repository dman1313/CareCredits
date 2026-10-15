from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.repository.audit_repository import AuditRepository
from security import operator, throttle
from shared.model_defaults import env_or_provisional, using_provisional
from shared.contracts import public_web_url
from services.ingestion_service import IngestionService


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# === Legacy Training Endpoint (Disabled) ===
# @router.post("/trainings/{course_id}/cancel")
# def cancel_training(course_id: str, user=Depends(operator), db: Session = Depends(get_db)):
#     # TODO: Re-enable when scraper-service implements its own cancellation endpoint
#     pass


# === Ingestion Control Endpoints ===
@router.post("/ingestion/auto-approve")
def auto_approve_candidates(user=Depends(operator), db: Session = Depends(get_db)):
    service = IngestionService(db)
    count = service.auto_approve()
    return {"approved_count": count}


@router.post("/ingestion/manual-approve")
def manual_approve_candidates(
    candidate_ids: List[str],
    _operator=Depends(operator),
    db: Session = Depends(get_db),
):
    service = IngestionService(db)
    return service.manual_approve(candidate_ids)


# === Audit Endpoints ===
@router.get("/audit")
def admin_audit(
    page: int = 1, page_size: int = 20,
    user=Depends(operator), db: Session = Depends(get_db),
):
    repo = AuditRepository(db)
    try:
        # Admin sees ALL audits; no account_id filter
        return repo.get_paginated(page, page_size, account_id=None)
    except ValueError as e:
        raise HTTPException(422, str(e))


# === Infrastructure Endpoints ===
@router.get("/services")
def services(user=Depends(operator), db: Session = Depends(get_db)):
    database = "ready"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"
    return {
        "backend": "ready" if database == "ready" else "degraded",
        "database": database,
        "frontend": "this portal",
    }


@router.get("/integrations")
def integrations(user=Depends(operator)):
    weights = env_or_provisional("MODEL_WEIGHTS_URL") or None
    license_url = env_or_provisional("MODEL_LICENSE_URL") or None
    input_chars = int((env_or_provisional("MODEL_MAX_INPUT_CHARS") or "0").strip()) or None
    output_tokens = int((env_or_provisional("MODEL_MAX_OUTPUT_TOKENS") or "0").strip()) or None
    return {
        "model_id": env_or_provisional("MODEL_ID") or None,
        "model_publisher": env_or_provisional("MODEL_PUBLISHER") or None,
        "model_host": env_or_provisional("MODEL_HOST") or None,
        "model_weights_url": public_web_url(weights),
        "model_license_url": public_web_url(license_url),
        "model_identity_provisional": using_provisional("MODEL_ID"),
        "model_caps_configured": bool(input_chars and output_tokens),
        "model_max_input_chars": input_chars,
        "model_max_output_tokens": output_tokens,
        "google_oauth": False,
    }