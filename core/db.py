import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from core.logging import get_logger

logger = get_logger(__name__)

# Use SQLite by default if not provided
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/content_os.db")

# Isolate database access so we can replace sqlite with postgres later
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    from core.models import Idea, Draft, AppState, SourceItem  # Import models here to ensure they are registered
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized", extra={"component": "db", "action": "init", "status": "success"})

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
