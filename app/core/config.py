"""
Core configuration module using Pydantic Settings.
Loads configuration from environment variables with validation.
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database Configuration
    database_url: str
    
    # Kafka Configuration
    kafka_bootstrap_servers: str
    
    # MinIO Configuration
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool = False
    
    # Security Configuration
    bcrypt_rounds: int = 12
    token_expiry_hours: int = 24
    
    # Application Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()
