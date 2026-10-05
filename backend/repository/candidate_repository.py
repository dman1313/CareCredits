from sqlalchemy.orm import Session
from models.ingestion import Candidate


class CandidateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_pending(self, limit: int = 100):
        return (
            self.db.query(Candidate)
            .filter(Candidate.status == "pending_review")
            .order_by(Candidate.created_at)
            .limit(limit)
            .all()
        )

    def update_status(self, candidate_id: str, status: str):
        candidate = self.db.query(Candidate).get(candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")
        candidate.status = status
        self.db.flush()
        return candidate