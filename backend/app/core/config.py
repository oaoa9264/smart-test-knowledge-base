import os
from typing import List

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./test_knowledge_base.db")
APP_ENV: str = os.getenv("APP_ENV", "development")

_cors_raw = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS: List[str] = [o.strip() for o in _cors_raw.split(",") if o.strip()]
