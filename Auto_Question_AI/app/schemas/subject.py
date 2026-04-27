from typing import Optional
from pydantic import BaseModel


class SubjectCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None


class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SubjectOut(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True
