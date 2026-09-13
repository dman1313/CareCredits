from sqlalchemy import Column, Integer, String, Boolean, DateTime, DECIMAL, ForeignKey, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with registrations
    registrations = relationship("Registration", back_populates="user")

class Course(Base):
    __tablename__ = "courses"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    location = Column(String(255), nullable=True)
    fee = Column(DECIMAL(10, 2), nullable=True)
    difficulty = Column(String(50), nullable=True)
    cpd_points = Column(DECIMAL(5, 2), nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

class Registration(Base):
    __tablename__ = "registrations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    registered_at = Column(TIMESTAMP, default=datetime.utcnow)
    status = Column(String(50), default="registered")
    
    # Relationships
    user = relationship("User", back_populates="registrations")
    course = relationship("Course")
