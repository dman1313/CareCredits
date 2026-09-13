from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from typing import List
import os
from contextlib import asynccontextmanager

# Import models and schemas
from .database import Base, engine
from .models import User, Course, Registration
from .schemas import UserCreate, UserLogin, CourseCreate, RegistrationCreate
from .auth import get_password_hash, verify_password, create_access_token, get_current_user

# Create database tables
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

# Initialize FastAPI app
app = FastAPI(
    title="CareCredit API",
    description="API for the CareCredit CPD portal",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database dependency
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Root endpoint
@app.get("/")
def read_root():
    return {"message": "Welcome to CareCredit API"}

# User endpoints
@app.post("/users/", response_model=dict)
def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = User(email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return {"message": "User created successfully", "user_id": db_user.id}

@app.post("/users/login", response_model=dict)
def login(user: UserLogin, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create access token
    access_token = create_access_token(data={"sub": db_user.email})
    
    return {"access_token": access_token, "token_type": "bearer"}

# Course endpoints
@app.post("/courses/", response_model=dict)
def create_course(course: CourseCreate, db: AsyncSession = Depends(get_db)):
    db_course = Course(**course.dict())
    db.add(db_course)
    db.commit()
    db.refresh(db_course)
    
    return {"message": "Course created successfully", "course_id": db_course.id}

@app.get("/courses/", response_model=List[CourseCreate])
def get_courses(db: AsyncSession = Depends(get_db)):
    courses = db.query(Course).all()
    return courses

@app.get("/courses/{course_id}", response_model=CourseCreate)
def get_course(course_id: int, db: AsyncSession = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course

# Registration endpoints
@app.post("/registrations/", response_model=dict)
def create_registration(registration: RegistrationCreate, db: AsyncSession = Depends(get_db)):
    # Check if course exists
    course = db.query(Course).filter(Course.id == registration.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check if user exists
    user = db.query(User).filter(User.id == registration.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create registration
    db_registration = Registration(**registration.dict())
    db.add(db_registration)
    db.commit()
    db.refresh(db_registration)
    
    return {"message": "Registration created successfully", "registration_id": db_registration.id}

@app.get("/registrations/{user_id}", response_model=List[RegistrationCreate])
def get_user_registrations(user_id: int, db: AsyncSession = Depends(get_db)):
    registrations = db.query(Registration).filter(Registration.user_id == user_id).all()
    return registrations

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "CareCredit API is running"}
