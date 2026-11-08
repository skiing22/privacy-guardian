"""App settings, read from environment variables or .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Privacy Guardian Agent"
    env: str = "dev"
    database_url: str = "postgresql+psycopg://pg:pg@localhost:5432/privacy_guardian"
    ner_model_path: str = "../ml/models/ner-distilbert-v1"
    ner_threshold: float = 0.5


settings = Settings()
