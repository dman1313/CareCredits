from pydantic import BaseModel
from typing import Optional
from datetime import date

class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: str
    
    class Config:
        from_attributes = True

class CourseBase(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    fee: Optional[float] = None
    difficulty: Optional[str] = None
    cpd_points: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class CourseCreate(CourseBase):
    pass

class CourseResponse(CourseBase):
    id: int
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True

class RegistrationBase(BaseModel):
    user_id: int
    course_id: int
    status: Optional[str] = "registered"

class RegistrationCreate(RegistrationBase):
    pass

class RegistrationResponse(RegistrationBase):
    id: int
    registered_at: str
    
    class Config:
        from_attributes = True
