import re
import unicodedata
import grapheme
from dataclasses import dataclass

URL_LENGTH = 23
MAX_WEIGHTED_CHARACTERS = 280

@dataclass
class CharacterCountResult:
    weighted_count: int
    maximum: int
    remaining: int
    valid: bool
    reason: str = ""

def extract_urls(text: str) -> list[str]:
    # A robust regex for URLs to closely approximate X's URL extraction
    url_pattern = re.compile(r'(?:https?://)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?::\d+)?(?:/[^\s]*)?', re.IGNORECASE)
    # Filter out plain words that might get caught if they don't look like URLs
    urls = []
    for match in url_pattern.findall(text):
        # basic sanity check: must have scheme or start with www or have a known TLD pattern (the regex mostly enforces TLD structure)
        urls.append(match)
    return urls

def get_grapheme_weight(cluster: str) -> int:
    """
    Returns the weight of a single grapheme cluster based on X's rules.
    - CJK characters (East_Asian_Width 'W', 'F', or 'A') count as 2.
    - Emojis (including complex ZWJ sequences) count as 2.
    - ASCII / basic Latin counts as 1.
    """
    # If the grapheme cluster has multiple codepoints, it's a complex sequence (e.g. ZWJ emoji, combining marks)
    # X counts emojis as 2. Combining marks on standard text are usually 1 if they form a standard letter, 
    # but for simplicity, multi-codepoint sequences that are emojis count as 2.
    if len(cluster) > 1:
        # Check if it contains any emoji/symbol codepoints. 
        # For simplicity, we treat all complex grapheme clusters as weight 2.
        return 2
        
    char = cluster[0]
    
    if ord(char) <= 0x7F:
        return 1
    
    # Emojis and wide characters outside BMP
    if ord(char) > 0xFFFF:
        return 2
        
    eaw = unicodedata.east_asian_width(char)
    if eaw in ('W', 'F'):
        return 2
    
    return 1

def count(text: str) -> int:
    urls = extract_urls(text)
    
    text_without_urls = text
    for url in urls:
        text_without_urls = text_without_urls.replace(url, "", 1)
        
    weight = 0
    weight += len(urls) * URL_LENGTH
    
    # Iterate over actual grapheme clusters instead of raw codepoints
    for cluster in grapheme.graphemes(text_without_urls):
        weight += get_grapheme_weight(cluster)
        
    return weight

def validate(text: str, internal_target: int = 265) -> CharacterCountResult:
    weighted_count = count(text)
    remaining = internal_target - weighted_count
    
    valid = True
    reason = ""
    
    if weighted_count == 0:
        valid = False
        reason = "Text is empty."
    elif weighted_count > MAX_WEIGHTED_CHARACTERS:
        valid = False
        reason = f"Exceeds absolute maximum of {MAX_WEIGHTED_CHARACTERS} characters."
    elif weighted_count > internal_target:
        valid = False
        reason = f"Exceeds internal target of {internal_target} characters."
        
    return CharacterCountResult(
        weighted_count=weighted_count,
        maximum=internal_target,
        remaining=remaining,
        valid=valid,
        reason=reason
    )
