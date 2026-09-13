from pydantic import BaseModel


class UserCreate(BaseModel):
    email: str
    name: str | None = None


class UserResponse(BaseModel):
    id: int
    email: str
    name: str | None = None

    class Config:
        from_attributes = True
