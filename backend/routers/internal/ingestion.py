from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database.database import get_db
from repository.course_repository import CourseRepository
from models.ingestion import IngestionBatch, Candidate
import time
from typing import List, Optional

# This Api class should strictly be used by our scraper microservice, all it does is supply API endpoints for
# pushing courses the scraper has found and for the scraper to find out whats already in the DB

router = APIRouter(prefix="/internal/v1/ingestion", tags=["internal-ingestion"])

class ScraperBatchPayload(BaseModel):
    operator_id: str
    events: List[dict]


@router.post("/batches/push")
def push_scraper_results(
    batch_payload: ScraperBatchPayload,
    db: Session = Depends(get_db)
):
    """
    API point for pushing course batches, will return which events have been accepted and rejected
    by the db for further agentic learning.
    """
    course_repo = CourseRepository(db)
    accepted = []
    rejected = []

    batch = IngestionBatch(
        operator_id=batch_payload.operator_id,
        source_system="scraper-v1",
        event_count=len(batch_payload.events),
        created_at=time.time()
    )
    db.add(batch)
    db.flush()

    for event in batch_payload.events:
        source_key = event.get("source_key")

        existing = course_repo.get_by_source_key(source_key)

        if existing:
            rejected.append({
                "source_key": source_key,
                "reason": "Event already exists in catalogue"
            })
        else:
            candidate = Candidate(
                batch_id=batch.id,
                source_key=source_key,
                raw_data=event,
                status="pending_review"
            )
            db.add(candidate)
            accepted.append(source_key)

    db.commit()

    return {
        "batch_id": batch.id,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "details": {"rejected": rejected}
    }


@router.get("/catalogue/existing-events")
def get_existing_events(
    from_date: str = Query(..., description="YYYY-MM-DD format"),
    source_keys: Optional[List[str]] = Query(None, description="Optional filter by specific source keys"),
    db: Session = Depends(get_db)
):
    """
    Returns upcoming events that the scraper should treat as 'already known'.
    Optimized payload for agent-based deduplication (fingerprint fields only).
    """
    repo = CourseRepository(db)
    events = repo.get_upcoming_events(from_date=from_date, source_keys=source_keys)

    return [
        {
            "source_key": e.source_key,
            "title": e.title,
            "provider": e.provider,
            "start_date": e.start_date,
            "city": e.city,
            "mode": e.mode,
            "updated_at": e.updated_at,
        }
        for e in events
    ]