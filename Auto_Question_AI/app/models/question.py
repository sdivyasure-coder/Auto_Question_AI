from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.database.base import Base


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    chapter = Column(Integer, nullable=False)
    text = Column(String(2000), nullable=False)
    mark = Column(Integer, nullable=False)
    difficulty = Column(String(20), nullable=False, default="medium")
    source = Column(String(50), nullable=False, default="bank")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    subject = relationship("Subject", back_populates="questions")
    paper_links = relationship("PaperQuestion", back_populates="question", cascade="all, delete-orphan")
