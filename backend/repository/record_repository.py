from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.record import Record


class RecordRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_account_and_course(self, account_id: str, course_id: str) -> Optional[Record]:
        """Get existing record for optimistic locking / updates."""
        return (
            self.db.query(Record)
            .filter_by(account_id=account_id, course_id=course_id)
            .first()
        )

    def get_attended_records_for_year(self, account_id: str, year: int) -> List[Record]:
        """
        Returns all attended records for a user in a specific year.
        Used by PointProgressService for CPD calculation.
        """
        from datetime import datetime, timezone
        start_ts = datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()
        end_ts = datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp()

        return (
            self.db.query(Record)
            .filter(
                Record.account_id == account_id,
                Record.attended == True,
                Record.attended_on >= start_ts,
                Record.attended_on < end_ts,
            )
            .all()
        )
    
    def get_all_records_for_year(self, account_id: str, year: int) -> List:
        from datetime import datetime, timezone
        start_ts = datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()
        end_ts = datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp()
        
        return (
            self.db.query(Record)
            .filter(
                Record.account_id == account_id,
                (
                    (Record.attended == True) | 
                    (Record.signup_status == 'signed_up') | 
                    (Record.signed_up == True)
                ),
                ((Record.attended_on >= start_ts) & (Record.attended_on < end_ts)) |
                ((Record.attended_on.is_(None)) & (Record.updated_at >= start_ts) & (Record.updated_at < end_ts))
            )
            .all()
    )

    def save(self, record: Record) -> Record:
        """Persist new or updated record."""
        self.db.add(record)
        self.db.flush()
        return record

    def update_version(self, record_id: str, expected_version: int, **kwargs) -> bool:
        """Optimistic lock update. Returns True if successful."""
        result = (
            self.db.query(Record)
            .filter(Record.id == record_id, Record.version == expected_version)
            .update(kwargs)
        )
        self.db.flush()
        return result.rowcount == 1