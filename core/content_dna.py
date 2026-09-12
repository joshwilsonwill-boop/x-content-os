import yaml
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class ContentDNA:
    positioning: str
    audience: str
    pillars: List[str]
    recurring_beliefs: List[str]
    recurring_arguments: List[str]
    preferred_vocabulary: List[str]
    banned_cliches: List[str]
    banned_phrases: List[str]
    preferred_sentence_length: str
    preferred_post_length: str
    acceptable_levels_of_controversy: str
    tone: str
    humour_level: str
    personal_story_preference: str
    technical_depth: str
    cta_policy: str
    hashtag_policy: str
    link_policy: str

def load_content_dna(filepath: str = "config/content_dna.yaml") -> ContentDNA:
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    return ContentDNA(
        positioning=data.get("account_positioning", ""),
        audience=data.get("audience", ""),
        pillars=data.get("content_pillars", []),
        recurring_beliefs=data.get("recurring_beliefs", []),
        recurring_arguments=data.get("recurring_arguments", []),
        preferred_vocabulary=data.get("preferred_vocabulary", []),
        banned_cliches=data.get("banned_clichés", []),
        banned_phrases=data.get("banned_phrases", []),
        preferred_sentence_length=data.get("preferred_sentence_length", ""),
        preferred_post_length=data.get("preferred_post_length", ""),
        acceptable_levels_of_controversy=data.get("acceptable_levels_of_controversy", ""),
        tone=data.get("tone", ""),
        humour_level=data.get("humour_level", ""),
        personal_story_preference=data.get("personal_story_preference", ""),
        technical_depth=data.get("technical_depth", ""),
        cta_policy=data.get("cta_policy", ""),
        hashtag_policy=data.get("hashtag_policy", ""),
        link_policy=data.get("link_policy", "")
    )
