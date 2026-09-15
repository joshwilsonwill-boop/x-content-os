import os
import json
import ssl
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from core.sources import RawSourceItem, SourceAdapter
from core.x_source_config import XQueryConfig
from core.logging import get_logger

logger = get_logger(__name__)

try:
    import certifi
    DEFAULT_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    DEFAULT_SSL_CONTEXT = None

X_SEARCH_ENDPOINT = "https://api.x.com/2/tweets/search/recent"
MAX_PAGES = 2  # Hard upper limit on pagination to respect rate limits
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB safety bound

class XAPIError(Exception):
    """Base exception for X API errors."""
    pass

class XAuthError(XAPIError):
    """Raised when X API authentication fails (401/403)."""
    pass

class XRateLimitError(XAPIError):
    """Raised when X API rate limit is exceeded (429)."""
    def __init__(self, message: str, reset_timestamp: Optional[int] = None):
        super().__init__(message)
        self.reset_timestamp = reset_timestamp

class XSourceAdapter:
    """
    Official X API v2 read-only recent search adapter.
    Implements the SourceAdapter protocol with bounded requests, pagination,
    and standard-library HTTP handling.
    """
    def __init__(
        self,
        config: XQueryConfig,
        bearer_token: Optional[str] = None,
        timeout: int = 10,
        max_pages: int = 1,
        endpoint: str = X_SEARCH_ENDPOINT
    ):
        self.config = config
        self.bearer_token = bearer_token or os.environ.get("X_BEARER_TOKEN", "").strip()
        self.timeout = timeout
        self.max_pages = min(MAX_PAGES, max(1, max_pages))
        self.endpoint = endpoint

    def fetch(self) -> List[RawSourceItem]:
        """Executes read-only recent search with bounded pagination."""
        if not self.bearer_token:
            raise XAuthError(
                "X_BEARER_TOKEN is not configured in environment. "
                "Add your official X API Bearer Token to .env to enable X intelligence."
            )

        items: List[RawSourceItem] = []
        next_token: Optional[str] = None
        current_page = 0

        while current_page < self.max_pages:
            current_page += 1
            payload = self._execute_search_request(next_token)
            page_items, next_token = self.parse_response(payload)
            items.extend(page_items)

            if not next_token:
                break

        logger.info(
            f"Retrieved {len(items)} posts across {current_page} page(s) for X query '{self.config.id}'"
        )
        return items

    def _execute_search_request(self, next_token: Optional[str] = None) -> Dict[str, Any]:
        """Performs a single authenticated GET request to the X recent search endpoint."""
        params = {
            "query": self.config.query,
            "max_results": str(self.config.max_results),
            "tweet.fields": "created_at,author_id,public_metrics,conversation_id,lang",
            "expansions": "author_id",
            "user.fields": "name,username,verified"
        }
        if next_token:
            params["next_token"] = next_token

        query_string = urllib.parse.urlencode(params)
        url = f"{self.endpoint}?{query_string}"

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": "x-content-os/1.0 (+https://github.com/joshwilsonwill-boop/x-content-os)"
            },
            method="GET"
        )

        kwargs = {"timeout": self.timeout}
        if DEFAULT_SSL_CONTEXT is not None and url.startswith("https://"):
            kwargs["context"] = DEFAULT_SSL_CONTEXT

        try:
            with urllib.request.urlopen(req, **kwargs) as resp:
                raw_bytes = resp.read(MAX_RESPONSE_BYTES + 1)
                if len(raw_bytes) > MAX_RESPONSE_BYTES:
                    raise ValueError(f"X API response exceeded {MAX_RESPONSE_BYTES} bytes")
                text = raw_bytes.decode("utf-8")
                return json.loads(text)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise XAuthError(
                    f"X API access rejected (HTTP {e.code}). Verify X_BEARER_TOKEN access level."
                ) from e
            elif e.code == 429:
                reset_header = e.headers.get("x-rate-limit-reset")
                reset_ts = int(reset_header) if reset_header and reset_header.isdigit() else None
                raise XRateLimitError(
                    f"X API rate limit exceeded (HTTP 429). Reset at timestamp {reset_ts}.",
                    reset_timestamp=reset_ts
                ) from e
            else:
                raise XAPIError(f"X API HTTP error {e.code}: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise XAPIError(f"Malformed JSON response from X API: {e}") from e
        except Exception as e:
            if isinstance(e, XAPIError):
                raise
            raise XAPIError(f"Network error querying X API for '{self.config.id}': {e}") from e

    def parse_response(self, payload: Dict[str, Any]) -> tuple[List[RawSourceItem], Optional[str]]:
        """Parses an official X API v2 recent search JSON payload into RawSourceItem list."""
        if not isinstance(payload, dict):
            return [], None

        tweets = payload.get("data", [])
        if not isinstance(tweets, list):
            return [], None

        # Build author lookup map from includes.users
        users_by_id: Dict[str, Dict[str, Any]] = {}
        includes = payload.get("includes", {})
        if isinstance(includes, dict):
            for u in includes.get("users", []):
                if isinstance(u, dict) and "id" in u:
                    users_by_id[str(u["id"])] = u

        items: List[RawSourceItem] = []
        for tweet in tweets:
            if not isinstance(tweet, dict):
                continue

            tweet_id = str(tweet.get("id", "")).strip()
            text = str(tweet.get("text", "")).strip()
            if not tweet_id or not text:
                continue

            author_id = str(tweet.get("author_id", ""))
            author_info = users_by_id.get(author_id, {})
            username = author_info.get("username", "unknown")
            display_name = author_info.get("name", username)
            author_str = f"@{username} ({display_name})" if display_name != username else f"@{username}"

            # Canonical X post URL
            if username and username != "unknown":
                canonical_url = f"https://x.com/{username}/status/{tweet_id}"
            else:
                canonical_url = f"https://x.com/i/status/{tweet_id}"

            # Parse created_at timestamp
            created_at_str = tweet.get("created_at")
            published_at = self._parse_iso_datetime(created_at_str)

            # Extract title summary (first sentence or up to 80 chars)
            first_line = text.split("\n")[0].strip()
            title = first_line[:80].strip()
            if len(first_line) > 80:
                title += "..."

            metrics = tweet.get("public_metrics", {})
            raw_metadata = {
                "tweet_id": tweet_id,
                "author_id": author_id,
                "username": username,
                "name": display_name,
                "public_metrics": metrics,
                "conversation_id": tweet.get("conversation_id"),
                "lang": tweet.get("lang"),
                "query_id": self.config.id,
                "query": self.config.query
            }

            items.append(RawSourceItem(
                source_id=f"x_{self.config.id}",
                source_type="x",
                external_id=tweet_id,
                title=title,
                content=text,
                url=canonical_url,
                author=author_str,
                topic=self.config.topic,
                published_at=published_at,
                raw_metadata=raw_metadata
            ))

        # Extract next_token from meta
        meta = payload.get("meta", {})
        next_token = meta.get("next_token") if isinstance(meta, dict) else None

        return items, next_token

    def _parse_iso_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """Safely parses ISO 8601 UTC datetimes returned by X API v2."""
        if not date_str:
            return None
        try:
            clean = date_str.strip()
            if clean.endswith("Z"):
                clean = clean[:-1] + "+00:00"
            dt = datetime.fromisoformat(clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
