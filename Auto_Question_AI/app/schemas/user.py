from typing import Optional
from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    role: Optional[str] = "student"


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str

    class Config:
        from_attributes = True
