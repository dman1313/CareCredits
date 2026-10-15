from sqlalchemy import Column, Integer
from backend.database.database import Base

class SchemaVersion(Base):
    __tablename__ = 'portal_schema_version'
    version = Column(Integer, primary_key=True)