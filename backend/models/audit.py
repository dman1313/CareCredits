import time
import uuid
from sqlalchemy import Column, String, Float, JSON, ForeignKey
from sqlalchemy.orm import relationship
from backend.database.database import Base


def uid() -> str:
    return uuid.uuid4().hex


class AuditLog(Base):
    __tablename__ = 'portal_audit'

    id = Column(String, primary_key=True, default=uid)
    
    account_id = Column(
        String, 
        ForeignKey('accounts.id', ondelete='RESTRICT'), 
        nullable=False, 
        index=True
    )
    
    action = Column(String(50), nullable=False)
    entity_id = Column(String, nullable=False)
    changed = Column(JSON, nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)
    
    account = relationship("Account", back_populates="audit_logs")