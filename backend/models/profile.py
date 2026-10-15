from sqlalchemy import Column, String, Boolean, ForeignKey
from backend.database.database import Base

class AccountProfile(Base):
    __tablename__ = 'account_profiles'
    
    account_id = Column(String, ForeignKey('accounts.id'), primary_key=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=True)
    city = Column(String, default='Kuala Lumpur', nullable=False)
    bio = Column(String, default='', nullable=False)
    public_enabled = Column(Boolean, default=False, nullable=False)
    public_slug = Column(String, unique=True, nullable=True) 