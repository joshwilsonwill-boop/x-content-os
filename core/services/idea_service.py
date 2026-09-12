from sqlalchemy.orm import Session
from core.models import Idea
from core.logging import get_logger, log_action

logger = get_logger(__name__)

def create_idea(db: Session, raw_text: str, source: str = "telegram") -> Idea:
    idea = Idea(
        source=source,
        raw_text=raw_text,
        status="RAW"
    )
    db.add(idea)
    db.commit()
    db.refresh(idea)
    log_action(logger, 20, "idea", "created", "success", object_id=f"idea_{idea.id}")
    return idea

def get_idea(db: Session, idea_id: int) -> Idea:
    return db.query(Idea).filter(Idea.id == idea_id).first()

def get_all_ideas(db: Session):
    return db.query(Idea).all()
