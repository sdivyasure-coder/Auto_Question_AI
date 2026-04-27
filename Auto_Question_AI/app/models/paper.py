from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship

from app.database.base import Base


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(255), nullable=False)
    pattern = Column(String(50), nullable=False)
    max_marks = Column(Integer, nullable=False)
    difficulty = Column(String(20), nullable=False)
    file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    subject = relationship("Subject", back_populates="papers")
    user = relationship("User", back_populates="papers")
    questions = relationship("PaperQuestion", back_populates="paper", cascade="all, delete-orphan")
