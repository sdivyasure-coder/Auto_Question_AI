from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey, Text

from app.database.base import Base


class UploadAsset(Base):
    __tablename__ = "upload_assets"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    file_type = Column(String(30), nullable=False)
    file_path = Column(String(500), nullable=False)
    parse_status = Column(String(20), nullable=False, default="pending")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
