import time
import uuid
from sqlalchemy import Column, String, Boolean, Float, JSON, ForeignKey, UniqueConstraint, Integer
from database import Base


def uid() -> str:
    return uuid.uuid4().hex


class Record(Base):
    __tablename__ = 'doctor_records'
    __table_args__ = (UniqueConstraint('account_id', 'course_id'),)

    id = Column(String, primary_key=True, default=uid)
    
    account_id = Column(String, ForeignKey('accounts.id'), nullable=False, index=True)
    course_id = Column(String, ForeignKey('courses.id'), nullable=False, index=True)
    
    signed_up = Column(Boolean, default=False, nullable=False)
    attended = Column(Boolean, default=False, nullable=False)
    attended_on = Column(Float, nullable=True)  
    points = Column(Float, nullable=True)
    credit_label = Column(String(30), default='CPD', nullable=False)
    public = Column(Boolean, default=False, nullable=False)
    
    version = Column(Integer, default=1, nullable=False) 
    
    updated_at = Column(Float, default=time.time, onupdate=time.time, nullable=False)


class RecordHistory(Base):
    __tablename__ = 'record_history'
    id = Column(String, primary_key=True, default=uid) 
    record_id = Column(String, ForeignKey('doctor_records.id'), nullable=False, index=True)   
    changed = Column(JSON, nullable=False) 
    created_at = Column(Float, default=time.time, nullable=False)

# Later expansion
# class AffiliationCertificate(Base):
#     __tablename__ = 'affiliation_certificates'
    
#     id = Column(String, primary_key=True, default=uid)
#     account_id = Column(String, ForeignKey('accounts.id'), nullable=False, index=True)
#     year = Column(Integer, nullable=False)
#     recorded_points_snapshot = Column(Float, nullable=False)
#     issued_at = Column(Float, default=time.time, nullable=False)
#     document_hash = Column(String, nullable=False)
#     disclaimer_version = Column(String, default='CERT-01-v1', nullable=False)