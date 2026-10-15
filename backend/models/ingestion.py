import time
import uuid
from sqlalchemy import Column, String, Float, JSON, ForeignKey, UniqueConstraint
from backend.database.database import Base


def uid() -> str:
    return uuid.uuid4().hex

class Candidate(Base):
    __tablename__ = 'course_candidates'
    __table_args__ = (UniqueConstraint('batch_id', 'source_key'),)

    id = Column(String, primary_key=True, default=uid)
    batch_id = Column(String, ForeignKey('ingestion_batches.id'), nullable=False, index=True)
    source_key = Column(String(200), nullable=False, index=True)
    
    raw_data = Column(JSON, nullable=False) 
    
    status = Column(String(20), default='pending_review', nullable=False, index=True)
    created_at = Column(Float, default=time.time, nullable=False)