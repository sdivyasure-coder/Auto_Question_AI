from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey, Float
from sqlalchemy.orm import relationship

from app.database.base import Base


class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    unit_no = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    weightage_percent = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, server_default=func.now())

    subject = relationship("Subject", back_populates="units")
