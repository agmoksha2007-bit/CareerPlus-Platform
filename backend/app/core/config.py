"""
PURPOSE
-------
Centralized application configuration, loaded once from environment
variables / the .env file. This is the single source of truth for every
environment-dependent value in the backend — no other module should read
os.environ directly.

Using pydantic-settings (Pydantic v2) means a missing required variable
(MONGODB_URI, JWT_SECRET_KEY) causes the app to fail immediately on
startup with a clear validation error, instead of failing confusingly on
the first request that needs it.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # model_config tells pydantic-settings WHERE to load values from:
    # the `.env` file in backend/, UTF-8 encoded. `extra="ignore"` means
    # an unrelated env var sitting in the same .env file won't crash
    # startup — it's just ignored rather than treated as an error.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application metadata — used in main.py (FastAPI title) and in any
    # future logging/error-reporting setup that wants to identify itself.
    # ------------------------------------------------------------------
    APP_NAME: str = "CareerPulse API"

    # All routers are mounted under this prefix (see architecture doc
    # Section 8 — every endpoint lives under /api/v1). Defining it here,
    # rather than hardcoding "/api/v1" in every router file, means a
    # future version bump (/api/v2) is a one-line change.
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------------
    # MongoDB — no default for the URI itself. A missing MONGODB_URI
    # should stop the app from starting, not silently fall back to
    # some guessed local default that might not exist.
    # ------------------------------------------------------------------
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "careerpulse"

    # ------------------------------------------------------------------
    # JWT / Auth — JWT_SECRET_KEY has no default on purpose (same
    # reasoning as MONGODB_URI: a real secret must be explicitly
    # provided, never silently defaulted). Token lifetimes have sensible
    # defaults per the architecture doc's auth flow (Section 6.1):
    # short-lived access tokens, longer-lived refresh tokens.
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ------------------------------------------------------------------
    # CORS — stored as the raw comma-separated string from the env var,
    # exposed as a parsed list via the property below. Kept as a plain
    # string field (rather than a list field) because env vars are text;
    # parsing happens in one place instead of relying on pydantic's
    # implicit list-from-string coercion, which is easy to misconfigure.
    # ------------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:5173"

    # ------------------------------------------------------------------
    # Environment / Debug
    # ------------------------------------------------------------------
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed, whitespace-trimmed list — what CORSMiddleware actually needs."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Used in main.py to disable /docs and /redoc outside development."""
        return self.ENVIRONMENT.lower() == "production"


# Singleton instance — imported directly as `from app.core.config import settings`
# everywhere else in the app. Because Settings() is only instantiated once,
# here, at module import time, the .env file is only read once per process.
settings = Settings()