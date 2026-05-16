import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "PhotoMatch")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-secret-key")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/photomatch.db")

    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@photomatch.local")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    ADMIN_NAME: str = os.getenv("ADMIN_NAME", "PhotoMatch Admin")
    
    GOOGLE_DRIVE_PARENT_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", "")
    GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")




settings = Settings()
