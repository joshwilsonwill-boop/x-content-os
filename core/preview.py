import html
import yaml
from typing import Optional
from sqlalchemy.orm import Session
from core.models import Draft, Idea
from core.quality_gate import run_quality_gate
from core.x_character_count import MAX_WEIGHTED_CHARACTERS

def load_preview_settings() -> dict:
    try:
        with open("config/settings.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("preview", {})
    except Exception:
        return {}

def generate_preview_html(db: Session, draft: Draft) -> str:
    settings = load_preview_settings()
    display_name = html.escape(settings.get("display_name", "Preview User"))
    handle = html.escape(settings.get("handle", "@preview"))
    
    # Run quality gate to get sub-scores and warnings
    # idea.pillar is needed for the gate
    idea = db.query(Idea).filter(Idea.id == draft.idea_id).first()
    pillar = idea.pillar if idea else "Unknown"
    
    q_result = run_quality_gate(db, draft.text, pillar=pillar)
    
    # Escape draft text for HTML
    # We use <pre> or just simple text mapping for Telegram HTML
    safe_text = html.escape(draft.text)
    
    # Determine Status
    if draft.status == "FAILED" or not q_result.passed:
        status_text = "FAILED"
    elif q_result.warnings:
        status_text = "WARNING"
    else:
        status_text = "PASS"

    warnings_block = ""
    if q_result.warnings:
        warnings_block = "<b>Warnings:</b>\n" + "\n".join(f"- {html.escape(w)}" for w in q_result.warnings) + "\n\n"

    # Assemble HTML
    preview = (
        f"<b>X PREVIEW</b>\n\n"
        f"👤 <b>{display_name}</b> {handle}\n\n"
        f"{safe_text}\n\n"
        f"<i>{draft.character_count}/{MAX_WEIGHTED_CHARACTERS} weighted characters</i>\n\n"
        f"<b>Quality: {q_result.overall_score}/10</b>\n"
        f"Hook: {q_result.hook_score}\n"
        f"Specificity: {q_result.specificity_score}\n"
        f"Usefulness: {q_result.usefulness_score}\n"
        f"Voice Fit: {q_result.voice_fit_score}\n"
        f"Originality: {q_result.originality_score}\n\n"
        f"Pillar: {html.escape(pillar)}\n"
        f"Structure: {html.escape(draft.format or 'None')}\n\n"
        f"{warnings_block}"
        f"Status: <b>{status_text}</b>"
    )
    
    return preview
