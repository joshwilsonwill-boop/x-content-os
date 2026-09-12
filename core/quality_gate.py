import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from core.content_dna import load_content_dna
from core.x_character_count import validate as validate_char_count
from core.repetition import calculate_similarity, detect_opening_pattern
from sqlalchemy.orm import Session
from core.models import Draft

@dataclass
class QualityResult:
    passed: bool
    overall_score: float
    character_valid: bool
    hook_score: float
    specificity_score: float
    usefulness_score: float
    originality_score: float
    voice_fit_score: float
    warnings: List[str]

def run_quality_gate(db: Session, text: str, pillar: Optional[str] = None) -> QualityResult:
    dna = load_content_dna()
    warnings = []
    passed = True
    
    # 1. Character Count
    char_result = validate_char_count(text)
    if not char_result.valid:
        passed = False
        warnings.append(f"CHARACTER LIMIT FAILED: {char_result.reason}")
        
    if not text.strip():
        passed = False
        warnings.append("EMPTY DRAFT")
        return QualityResult(False, 0.0, False, 0.0, 0.0, 0.0, 0.0, 0.0, warnings)

    # 2. Banned Phrases (Case insensitive)
    lower_text = text.lower()
    for phrase in dna.banned_phrases + dna.banned_cliches:
        if phrase.lower() in lower_text:
            passed = False
            warnings.append(f"BANNED PHRASE: '{phrase}'")

    # 3. Repetition Detection
    # Get recent 50 approved/published drafts
    recent_drafts = db.query(Draft).filter(
        Draft.status.in_(["APPROVED", "PUBLISHED"])
    ).order_by(Draft.created_at.desc()).limit(50).all()

    max_sim = 0.0
    opening_pattern = detect_opening_pattern(text)
    opening_count = 0

    for rd in recent_drafts:
        sim = calculate_similarity(text, rd.text)
        if sim > max_sim:
            max_sim = sim
        
        if detect_opening_pattern(rd.text) == opening_pattern:
            opening_count += 1
            
    if max_sim > 0.6:  # Arbitrary high similarity threshold
        passed = False
        warnings.append(f"DUPLICATION FAILED: High semantic similarity ({max_sim:.2f}) with a recent post.")
    elif max_sim > 0.4:
        warnings.append(f"DUPLICATION WARNING: Moderate semantic similarity ({max_sim:.2f}).")
        
    if opening_count >= 3:
        warnings.append(f"PATTERN FATIGUE: Opening pattern '{opening_pattern}' used {opening_count} times recently.")

    # 4. Deterministic pseudo-scoring for Phase 3 (since we don't have an LLM evaluator yet)
    # These are heuristics representing the score dimensions.
    # Hook score: does it start with a short punchy sentence?
    first_sentence = text.split('.')[0] if '.' in text else text
    hook_score = 9.0 if len(first_sentence) < 50 else 6.0
    
    # Specificity: does it use numbers, capitalization (proper nouns), or specific quotes?
    has_numbers = bool(re.search(r'\d+', text))
    specificity_score = 8.5 if has_numbers else 7.0
    
    # Voice fit: matches preferred vocabulary?
    vocab_matches = sum(1 for v in dna.preferred_vocabulary if v.lower() in lower_text)
    voice_fit_score = min(10.0, 7.0 + vocab_matches)
    
    # Usefulness: contains "how to", "why", or bullet points?
    usefulness_score = 8.0 if ("\n-" in text or "why" in lower_text) else 7.0
    
    # Originality: inversely proportional to max similarity
    originality_score = max(0.0, 10.0 - (max_sim * 10))

    overall_score = round(sum([hook_score, specificity_score, voice_fit_score, usefulness_score, originality_score]) / 5, 1)

    return QualityResult(
        passed=passed,
        overall_score=overall_score,
        character_valid=char_result.valid,
        hook_score=hook_score,
        specificity_score=specificity_score,
        usefulness_score=usefulness_score,
        originality_score=originality_score,
        voice_fit_score=voice_fit_score,
        warnings=warnings
    )
