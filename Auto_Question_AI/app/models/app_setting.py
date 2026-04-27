from sqlalchemy import Column, Integer, String, DateTime, func, Text

from app.database.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
