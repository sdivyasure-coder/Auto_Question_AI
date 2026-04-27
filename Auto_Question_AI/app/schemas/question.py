from typing import Optional, List
from pydantic import BaseModel


class QuestionCreate(BaseModel):
    subject_id: int
    chapter: int
    text: str
    mark: int
    difficulty: str
    source: Optional[str] = "bank"


class QuestionUpdate(BaseModel):
    chapter: Optional[int] = None
    text: Optional[str] = None
    mark: Optional[int] = None
    difficulty: Optional[str] = None
    source: Optional[str] = None
    active: Optional[bool] = None


class QuestionOut(BaseModel):
    id: int
    subject_id: int
    chapter: int
    text: str
    mark: int
    difficulty: str
    source: str
    active: bool

    class Config:
        from_attributes = True


class QuestionBulkUpload(BaseModel):
    subject_id: int
    rows: List[QuestionCreate]
