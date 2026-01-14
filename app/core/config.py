from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from dotenv import load_dotenv
from typing import List

load_dotenv() 

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = Field(default="development", description="Environment: development, staging, production")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL connection string")
    DB_POOL_SIZE: int = Field(default=5, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, description="Max overflow connections")
    DB_POOL_RECYCLE: int = Field(default=3600, description="Recycle connections after N seconds")
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    
    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0", description="Celery broker URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/1", description="Celery result backend URL")
    CELERY_TASK_TIME_LIMIT: int = Field(default=600, description="Task hard time limit in seconds")
    CELERY_TASK_SOFT_TIME_LIMIT: int = Field(default=540, description="Task soft time limit in seconds")
    CELERY_TASK_MAX_RETRIES: int = Field(default=3, description="Max retries for failed tasks")
    
    # LLM API Keys
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API key")
    PERPLEXITY_API_KEY: str = Field(default="", description="Perplexity API key")
    PERPLEXITY_BASE_URL: str = Field(default="https://api.perplexity.ai", description="Perplexity API base URL")
    
    # Browser Automation
    BROWSER_USE_MODEL: str = Field(default="gpt-4o", description="Default model for browser automation")
    BROWSER_HEADLESS: bool = Field(default=True, description="Run browser in headless mode")
    BROWSER_TIMEOUT: int = Field(default=300, description="Browser task timeout in seconds")
    
    # CORS Settings for Android App
    CORS_ORIGINS: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins (use specific origins in production)"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="Allow credentials in CORS")
    CORS_ALLOW_METHODS: List[str] = Field(default=["*"], description="Allowed HTTP methods")
    CORS_ALLOW_HEADERS: List[str] = Field(default=["*"], description="Allowed HTTP headers")
    
    # API Settings
    API_V1_PREFIX: str = Field(default="/api/v1", description="API v1 route prefix")
    API_TITLE: str = Field(default="Premove Backend", description="API title")
    API_VERSION: str = Field(default="1.0.0", description="API version")
    
    # Authentication (optional - for future use)
    API_KEY_ENABLED: bool = Field(default=False, description="Enable API key authentication")
    JWT_SECRET_KEY: str = Field(default="", description="JWT secret key for token generation")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    JWT_EXPIRATION_HOURS: int = Field(default=24, description="JWT token expiration in hours")
    
    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL is required")
        if not v.startswith(("postgresql://", "postgresql+psycopg2://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow",
        case_sensitive=True
    )

settings = Settings()  # Global config object