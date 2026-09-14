import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Dict, Any
from core.source_config import SourceConfig
from core.logging import get_logger

logger = get_logger(__name__)

@dataclass
class RawSourceItem:
    source_id: str
    source_type: str
    external_id: str
    title: str
    content: str
    url: str
    author: Optional[str] = None
    topic: Optional[str] = None
    published_at: Optional[datetime] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

class SourceAdapter(Protocol):
    def fetch(self) -> List[RawSourceItem]:
        """Fetch raw items from the underlying source."""
        ...

class RSSSourceAdapter:
    """
    Standard-library RSS 2.0 / RSS 1.0 / Atom feed parser.
    Zero external dependencies, fast, deterministic, and testable offline.
    """
    def __init__(self, config: SourceConfig, timeout: int = 10):
        self.config = config
        self.timeout = timeout

    def fetch(self) -> List[RawSourceItem]:
        req = urllib.request.Request(
            self.config.url,
            headers={"User-Agent": "x-content-os/1.0 (+https://github.com/joshwilsonwill-boop/x-content-os)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                xml_data = resp.read()
            return self.parse_xml(xml_data)
        except Exception as e:
            logger.error(f"Failed to fetch RSS feed {self.config.id} ({self.config.url}): {e}")
            raise

    def parse_xml(self, xml_bytes_or_str) -> List[RawSourceItem]:
        if isinstance(xml_bytes_or_str, str):
            xml_bytes = xml_bytes_or_str.encode("utf-8")
        else:
            xml_bytes = xml_bytes_or_str

        if not xml_bytes.strip():
            return []

        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            logger.warning(f"Malformed XML for source {self.config.id}: {e}")
            return []

        # Check for Atom feed: root.tag ends with 'feed'
        tag_lower = root.tag.lower()
        if "feed" in tag_lower:
            return self._parse_atom(root)
        else:
            return self._parse_rss(root)

    def _parse_rss(self, root: ET.Element) -> List[RawSourceItem]:
        items: List[RawSourceItem] = []
        
        # In RSS 2.0 items are under <channel>, in RSS 1.0 directly or under channel
        raw_items = root.findall(".//item")
        default_topic = self.config.topics[0] if self.config.topics else None

        for elem in raw_items:
            title = self._find_text(elem, ["title"]) or ""
            link = self._find_text(elem, ["link"]) or ""
            guid = self._find_text(elem, ["guid", "id"]) or link or title
            
            # Content/summary from description or content:encoded
            description = self._find_text(elem, [
                "description",
                "{http://purl.org/rss/1.0/modules/content/}encoded",
                "summary"
            ]) or ""
            
            author = self._find_text(elem, [
                "author",
                "{http://purl.org/dc/elements/1.1/}creator",
                "creator"
            ])
            
            pub_date_str = self._find_text(elem, ["pubDate", "date", "{http://purl.org/dc/elements/1.1/}date"])
            published_at = self._parse_date(pub_date_str)
            
            items.append(RawSourceItem(
                source_id=self.config.id,
                source_type="rss",
                external_id=guid.strip(),
                title=title.strip(),
                content=description.strip(),
                url=link.strip(),
                author=author.strip() if author else None,
                topic=default_topic,
                published_at=published_at,
                raw_metadata={"raw_pubdate": pub_date_str}
            ))

        return items

    def _parse_atom(self, root: ET.Element) -> List[RawSourceItem]:
        items: List[RawSourceItem] = []
        # Atom namespaces usually need handling
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        default_topic = self.config.topics[0] if self.config.topics else None

        # Search for entries with or without namespace
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        if not entries:
            entries = root.findall(".//entry")

        for elem in entries:
            title = self._find_text(elem, ["{http://www.w3.org/2005/Atom}title", "title"]) or ""
            
            # Link in Atom is often <link href="..."/>
            link = ""
            for l in elem.findall(".//{http://www.w3.org/2005/Atom}link"):
                href = l.get("href")
                rel = l.get("rel", "alternate")
                if href and rel in ("alternate", ""):
                    link = href
                    break
            if not link:
                for l in elem.findall(".//link"):
                    href = l.get("href")
                    if href:
                        link = href
                        break

            entry_id = self._find_text(elem, ["{http://www.w3.org/2005/Atom}id", "id"]) or link or title
            content = self._find_text(elem, [
                "{http://www.w3.org/2005/Atom}content",
                "{http://www.w3.org/2005/Atom}summary",
                "content",
                "summary"
            ]) or ""
            
            author = self._find_text(elem, [
                "{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name",
                "author/name",
                "author"
            ])
            
            published_str = self._find_text(elem, [
                "{http://www.w3.org/2005/Atom}published",
                "{http://www.w3.org/2005/Atom}updated",
                "published",
                "updated"
            ])
            published_at = self._parse_date(published_str)

            items.append(RawSourceItem(
                source_id=self.config.id,
                source_type="rss",
                external_id=entry_id.strip(),
                title=title.strip(),
                content=content.strip(),
                url=link.strip(),
                author=author.strip() if author else None,
                topic=default_topic,
                published_at=published_at,
                raw_metadata={"raw_pubdate": published_str}
            ))

        return items

    def _find_text(self, elem: ET.Element, tags: List[str]) -> Optional[str]:
        for tag in tags:
            found = elem.find(tag)
            if found is not None and found.text:
                return found.text
        return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        clean = date_str.strip()
        # Try RFC 2822 / 822 (common in RSS)
        try:
            dt = parsedate_to_datetime(clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass

        # Try ISO 8601 (common in Atom)
        try:
            # Replace trailing Z with +00:00
            if clean.endswith("Z"):
                clean = clean[:-1] + "+00:00"
            dt = datetime.fromisoformat(clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass

        return None
