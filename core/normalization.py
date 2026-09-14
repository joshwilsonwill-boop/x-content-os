import re
import html
import hashlib
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import Tuple
from core.sources import RawSourceItem

TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_cid", "utm_reader", "fbclid", "gclid", "ref", "source"
}

def clean_html_and_entities(text: str) -> str:
    """Strips HTML markup and unescapes HTML entities."""
    if not text:
        return ""
    # Unescape HTML entities (&amp;, &#39;, &lt;, &gt;, etc.)
    clean = html.unescape(text)
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", " ", clean)
    # Consolidate whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean

def canonicalize_url(url: str) -> str:
    """Canonicalizes a URL by stripping tracking parameters, trailing slashes, and lowercasing host."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        scheme = (parsed.scheme or "http").lower()
        netloc = parsed.netloc.lower()
        
        # Strip trailing slash from path (unless path is just '/')
        path = parsed.path.rstrip("/")
        
        # Filter out tracking query params
        query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
        filtered_query = [
            (k, v) for (k, v) in query_pairs 
            if k.lower() not in TRACKING_QUERY_PARAMS
        ]
        # Sort query params for deterministic ordering
        filtered_query.sort(key=lambda x: x[0])
        new_query = urlencode(filtered_query)
        
        return urlunparse((scheme, netloc, path, "", new_query, ""))
    except Exception:
        return url.strip().rstrip("/")

def compute_content_hash(canonical_url: str, title: str, content: str) -> str:
    """
    Computes a deterministic SHA-256 content hash based on
    canonical URL, normalized title, and the first 250 characters of normalized content.
    """
    payload = f"{canonical_url}|{title.lower().strip()}|{content[:250].lower().strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def normalize_source_item(item: RawSourceItem) -> Tuple[str, str, str, str]:
    """
    Returns (normalized_title, normalized_content, canonical_url, content_hash).
    Handles missing titles, HTML entities, whitespace, and tracking URLs.
    """
    clean_title = clean_html_and_entities(item.title)
    clean_content = clean_html_and_entities(item.content)
    clean_url = canonicalize_url(item.url)
    
    if not clean_title:
        if clean_content:
            clean_title = clean_content[:60].strip() + "..."
        elif clean_url:
            clean_title = f"Signal from {clean_url}"
        else:
            clean_title = f"Signal from {item.source_id}"

    if not clean_content:
        clean_content = clean_title

    content_hash = compute_content_hash(clean_url, clean_title, clean_content)
    return clean_title, clean_content, clean_url, content_hash
