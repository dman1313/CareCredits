import time
import uuid
from sqlalchemy import Column, String, Float, Boolean, JSON, Index
from database import Base


def uid() -> str:
    return uuid.uuid4().hex


class Course(Base):
    __tablename__ = 'courses'

    id = Column(String, primary_key=True, default=uid)
    source_key = Column(String, unique=True, nullable=False, index=True)

    title = Column(String(200), nullable=False, index=True)
    provider = Column(String(200), nullable=False, index=True)
    description = Column(String(3000), nullable=True)
    start_date = Column(String, nullable=True, index=True)
    city = Column(String, nullable=True, index=True)
    state = Column(String, nullable=True)
    country = Column(String(2), default='MY', nullable=False)
    mode = Column(String(20), default='online', nullable=False, index=True)
    fee = Column(Float, nullable=True)
    points = Column(Float, nullable=True)
    credit_label = Column(String(30), nullable=True)
    difficulty = Column(String(50), nullable=True, index=True)

    # Metadata
    demo = Column(Boolean, default=False, nullable=False)
    updated_at = Column(Float, default=time.time, nullable=False)

    # Raw data for audit/debugging
    raw_source_data = Column(JSON, nullable=True)