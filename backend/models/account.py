import uuid
from sqlalchemy import Column, Float, String, Boolean
from database import Base
from sqlalchemy.orm import relationship

def uid():
    return uuid.uuid4().hex

class Account(Base):
    __tablename__ = 'accounts'
    
    id = Column(String, primary_key=True, default=uid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    deleted_at = Column(Float, nullable=True, index=True)
    
    audit_logs = relationship("AuditLog", back_populates="account")