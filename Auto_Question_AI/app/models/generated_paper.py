from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database.base import Base


class GeneratedPaper(Base):
    __tablename__ = "generated_papers"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    template_id = Column(Integer, ForeignKey("paper_templates.id"), nullable=True)
    title = Column(String(255), nullable=False)
    total_marks = Column(Integer, nullable=False)
    requested_difficulty = Column(String(20), nullable=False, default="medium")
    num_questions = Column(Integer, nullable=False, default=0)
    selected_units_json = Column(Text, nullable=False, default="[]")
    status = Column(String(20), nullable=False, default="draft")
    quality_report_json = Column(Text, nullable=False, default="{}")
    answer_key_json = Column(Text, nullable=False, default="{}")
    preview_html = Column(Text, nullable=False, default="")
    file_pdf = Column(String(500), nullable=True)
    file_docx = Column(String(500), nullable=True)
    exam_date = Column(String(30), nullable=True)
    estimated_minutes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    subject = relationship("Subject")
    user = relationship("User")
    template = relationship("PaperTemplate")
    questions = relationship("GeneratedPaperQuestion", back_populates="paper", cascade="all, delete-orphan")


class GeneratedPaperQuestion(Base):
    __tablename__ = "generated_paper_questions"

    id = Column(Integer, primary_key=True, index=True)
    generated_paper_id = Column(Integer, ForeignKey("generated_papers.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True, index=True)
    section = Column(String(10), nullable=False)
    question_no = Column(Integer, nullable=False)
    marks = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    difficulty = Column(String(20), nullable=False, default="medium")
    blooms_level = Column(String(20), nullable=False, default="understand")
    co_code = Column(String(30), nullable=True)
    po_code = Column(String(30), nullable=True)
    is_ai_generated = Column(Integer, nullable=False, default=0)
    answer_key = Column(Text, nullable=True)

    paper = relationship("GeneratedPaper", back_populates="questions")
    question = relationship("Question")
