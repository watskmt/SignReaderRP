from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Database
    DATABASE_URL: str = "postgresql://signreader:signreader_pass@localhost:5432/signreader_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # API
    API_DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-key-change-in-production"

    # OCR
    USE_GOOGLE_VISION: bool = False
    GOOGLE_VISION_THRESHOLD: float = 0.85
    OCR_MIN_CONFIDENCE: float = 0.80

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Gemini validation
    GEMINI_API_KEY: str = ""
    GEMINI_VALIDATION_ENABLED: bool = False
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_MIN_PROBABILITY: float = 0.5

    # ローカル画像保存
    IMAGE_STORAGE_PATH: str = "/app/images"
    IMAGE_STORAGE_MAX_GB: float = 5.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
