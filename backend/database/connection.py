import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from backend.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

try:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        pass
except (ModuleNotFoundError, OperationalError) as exc:
    fallback_url = "sqlite:///./trading_bot_fallback.db"
    logger.warning(
        "Failed to connect to PostgreSQL (or psycopg2 not installed); falling back to SQLite database at %s. "
        "Error: %s",
        fallback_url,
        str(exc)
    )
    engine = create_engine(fallback_url, pool_pre_ping=True, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
