from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.database.base import Base


class QuestionProfile(Base):
    __tablename__ = "question_profiles"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, unique=True, index=True)
    blooms_level = Column(String(20), nullable=False, default="understand")
    co_code = Column(String(30), nullable=True)
    po_code = Column(String(30), nullable=True)

    question = relationship("Question")
