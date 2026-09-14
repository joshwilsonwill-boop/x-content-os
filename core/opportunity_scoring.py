import re
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, List, Tuple
from core.content_dna import ContentDNA, load_content_dna

@dataclass
class OpportunityScoreResult:
    overall_score: int
    relevance_score: int
    freshness_score: int
    original_angle_score: int
    audience_value_score: int
    conversation_score: int
    spam_risk_score: int
    why_it_matters: str
    suggested_angle: str
    matched_pillar: str

SPAM_SIGNALS = [
    "thrilled to announce", "revolutionary", "game changer", "mind blowing",
    "presale", "airdrop", "100x", "guaranteed profit", "free giveaway",
    "limited time offer", "unprecedented growth", "paradigm shift"
]

TECHNICAL_VALUE_SIGNALS = [
    "architecture", "vulnerability", "performance", "benchmark", "postmortem",
    "database", "security", "release", "api", "protocol", "engineering",
    "latency", "failure", "production", "refactor", "open source"
]

CONVERSATION_SIGNALS = [
    "vs", "trade-off", "tradeoff", "why we", "should you", "failure",
    "lessons", "rethinking", "debate", "alternative", "migration"
]

def score_opportunity(
    title: str,
    content: str,
    published_at: Optional[datetime] = None,
    topic: Optional[str] = None,
    dna: Optional[ContentDNA] = None
) -> OpportunityScoreResult:
    """
    Scores an external source signal deterministically across 6 editorial dimensions:
    - Relevance (0-20)
    - Freshness (0-20)
    - Original Angle (0-20)
    - Audience Value (0-20)
    - Conversation (0-10)
    - Spam Risk (0-10) -> penalizes overall score
    """
    if dna is None:
        try:
            dna = load_content_dna()
        except Exception:
            dna = None

    text = f"{title} {content} {topic or ''}".lower()

    # 1. Relevance (0-20)
    relevance = 6
    matched_pillar = topic or "Technology"
    if dna:
        for pillar in dna.pillars:
            p_lower = pillar.lower()
            # Simple keyword match
            keywords = p_lower.split()
            if any(k in text for k in keywords if len(k) > 3):
                relevance += 4
                matched_pillar = pillar
                break
        for vocab in dna.preferred_vocabulary:
            if vocab.lower() in text:
                relevance += 2
    relevance = min(20, max(0, relevance))

    # 2. Freshness (0-20)
    freshness = 4
    if published_at:
        now = datetime.now(timezone.utc)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        age_hours = (now - published_at).total_seconds() / 3600.0
        
        if age_hours < 0:
            # Future-dated timestamp handling:
            # Minor clock skew (within 2 hours into future): conservative neutral score
            # Significant future date (>2 hours into future): minimum freshness
            if age_hours >= -2.0:
                freshness = 8
            else:
                freshness = 2
        elif age_hours <= 12:
            freshness = 20
        elif age_hours <= 24:
            freshness = 18
        elif age_hours <= 48:
            freshness = 14
        elif age_hours <= 120: # 5 days
            freshness = 9
        elif age_hours <= 336: # 14 days
            freshness = 5
        else:
            freshness = 2
    else:
        freshness = 8 # Default neutral freshness if date is omitted

    # 3. Original Angle (0-20)
    original_angle = 7
    if dna:
        for arg in dna.recurring_arguments:
            for w in arg.lower().split():
                if len(w) > 4 and w in text:
                    original_angle += 3
        for belief in dna.recurring_beliefs:
            for w in belief.lower().split():
                if len(w) > 4 and w in text:
                    original_angle += 2
    if any(sig in text for sig in ["problem", "mistake", "death of", "broken", "flaw", "hidden cost"]):
        original_angle += 4
    original_angle = min(20, max(0, original_angle))

    # 4. Audience Value (0-20)
    audience_value = 6
    for val_sig in TECHNICAL_VALUE_SIGNALS:
        if val_sig in text:
            audience_value += 3
    # Look for numbers/metrics indicating concrete substance
    if re.search(r"\b\d+(\.\d+)?(k|m|%|x|ms|s|gb|tb|kb)?\b", text):
        audience_value += 2
    audience_value = min(20, max(0, audience_value))

    # 5. Conversation Potential (0-10)
    conversation = 3
    for conv_sig in CONVERSATION_SIGNALS:
        if conv_sig in text:
            conversation += 2
    if "?" in title:
        conversation += 2
    conversation = min(10, max(0, conversation))

    # 6. Spam / Low-Value Risk (0-10)
    spam_risk = 1
    for spam_sig in SPAM_SIGNALS:
        if spam_sig in text:
            spam_risk += 3
    if dna:
        for banned in dna.banned_phrases + dna.banned_cliches:
            if banned.lower() in text:
                spam_risk += 3
    spam_risk = min(10, max(0, spam_risk))

    # Overall Calculation:
    # 20 + 20 + 20 + 20 + 10 = 90 max base, scaled and adjusted for risk
    raw_score = relevance + freshness + original_angle + audience_value + conversation - (spam_risk * 2)
    # Scale to 0-100 range
    overall_score = min(100, max(0, int(raw_score * (100.0 / 80.0))))

    # Deterministic Explanations
    why_it_matters = (
        f"Relevant to pillar '{matched_pillar}' with freshness score {freshness}/20. "
        f"Shows concrete technical substance for developers."
    )
    suggested_angle = (
        f"Contrarian observation on '{matched_pillar}': Highlight practical engineering trade-offs "
        f"and systems durability rather than hype."
    )

    return OpportunityScoreResult(
        overall_score=overall_score,
        relevance_score=relevance,
        freshness_score=freshness,
        original_angle_score=original_angle,
        audience_value_score=audience_value,
        conversation_score=conversation,
        spam_risk_score=spam_risk,
        why_it_matters=why_it_matters,
        suggested_angle=suggested_angle,
        matched_pillar=matched_pillar
    )
