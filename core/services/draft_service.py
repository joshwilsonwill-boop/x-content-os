from sqlalchemy.orm import Session
from core.models import Draft
from core.logging import get_logger, log_action

logger = get_logger(__name__)

def create_draft(db: Session, idea_id: int, text: str, format: str = "Observation", status: str = "UNDER_REVIEW") -> Draft:
    draft = Draft(
        idea_id=idea_id,
        text=text,
        format=format,
        status=status
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    log_action(logger, 20, "draft", "created", "success", object_id=f"draft_{draft.id}")
    return draft

def get_drafts_awaiting_review(db: Session):
    return db.query(Draft).filter(Draft.status == "UNDER_REVIEW").all()

def update_draft_status(db: Session, draft_id: int, status: str) -> Draft:
    draft = db.query(Draft).filter(Draft.id == draft_id).first()
    if draft:
        draft.status = status
        db.commit()
        db.refresh(draft)
        action_name = status.lower()
        log_action(logger, 20, "draft", action_name, "success", object_id=f"draft_{draft.id}")
    return draft

from core.quality_gate import run_quality_gate

def update_draft_text(db: Session, draft_id: int, text: str) -> Draft:
    draft = db.query(Draft).filter(Draft.id == draft_id).first()
    if draft:
        q_result = run_quality_gate(db, text)
        status = "FAILED" if not q_result.passed else "UNDER_REVIEW"
        
        draft.text = text
        draft.status = status
        draft.quality_score = q_result.overall_score
        # update char count
        from core.x_character_count import count as count_characters
        draft.character_count = count_characters(text)
        
        db.commit()
        db.refresh(draft)
        log_action(logger, 20, "draft", "edited", "success", object_id=f"draft_{draft.id}")
    return draft
