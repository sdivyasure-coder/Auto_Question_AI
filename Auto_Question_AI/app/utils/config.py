from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    # Support .env files saved with UTF-8 BOM by common Windows editors.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig")

    APP_NAME: str = "AI Question Paper Generator API"
    ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./questionpaper.db"
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"
    CORS_ORIGINS: str = "*"

    def cors_list(self) -> List[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]


settings = Settings()
