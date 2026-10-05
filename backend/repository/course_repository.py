import time
from typing import List, Optional
from sqlalchemy.orm import Session

from models.course import Course
from shared.contracts import Training

FILTER_FIELDS = (
    'title', 'provider', 'description', 'start_date', 'city', 'state',
    'country', 'mode', 'latitude', 'longitude', 'fee', 'currency',
    'points', 'credit_label', 'difficulty',
)


class CourseRepository:
    def __init__(self, db: Session):
        self.db = db

    def hydrate(self, training: Training, demo: Optional[bool] = None) -> Course:
        payload = training.model_dump(mode='json')

        start = payload.get('start_date')
        if hasattr(start, 'isoformat'):
            payload['start_date'] = start.isoformat()

        course = Course(
            source_key=payload.get('source_key'),
            title=(payload.get('title') or '')[:200],
            provider=(payload.get('provider') or '')[:200],
            description=(payload.get('description') or '')[:3000],
            start_date=payload.get('start_date'),
            city=payload.get('city'),
            state=payload.get('state'),
            country=payload.get('country') or 'MY',
            mode=payload.get('mode') or 'online',
            latitude=payload.get('latitude'),
            longitude=payload.get('longitude'),
            fee=payload.get('fee'),
            currency=payload.get('currency'),
            points=payload.get('points'),
            credit_label=payload.get('credit_label'),
            difficulty=payload.get('difficulty'),
            raw_source_data=payload,
            updated_at=time.time(),
        )

        if demo is not None:
            course.demo = demo

        return course

    def create_from_raw_data(self, source_key: str, raw_data: dict) -> Course:
        course = Course(
            source_key=source_key,
            title=(raw_data.get("title") or "")[:200],
            provider=(raw_data.get("provider") or "")[:200],
            description=(raw_data.get("description") or "")[:3000],
            start_date=raw_data.get("start_date"),
            city=raw_data.get("city"),
            state=raw_data.get("state"),
            country=raw_data.get("country", "MY"),
            mode=raw_data.get("mode", "online"),
            fee=raw_data.get("fee"),
            points=raw_data.get("points"),
            credit_label=raw_data.get("credit_label"),
            difficulty=raw_data.get("difficulty"),
            raw_source_data=raw_data,
            updated_at=time.time(),
        )
        self.db.add(course)
        self.db.flush()
        return course

    def save(self, course: Course) -> Course:
        self.db.add(course)
        self.db.flush()
        return course

    def get_by_id(self, course_id: str) -> Optional[Course]:
        return self.db.query(Course).filter(Course.id == course_id).first()

    def get_by_source_key(self, source_key: str) -> Optional[Course]:
        return self.db.query(Course).filter(Course.source_key == source_key).first()

    def get_upcoming_events(self, from_date: str, source_keys: Optional[List[str]] = None):
        query = self.db.query(Course).filter(Course.start_date >= from_date)
    
        if source_keys:
            query = query.filter(Course.source_key.in_(source_keys))
        
        return query.order_by(Course.start_date).limit(5000).all()