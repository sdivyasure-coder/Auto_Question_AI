from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class UnitIn(BaseModel):
    subject_id: int
    unit_no: int
    title: str
    weightage_percent: float = 0.0


class UnitOut(BaseModel):
    id: int
    subject_id: int
    unit_no: int
    title: str
    weightage_percent: float

    class Config:
        from_attributes = True


class TemplateSeedIn(BaseModel):
    name: str
    template_type: str
    total_marks: int
    structure: Dict[str, Any]


class PaperGenerateV2In(BaseModel):
    subject_id: int
    unit_ids: List[int] = Field(default_factory=list)
    total_marks: int = 100
    difficulty: str = "medium"
    question_count: int = 18
    template_name: str = "semester"
    exam_date: Optional[str] = None
    regenerate_from_paper_id: Optional[int] = None


class SectionEditIn(BaseModel):
    section: str
    action: str = "regenerate"


class PaperQuestionV2Out(BaseModel):
    id: int
    section: str
    question_no: int
    marks: int
    text: str
    difficulty: str
    blooms_level: str
    co_code: Optional[str] = None
    po_code: Optional[str] = None
    answer_key: Optional[str] = None

    class Config:
        from_attributes = True


class PaperV2Out(BaseModel):
    id: int
    subject_id: int
    title: str
    total_marks: int
    requested_difficulty: str
    num_questions: int
    status: str
    exam_date: Optional[str] = None
    estimated_minutes: int
    quality_report: Dict[str, Any]
    answer_keys: Dict[str, Any]
    preview_html: str
    pdf_url: Optional[str] = None
    docx_url: Optional[str] = None
    questions: List[PaperQuestionV2Out]


class HistoryQueryOut(BaseModel):
    id: int
    title: str
    subject_id: int
    total_marks: int
    requested_difficulty: str
    status: str
    created_at: str


class ImproveQuestionIn(BaseModel):
    question_text: str


class ImproveQuestionOut(BaseModel):
    improved_text: str


class ThemeSettingIn(BaseModel):
    theme: str = "dark"


class CollegeBrandingIn(BaseModel):
    college_name: str
    subject_code_prefix: Optional[str] = ""
    exam_date_format: Optional[str] = "DD-MM-YYYY"
    logo_path: Optional[str] = None


class UploadExtractOut(BaseModel):
    upload_id: int
    inserted_count: int
    parse_status: str


class AnalyticsOut(BaseModel):
    most_used_units: List[Dict[str, Any]]
    generation_frequency: List[Dict[str, Any]]
    difficulty_distribution: List[Dict[str, Any]]


class WeightageOut(BaseModel):
    paper_id: int
    unit_marks: List[Dict[str, Any]]
    total_marks: int
