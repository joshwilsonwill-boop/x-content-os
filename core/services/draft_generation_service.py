import uuid
from typing import List
from sqlalchemy.orm import Session
from core.models import Idea, Draft
from core.draft_generator import DraftGenerator
from core.quality_gate import run_quality_gate
from core.x_character_count import count as count_characters
from core.logging import get_logger, log_action

logger = get_logger(__name__)

def generate_drafts(
    db: Session, 
    idea_id: int, 
    structure_name: str, 
    generator: DraftGenerator, 
    variant_count: int = 3
) -> List[Draft]:
    idea = db.query(Idea).filter(Idea.id == idea_id).first()
    if not idea:
        return []
        
    group_id = str(uuid.uuid4())
    generated_texts = generator.generate(idea, structure_name, count=variant_count)
    
    drafts = []
    for i, text in enumerate(generated_texts):
        # Run quality gate
        q_result = run_quality_gate(db, text, pillar=idea.pillar)
        
        status = "UNDER_REVIEW"
        if not q_result.passed:
            status = "FAILED"
            
        draft = Draft(
            idea_id=idea.id,
            group_id=group_id,
            variant_number=i + 1,
            generation_method="deterministic_template",
            text=text,
            format=structure_name,
            status=status,
            character_count=count_characters(text),
            quality_score=q_result.overall_score
        )
        db.add(draft)
        drafts.append(draft)
        
    db.commit()
    for d in drafts:
        db.refresh(d)
        log_action(logger, 20, "draft", "generated", "success", object_id=f"draft_{d.id}", msg=f"Status: {d.status}")
        
    return drafts

def get_draft_quality_report(db: Session, draft_id: int):
    draft = db.query(Draft).filter(Draft.id == draft_id).first()
    if not draft:
        return None
    return run_quality_gate(db, draft.text)
