from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, Text

from app.database.base import Base


class PaperTemplate(Base):
    __tablename__ = "paper_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    template_type = Column(String(30), nullable=False, default="internal")
    total_marks = Column(Integer, nullable=False)
    structure_json = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())
