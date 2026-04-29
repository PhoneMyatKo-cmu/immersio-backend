from pydantic import BaseModel, EmailStr
from models.user import EstimatedLevel
from datetime import datetime

class UserBase(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr

class UserCreate(BaseModel):
    password_hash: str
    estimated_level: EstimatedLevel
    created_at: datetime

class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    password_hash: str | None = None
    estimated_level: EstimatedLevel | None = None

class User(BaseModel):
    pass