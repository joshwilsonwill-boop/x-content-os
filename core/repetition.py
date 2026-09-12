import re
from typing import List, Tuple

def normalize_text(text: str) -> str:
    # Lowercase and remove punctuation
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()

def get_tokens(text: str) -> List[str]:
    stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was", "were", "it", "this", "that"}
    normalized = normalize_text(text)
    tokens = normalized.split()
    return [t for t in tokens if t not in stop_words]

def get_ngrams(tokens: List[str], n: int = 3) -> set:
    if len(tokens) < n:
        return set(["_".join(tokens)])
    return set("_".join(tokens[i:i+n]) for i in range(len(tokens)-n+1))

def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity between two texts using 3-grams."""
    t1 = get_tokens(text1)
    t2 = get_tokens(text2)
    
    if not t1 or not t2:
        return 0.0
        
    set1 = get_ngrams(t1)
    set2 = get_ngrams(t2)
    
    if not set1 and not set2:
        return 0.0
        
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    
    return len(intersection) / len(union) if len(union) > 0 else 0.0

def detect_opening_pattern(text: str) -> str:
    """Extracts the first few words to detect repeated openings."""
    normalized = normalize_text(text)
    words = normalized.split()[:3]
    return " ".join(words)
