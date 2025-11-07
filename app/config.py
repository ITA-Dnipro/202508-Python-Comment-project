from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGO_URL: str
    MONGO_DB: str
    REDIS_URL: str

    # Celery config
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # External services
    NOTIFICATION_SERVICE_URL: str
    ANALYTICS_BROKER_URL: str

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
