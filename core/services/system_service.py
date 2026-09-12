from sqlalchemy.orm import Session
from core.models import AppState, Draft, Idea
from core.logging import get_logger, log_action

logger = get_logger(__name__)

def set_system_mode(db: Session, mode: str):
    state = db.query(AppState).filter(AppState.key == "system_mode").first()
    if not state:
        state = AppState(key="system_mode", value=mode)
        db.add(state)
    else:
        state.value = mode
    db.commit()
    log_action(logger, 20, "system", mode.lower(), "success")

def get_system_mode(db: Session) -> str:
    state = db.query(AppState).filter(AppState.key == "system_mode").first()
    return state.value if state else "RUNNING"

def get_stats(db: Session):
    ideas_count = db.query(Idea).count()
    drafts_review = db.query(Draft).filter(Draft.status == "UNDER_REVIEW").count()
    approved = db.query(Draft).filter(Draft.status == "APPROVED").count()
    rejected = db.query(Draft).filter(Draft.status == "REJECTED").count()
    return {
        "ideas": ideas_count,
        "drafts_review": drafts_review,
        "approved": approved,
        "rejected": rejected
    }
