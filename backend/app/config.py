"""App settings from environment variables (API.md 10.1, ARCHITECTURE 12).

Read once with `get_settings()`. In `prod` the app refuses to start with missing, short,
reused or DEV keys, or a non-HTTPS public origin (ADR-0020, ADR-0022 D15). Error messages
name the problem, never a key value.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.crypto.keys import ENV_NAMES, KeyConfigError, KeyRing, Purpose

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), extra="ignore", frozen=True
    )

    app_name: str = "Privacy Guardian"
    env: Literal["dev", "prod"] = "dev"
    public_origin: str = "http://localhost:8000"
    data_dir: Path = Path("/data")
    static_dir: Path = REPO_ROOT / "frontend" / "dist"

    ner_model_path: str = "/app/model"
    ner_threshold: float = Field(0.5, ge=0.0, le=1.0)

    max_upload_mb: int = Field(10, ge=1, le=100)
    retention_days: int = Field(7, ge=1, le=365)
    session_idle_hours: int = Field(8, ge=1, le=72)
    session_max_days: int = Field(7, ge=1, le=90)
    trusted_proxy_count: int = Field(0, ge=0, le=5)

    admin_email: str | None = None
    admin_password: SecretStr | None = None

    pg_token_key: SecretStr | None = None
    pg_audit_key: SecretStr | None = None
    pg_vault_key: SecretStr | None = None
    pg_storage_key: SecretStr | None = None

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    def key_env(self) -> dict[str, str]:
        """The key variables that are set, by their env names (values stay secret)."""
        values = {
            Purpose.TOKEN: self.pg_token_key,
            Purpose.AUDIT: self.pg_audit_key,
            Purpose.VAULT: self.pg_vault_key,
            Purpose.STORAGE: self.pg_storage_key,
        }
        out = {ENV_NAMES[p]: v.get_secret_value().strip() for p, v in values.items() if v}
        return {k: v for k, v in out.items() if v}  # empty "PG_X_KEY=" lines count as unset

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def load_keyring(settings: Settings) -> tuple[KeyRing, bool]:
    """(key ring, using_dev_keys). DEV keys only when no key is set and env is dev."""
    env = settings.key_env()
    if env or settings.env == "prod":
        return KeyRing.from_env(env), False
    return KeyRing.dev(), True


def check_prod(settings: Settings) -> None:
    """Refuse unsafe production config. Kept outside pydantic on purpose: pydantic's model
    errors print the whole input, which would put key values into logs."""
    if settings.env != "prod":
        return
    ring = KeyRing.from_env(settings.key_env())  # missing, short or reused keys
    dev = KeyRing.dev()
    if any(ring[p].current[1] == dev[p].current[1] for p in Purpose):
        raise KeyConfigError("DEV keys are not allowed in prod")
    if not settings.public_origin.startswith("https://"):
        raise KeyConfigError("PUBLIC_ORIGIN must be https:// in prod")
    if settings.admin_password and len(settings.admin_password.get_secret_value()) < 12:
        raise KeyConfigError("ADMIN_PASSWORD must be at least 12 characters")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    check_prod(settings)
    return settings
