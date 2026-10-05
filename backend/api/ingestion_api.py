from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
from repository.course_repository import CourseRepository
from models.ingestion import IngestionBatch, Candidate
import time

router = APIRouter(prefix="/internal/v1/batches", tags=["internal"])

@router.post("/push")
def push_scraper_results(
    batch_payload: dict,  
    db: Session = Depends(get_db)
):
    course_repo = CourseRepository(db)
    accepted = []
    rejected = []

    batch = IngestionBatch(
        operator_id=batch_payload.get("operator_id"), 
        source_system="scraper-v1",
        event_count=len(batch_payload.get("events", [])),
        created_at=time.time()
    )
    db.add(batch)
    db.flush()

    for event in batch_payload.get("events", []):
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