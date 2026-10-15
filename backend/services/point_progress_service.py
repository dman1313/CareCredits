from backend.repository.course_repository import CourseRepository
from sqlalchemy.orm import Session

from backend.repository.record_repository import RecordRepository


class PointProgressService:
    def __init__(self, db: Session):
        self.course_repo = CourseRepository(db)
        self.record_repo = RecordRepository(db)

    def calculate_points(self, user_id: str, year: int) -> float:
        """Core business rule: only attended records with verified courses count."""
        records = self.record_repo.get_attended_records(user_id, year)
        total = 0.0
        for record in records:
            course = self.course_repo.get_by_id(record.course_id)
            if course and course.points and course.verification_status == 'source_reviewed':
                total += course.points
        return total

    def get_yearly_snapshot(self, user_id: str, year: int) -> dict:
        """Extended logic: points + exclusions + regulator limits."""
        points = self.calculate_points(user_id, year)
        excluded = self._get_excluded_records(user_id, year)
        return {
            'points': points,
            'excluded_count': len(excluded),
            'year': year,
        }