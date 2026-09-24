from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///:memory:"
    api_base_url: str = "http://localhost:8000"
    redis_url: str | None = None
    default_country_code: str = "CO"
    default_currency: str = "COP"
    jwt_secret: str = "development-secret-change-me-erp-educativo-2026"
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173,https://school-intelligent-jet.vercel.app"
    rate_limit_enabled: bool = False
    rate_limit_per_tenant_per_minute: int = 300
    rate_limit_per_ip_per_minute: int = 60
    rate_limit_auth_per_ip_per_minute: int = 10
    rate_limit_window_seconds: int = 60

    @property
    def production_blockers(self) -> list[str]:
        blockers: list[str] = []
        if self.database_url.startswith("sqlite"):
            blockers.append("DATABASE_URL must use PostgreSQL in production")
        if self.jwt_secret.startswith("development-") or self.jwt_secret == "change-me-in-production":
            blockers.append("JWT_SECRET must be replaced in production")
        if self.cors_origins.strip() in {"", "*"}:
            blockers.append("CORS_ORIGINS must be explicitly restricted in production")
        if not self.api_base_url or self.api_base_url.strip() in {"", "*"}:
            blockers.append("API_BASE_URL must be configured in production")
        if self.environment == "production" and self.rate_limit_enabled and not self.redis_url:
            blockers.append("REDIS_URL must be configured when rate limiting is enabled in production")
        return blockers

    def validate_production_settings(self) -> None:
        if self.environment == "production" and self.production_blockers:
            raise RuntimeError("Production configuration is unsafe: " + "; ".join(self.production_blockers))

    @property
    def cors_list(self) -> list[str]:
        return list(dict.fromkeys(x.strip() for x in self.cors_origins.split(",") if x.strip()))

@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    get_settings.cache_clear()
