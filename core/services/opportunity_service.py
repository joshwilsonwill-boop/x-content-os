from typing import List, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.models import SourceItem, Idea
from core.logging import get_logger, log_action

logger = get_logger(__name__)

def get_opportunities(db: Session, status: Optional[str] = "NEW", limit: int = 10) -> List[SourceItem]:
    """Returns top opportunities ordered by opportunity_score desc."""
    query = db.query(SourceItem)
    if status:
        query = query.filter(SourceItem.status == status)
    return query.order_by(desc(SourceItem.opportunity_score)).limit(limit).all()

def get_opportunity(db: Session, opportunity_id: int) -> Optional[SourceItem]:
    return db.query(SourceItem).filter(SourceItem.id == opportunity_id).first()

def save_opportunity(db: Session, opportunity_id: int) -> Optional[SourceItem]:
    item = get_opportunity(db, opportunity_id)
    if item:
        item.status = "SAVED"
        db.commit()
        db.refresh(item)
        log_action(logger, 20, "opportunity", "saved", "success", object_id=f"opp_{item.id}")
    return item

def ignore_opportunity(db: Session, opportunity_id: int) -> Optional[SourceItem]:
    item = get_opportunity(db, opportunity_id)
    if item:
        item.status = "IGNORED"
        db.commit()
        db.refresh(item)
        log_action(logger, 20, "opportunity", "ignored", "success", object_id=f"opp_{item.id}")
    return item

def draft_opportunity(db: Session, opportunity_id: int) -> Optional[Idea]:
    """Converts a SourceItem into an Idea preserving provenance, and marks it DRAFTED.
    Idempotent: Repeated calls return the existing Idea without creating duplicates.
    Ignored items return None to prevent accidental resurrection.
    """
    item = get_opportunity(db, opportunity_id)
    if not item:
        return None

    # Guard: IGNORED items cannot be drafted directly
    if item.status == "IGNORED":
        logger.warning(f"Cannot draft ignored opportunity {opportunity_id}")
        return None

    # Guard: If already DRAFTED, return existing Idea
    if item.status == "DRAFTED":
        existing_idea = db.query(Idea).filter(Idea.source_item_id == item.id).first()
        if existing_idea:
            return existing_idea
        logger.warning(f"Opportunity {opportunity_id} is marked DRAFTED but missing Idea; creating Idea to restore provenance.")

    raw_text = f"{item.title}\n\n{item.content[:250]}".strip()
    idea = Idea(
        source=item.source_type or "source_signal",
        source_url=item.url,
        raw_text=raw_text,
        topic=item.topic,
        pillar=item.topic,
        source_item_id=item.id,
        status="RAW"
    )
    db.add(idea)
    item.status = "DRAFTED"
    db.commit()
    db.refresh(idea)
    db.refresh(item)

    log_action(logger, 20, "opportunity", "drafted", "success", object_id=f"opp_{item.id}", msg=f"Created idea_{idea.id}")
    return idea

def expire_stale_opportunities(db: Session, max_age_days: int = 14) -> int:
    """Marks items in NEW status older than max_age_days as EXPIRED."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    stale_items = db.query(SourceItem).filter(
        SourceItem.status == "NEW",
        SourceItem.discovered_at < cutoff
    ).all()
    count = 0
    for item in stale_items:
        item.status = "EXPIRED"
        count += 1
    if count > 0:
        db.commit()
        log_action(logger, 20, "opportunity", "expired", "success", msg=f"Expired {count} stale opportunities")
    return count
