from typing import List, Optional
from pydantic import BaseModel


class PaperGenerate(BaseModel):
    subject_id: int
    marks: int
    difficulty: str


class PaperQuestionOut(BaseModel):
    id: int
    text: str
    mark: int
    display_marks: Optional[str] = None


class PaperOut(BaseModel):
    id: int
    subject_id: int
    title: str
    pattern: str
    max_marks: int
    difficulty: str
    file_path: Optional[str] = None

    class Config:
        from_attributes = True


class PaperHistoryOut(BaseModel):
    id: int
    subject_id: int
    title: str
    pattern: str
    max_marks: int
    difficulty: str

    class Config:
        from_attributes = True
