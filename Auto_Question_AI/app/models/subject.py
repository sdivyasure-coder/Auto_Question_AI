from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship

from app.database.base import Base


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    questions = relationship("Question", back_populates="subject", cascade="all, delete-orphan")
    papers = relationship("Paper", back_populates="subject", cascade="all, delete-orphan")
    units = relationship("Unit", back_populates="subject", cascade="all, delete-orphan")
