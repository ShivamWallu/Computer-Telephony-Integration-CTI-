import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

# Automatically load and reload environment variables from .env file
load_dotenv(override=True)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="allow", env_file=".env", env_file_encoding="utf-8")

    PROJECT_NAME: str = "Enterprise CTI & Customer Management CRM"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./crm_database.db")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))

    # Security & JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-jwt-key-change-in-production-crm-system-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # CTI & Telephony
    CTI_WEBHOOK_SECRET: str = os.getenv("CTI_WEBHOOK_SECRET", "cti-secure-webhook-secret-token")
    DEFAULT_COUNTRY_CODE: str = os.getenv("DEFAULT_COUNTRY_CODE", "91")

    # Tata Smartflo Telephony API Configuration
    SMARTFLO_API_TOKEN: str = os.getenv("SMARTFLO_API_TOKEN", "")
    SMARTFLO_BASE_URL: str = os.getenv("SMARTFLO_BASE_URL", "https://api-smartflo.tatateleservices.com/v1")

    # Transactional Email - Safe Simulation / Mock Mode (Prevents sending real emails to official addresses)
    EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "mock")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "itchd.kogm@gmail.com")
    EMAIL_API_KEY: str = os.getenv("EMAIL_API_KEY", "")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "itchd.kogm@gmail.com")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "otiuncukbgbskxfk")
    SMTP_TLS: bool = os.getenv("SMTP_TLS", "true").lower() == "true"

    # TCS iON ERP Automation Configuration
    TCSION_LOGIN_URL: str = os.getenv("TCSION_LOGIN_URL", "https://training.tcsion.com/Login/Login.html")
    TCSION_USERNAME: str = os.getenv("TCSION_USERNAME", "trng_infotech@khandelia.com")
    TCSION_PASSWORD: str = os.getenv("TCSION_PASSWORD", "Pass!@#32132")
    TCSION_HEADLESS: bool = os.getenv("TCSION_HEADLESS", "true").lower() == "true"

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

settings = Settings()
