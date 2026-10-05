from sqlalchemy.orm import Session
from repository.candidate_repository import CandidateRepository
from repository.course_repository import CourseRepository
from models.course import Course

class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.candidate_repo = CandidateRepository(db)
        self.course_repo = CourseRepository(db)

    def approve_candidate(self, candidate_id: str) -> Course:
        candidate = self.candidate_repo.update_status(candidate_id, "approved")
        
        course = self.course_repo.create_from_raw_data(
            source_key=candidate.source_key,
            raw_data=candidate.raw_data
        )
        
        return course

    def auto_approve(self) -> int:
        """Automatic mode"""
        pending = self.candidate_repo.get_pending(limit=5000)
        approved_count = 0
        for candidate in pending:
            try:
                self.approve_candidate(candidate.id)
                approved_count += 1
            except Exception as e:
                print(f"[AUTO-APPROVE] Failed {candidate.source_key}: {e}")
                continue
        self.db.commit()
        return approved_count

    def manual_approve(self, candidate_ids: list[str]) -> dict:
        """Manual mode: for debugging"""
        results = {"approved": [], "failed": []}
        for cid in candidate_ids:
            try:
                course = self.approve_candidate(cid)
                results["approved"].append({"id": cid, "course_id": course.id})
            except Exception as e:
                results["failed"].append({"id": cid, "error": str(e)})
        self.db.commit()
        return results