import time
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from models.course import Course

class CourseRepository:
    def __init__(self, db: Session):
        self.db = db

    def _build_course(self, data: Dict[str, Any], demo: Optional[bool] = None) -> Course:
        """
        Centralized course construction logic.
        Handles type coercion, sanitization, and defaults for ALL course creation paths.
        """
        start_date = data.get("start_date")
        if hasattr(start_date, "isoformat"):
            start_date = start_date.isoformat()

        return Course(
            source_key=data.get("source_key"),
            title=(data.get("title") or "")[:200],
            provider=(data.get("provider") or "")[:200],
            description=(data.get("description") or "")[:3000],
            start_date=start_date,
            city=data.get("city"),
            state=data.get("state"),
            country=data.get("country", "MY"),
            mode=data.get("mode", "online"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            fee=data.get("fee"),
            currency=data.get("currency"),
            points=data.get("points"),
            credit_label=data.get("credit_label"),
            difficulty=data.get("difficulty"),
            raw_source_data=data,
            updated_at=time.time(),
            demo=demo if demo is not None else False,
        )

    def create_from_raw_data(self, source_key: str, raw_data: dict) -> Course:
        """Create and persist a Course directly from unvalidated scraper/candidate data."""
        data = {**raw_data, "source_key": source_key}
        course = self._build_course(data)
        self.db.add(course)
        self.db.flush()
        return course

    def save(self, course: Course) -> Course:
        """Persist an existing Course instance."""
        self.db.add(course)
        self.db.flush()
        return course

    def get_by_id(self, course_id: str) -> Optional[Course]:
        return self.db.query(Course).filter(Course.id == course_id).first()

    def get_by_source_key(self, source_key: str) -> Optional[Course]:
        return self.db.query(Course).filter(Course.source_key == source_key).first()

    def get_events_from_date(
        self, from_date: str, source_keys: Optional[List[str]] = None
    ) -> List[Course]:
        query = self.db.query(Course).filter(Course.start_date >= from_date)
        if source_keys:
            query = query.filter(Course.source_key.in_(source_keys))
        return query.order_by(Course.start_date).limit(5000).all()