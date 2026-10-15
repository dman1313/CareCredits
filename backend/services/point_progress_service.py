from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.repository.course_repository import CourseRepository
from backend.repository.record_repository import RecordRepository


class PointProgressService:
    """
    Sole owner of CPD progress calculation logic.
    Replaces legacy digest.progress_snapshot() with clean repository separation.
    Timezone-aware: accepts UTC year or converts from user timezone.
    """

    def __init__(self, db: Session):
        self.db = db
        self.course_repo = CourseRepository(db)
        self.record_repo = RecordRepository(db)

    def calculate_points(self, user_id: str, year: int) -> float:
        """Only attended records with verified courses count toward CPD."""
        records = self.record_repo.get_attended_records(user_id, year)
        total = 0.0
        for record in records:
            course = self.course_repo.get_by_id(record.course_id)
            if course and course.points and course.verification_status == 'source_reviewed':
                total += course.points
        return round(total, 2)

    def get_yearly_snapshot(self, user_id: str, year: int) -> Dict[str, Any]:
        """
        Full progress snapshot replacing legacy progress_snapshot().
        Returns points, attendance counts, signup counts, and exclusion details.
        """
        # Get all records for this user/year
        records = self.record_repo.get_all_records_for_year(user_id, year)
        
        # Separate attended vs signed_up
        attended_records = []
        signed_up_count = 0
        excluded_reasons = []
        
        for record in records:
            is_attended = getattr(record, 'attendance_status', None) == 'attended' or bool(getattr(record, 'attended', False))
            signup_status = getattr(record, 'signup_status', None)
            
            # Count signups (exclude cancelled; honour legacy bool drift)
            if signup_status != 'cancelled':
                is_signed_up = (signup_status == 'signed_up') or bool(getattr(record, 'signed_up', False))
                if is_signed_up and not is_attended:
                    signed_up_count += 1
            
            # Process attended records
            if is_attended:
                attended_records.append(record)
                
                # Determine exclusions
                if record.points is None:
                    excluded_reasons.append({
                        'reason': 'unknown_points',
                        'credit_label': record.credit_label
                    })
                elif not self._counts_toward_cpd(record):
                    excluded_reasons.append({
                        'reason': 'unmapped_credit_label',
                        'credit_label': record.credit_label
                    })
        
        # Calculate countable points
        points = 0.0
        for record in attended_records:
            if self._counts_toward_cpd(record):
                course = self.course_repo.get_by_id(record.course_id)
                if course and course.points:
                    points += course.points
        
        return {
            'year': year,
            'points': round(points, 2),
            'attended': len(attended_records),
            'signed_up': signed_up_count,
            'excluded': len(excluded_reasons),
            'excluded_reasons': excluded_reasons,
        }

    def _counts_toward_cpd(self, record) -> bool:
        """Business rule: determines if a record's credit label counts toward official CPD."""
        # TODO: Extract valid credit labels to config/constants
        VALID_LABELS = {'CPD', 'CME', 'CPE', 'CE'}
        label = (getattr(record, 'credit_label', '') or '').strip().upper()
        return label in VALID_LABELS