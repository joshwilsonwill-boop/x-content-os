import os
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.models import SourceItem, Idea, Draft
from core.source_config import load_sources_config, SourceConfig
from core.sources import RSSSourceAdapter, RawSourceItem
from core.normalization import (
    clean_html_and_entities,
    canonicalize_url,
    compute_content_hash,
    normalize_source_item
)
from core.opportunity_scoring import score_opportunity
from core.services.ingestion_service import (
    is_duplicate,
    ingest_raw_items,
    run_ingestion,
    IngestionResult
)
from core.services import opportunity_service
from core.telegram_bot import (
    build_opportunity_keyboard,
    format_opportunity_card
)

# Sample RSS and Atom XML fixtures
RSS_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Tech Feed</title>
    <link>https://example.com</link>
    <description>A test feed</description>
    <item>
      <title>Breaking: Major &lt;b&gt;Security Vulnerability&lt;/b&gt; Discovered in Architecture</title>
      <link>https://example.com/item1?utm_source=twitter&amp;utm_medium=social</link>
      <guid>https://example.com/item1</guid>
      <description>&lt;p&gt;A major flaw in the distributed database system was found. Latency dropped by 45%.&lt;/p&gt;</description>
      <pubDate>Mon, 14 Sep 2026 08:00:00 GMT</pubDate>
      <author>security_expert</author>
    </item>
    <item>
      <title>Simple Post About Tools</title>
      <link>https://example.com/item2/</link>
      <guid>guid-item-2</guid>
      <description>Discussion on developer tooling.</description>
      <pubDate>Sun, 13 Sep 2026 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM_SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Sample Atom Feed</title>
  <link href="https://example.com/atom" rel="self"/>
  <entry>
    <title>Atom Architecture Release</title>
    <id>urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a</id>
    <link href="https://example.com/atom-entry-1" rel="alternate"/>
    <summary>Engineering release notes for the new protocol version.</summary>
    <published>2026-09-14T09:00:00Z</published>
    <author><name>Alex</name></author>
  </entry>
</feed>
"""

MALFORMED_XML = """<rss version="2.0"><channel><item><title>Unclosed tag</channel></rss>"""

@pytest.fixture(scope="module")
def engine():
    return create_engine("sqlite:///:memory:")

@pytest.fixture(scope="module")
def tables(engine):
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)

@pytest.fixture
def db(engine, tables):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()

# 1. Configuration tests
def test_sources_config_loading(tmp_path):
    # Valid config
    valid_cfg_path = tmp_path / "sources_valid.yaml"
    valid_cfg_path.write_text("""
sources:
  - id: feed_1
    type: rss
    name: Feed One
    url: https://example.com/rss
    enabled: true
    topics:
      - cybersecurity
  - id: feed_2
    type: rss
    name: Feed Two
    url: https://example.com/rss2
    enabled: false
""", encoding="utf-8")

    configs = load_sources_config(str(valid_cfg_path))
    assert len(configs) == 2
    assert configs[0].id == "feed_1"
    assert configs[0].enabled is True
    assert configs[0].topics == ["cybersecurity"]
    assert configs[1].enabled is False

    # Missing file returns empty
    assert load_sources_config("nonexistent.yaml") == []

    # Malformed YAML
    malformed_path = tmp_path / "sources_malformed.yaml"
    malformed_path.write_text("sources: [not a valid source dict]", encoding="utf-8")
    assert load_sources_config(str(malformed_path)) == []

# 2. RSS Ingestion & Parsing tests
def test_rss_adapter_parsing():
    conf = SourceConfig(id="test_rss", type="rss", name="Test", url="https://example.com", topics=["software"])
    adapter = RSSSourceAdapter(conf)

    # RSS 2.0
    items = adapter.parse_xml(RSS_SAMPLE_XML)
    assert len(items) == 2
    assert "Security Vulnerability" in items[0].title
    assert items[0].url == "https://example.com/item1?utm_source=twitter&utm_medium=social"
    assert items[0].external_id == "https://example.com/item1"
    assert items[0].author == "security_expert"
    assert items[0].published_at is not None
    assert items[0].topic == "software"

    # Atom Feed
    atom_items = adapter.parse_xml(ATOM_SAMPLE_XML)
    assert len(atom_items) == 1
    assert atom_items[0].title == "Atom Architecture Release"
    assert atom_items[0].external_id == "urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a"
    assert atom_items[0].url == "https://example.com/atom-entry-1"
    assert atom_items[0].author == "Alex"
    assert atom_items[0].published_at is not None

    # Empty feed
    assert adapter.parse_xml("") == []
    assert adapter.parse_xml(b"   ") == []

    # Malformed feed recovers gracefully
    assert adapter.parse_xml(MALFORMED_XML) == []

# 3. Normalization tests
def test_normalization():
    # Whitespace and HTML tags / entities
    raw_text = "   Breaking: &lt;b&gt;New &amp; Exciting&lt;/b&gt;   Update   "
    clean = clean_html_and_entities(raw_text)
    assert clean == "Breaking: New & Exciting Update"

    # Canonical URL stripping
    url = "https://EXAMPLE.com/path/to/page/?utm_source=rss&utm_medium=feed&ref=123&keep=yes"
    canon = canonicalize_url(url)
    assert "utm_source" not in canon
    assert "utm_medium" not in canon
    assert "ref" not in canon
    assert "keep=yes" in canon
    assert canon.startswith("https://example.com/path/to/page")

    # Missing title fallback
    raw_item = RawSourceItem(
        source_id="test",
        source_type="rss",
        external_id="1",
        title="",
        content="<p>This is a long description about software engineering architecture.</p>",
        url="https://example.com/item"
    )
    norm_title, norm_content, norm_url, content_hash = normalize_source_item(raw_item)
    assert norm_title.startswith("This is a long description")
    assert "<p>" not in norm_content
    assert len(content_hash) == 64

# 4. Deduplication tests
def test_deduplication(db):
    raw_item = RawSourceItem(
        source_id="feed1",
        source_type="rss",
        external_id="ext-100",
        title="Unique Architecture Guide",
        content="How to build robust systems.",
        url="https://example.com/unique-guide"
    )
    # First ingestion
    res1 = ingest_raw_items(db, [raw_item])
    assert res1.new_items == 1
    assert res1.duplicates == 0

    # Second ingestion with same external_id
    res2 = ingest_raw_items(db, [raw_item])
    assert res2.new_items == 0
    assert res2.duplicates == 1

    # Ingestion with same canonical URL but different source_id
    dup_url_item = RawSourceItem(
        source_id="feed2",
        source_type="rss",
        external_id="ext-200",
        title="Different Title",
        content="Different content",
        url="https://example.com/unique-guide?utm_source=twitter" # Canonicalizes to same URL
    )
    res3 = ingest_raw_items(db, [dup_url_item])
    assert res3.new_items == 0
    assert res3.duplicates == 1

    # Distinct item passes
    distinct_item = RawSourceItem(
        source_id="feed1",
        source_type="rss",
        external_id="ext-300",
        title="Completely Unrelated Database Failure Postmortem",
        content="Latency dropped and servers restarted.",
        url="https://example.com/postmortem"
    )
    res4 = ingest_raw_items(db, [distinct_item])
    assert res4.new_items == 1
    assert res4.duplicates == 0

# 5. Opportunity Scoring tests
def test_opportunity_scoring():
    now = datetime.now(timezone.utc)
    
    # Fresh, high-relevance technical item
    high_res = score_opportunity(
        title="Critical Security Vulnerability in Distributed Database Architecture",
        content="Latency dropped by 30% after memory failure. Lessons for systems engineering.",
        published_at=now - timedelta(hours=2),
        topic="Cybersecurity"
    )
    assert high_res.relevance_score >= 10
    assert high_res.freshness_score >= 18
    assert high_res.audience_value_score >= 10
    assert high_res.spam_risk_score <= 2
    assert high_res.overall_score >= 70
    assert "Relevant to pillar" in high_res.why_it_matters

    # Stale item
    stale_res = score_opportunity(
        title="Critical Security Vulnerability in Database",
        content="Old postmortem.",
        published_at=now - timedelta(days=20),
        topic="Cybersecurity"
    )
    assert stale_res.freshness_score < high_res.freshness_score
    assert stale_res.overall_score < high_res.overall_score

    # Low-value spam/marketing item
    spam_res = score_opportunity(
        title="We Are Thrilled to Announce Our Revolutionary 100x Game Changer",
        content="Free giveaway and airdrop for a limited time offer! Mind blowing profits.",
        published_at=now - timedelta(hours=1),
        topic="Web3"
    )
    assert spam_res.spam_risk_score >= 7
    assert spam_res.overall_score < high_res.overall_score

    # Determinism
    res_a = score_opportunity("Test Title", "Test Content", published_at=now)
    res_b = score_opportunity("Test Title", "Test Content", published_at=now)
    assert res_a.overall_score == res_b.overall_score
    assert res_a.relevance_score == res_b.relevance_score

# 6. Opportunity Lifecycle & Drafting tests
def test_opportunity_lifecycle_and_drafting(db):
    item = SourceItem(
        source_id="test_feed",
        source_type="rss",
        external_id="opp-lifecycle-1",
        title="Postmortem: How Simple Systems Live Longer",
        content="Technical breakdown of caching layers.",
        url="https://example.com/systems",
        topic="Software",
        opportunity_score=85,
        relevance_score=18,
        freshness_score=19,
        original_angle_score=17,
        audience_value_score=16,
        conversation_score=9,
        spam_risk_score=1,
        status="NEW"
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    # Initial status is NEW
    assert item.status == "NEW"

    # SAVE action
    saved_item = opportunity_service.save_opportunity(db, item.id)
    assert saved_item.status == "SAVED"

    # DRAFT action from SAVED
    idea = opportunity_service.draft_opportunity(db, item.id)
    assert idea is not None
    assert idea.source_item_id == item.id
    assert "Postmortem: How Simple Systems Live Longer" in idea.raw_text
    assert item.status == "DRAFTED"

    # IGNORE action on a distinct item
    item2 = SourceItem(
        source_id="test_feed",
        source_type="rss",
        external_id="opp-lifecycle-2",
        title="Ignored Test Post",
        content="Testing ignore lifecycle.",
        status="NEW"
    )
    db.add(item2)
    db.commit()
    db.refresh(item2)

    ignored_item = opportunity_service.ignore_opportunity(db, item2.id)
    assert ignored_item.status == "IGNORED"
    assert opportunity_service.draft_opportunity(db, item2.id) is None

    # Expiration
    stale_item = SourceItem(
        source_id="test_feed",
        source_type="rss",
        external_id="opp-lifecycle-stale",
        title="Very Old News",
        content="Old info.",
        status="NEW",
        discovered_at=datetime.now(timezone.utc) - timedelta(days=20)
    )
    db.add(stale_item)
    db.commit()
    
    expired_count = opportunity_service.expire_stale_opportunities(db, max_age_days=14)
    assert expired_count >= 1
    db.refresh(stale_item)
    assert stale_item.status == "EXPIRED"

# 7. Telegram formatting & compact buttons tests
def test_telegram_opportunity_card_and_buttons():
    item = SourceItem(
        id=42,
        source_id="techcrunch_rss",
        source_type="rss",
        title="<script>alert(1)</script> AI Infrastructure Breakthrough",
        content="Detailed overview.",
        url="https://example.com/ai-infra",
        topic="AI & Technology",
        opportunity_score=84,
        relevance_score=18,
        freshness_score=19,
        original_angle_score=17,
        audience_value_score=16,
        conversation_score=9,
        spam_risk_score=2,
        status="NEW"
    )

    card = format_opportunity_card(item)
    assert "OPPORTUNITY #42" in card
    assert "techcrunch_rss" in card
    assert "84/100" in card
    # Verify HTML escaping prevents script injection
    assert "<script>" not in card
    assert "&lt;script&gt;" in card

    kb = build_opportunity_keyboard(item)
    # Check compact identifiers
    all_callbacks = [
        btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data
    ]
    all_urls = [
        btn.url for row in kb.inline_keyboard for btn in row if btn.url
    ]
    assert "opp_draft_42" in all_callbacks
    assert "opp_save_42" in all_callbacks
    assert "opp_ignore_42" in all_callbacks
    # OPEN SOURCE is a direct clean URL, not arbitrary shell or script execution
    assert "https://example.com/ai-infra" in all_urls

# 8. Hardening: Idempotent drafting & status guards
def test_idempotent_opportunity_drafting(db):
    item = SourceItem(
        source_id="test_idempotent",
        source_type="rss",
        external_id="opp-idempotent-1",
        title="Idempotent Architecture Design",
        content="Testing repeated drafting calls.",
        url="https://example.com/idempotent",
        topic="Software",
        status="NEW"
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    # 1. First call creates exactly one Idea
    idea1 = opportunity_service.draft_opportunity(db, item.id)
    assert idea1 is not None
    assert idea1.source_item_id == item.id
    assert item.status == "DRAFTED"
    
    ideas_count_1 = db.query(Idea).filter(Idea.source_item_id == item.id).count()
    assert ideas_count_1 == 1

    # 2. Second call reuses existing Idea and does not create duplicate
    idea2 = opportunity_service.draft_opportunity(db, item.id)
    assert idea2 is not None
    assert idea2.id == idea1.id
    
    ideas_count_2 = db.query(Idea).filter(Idea.source_item_id == item.id).count()
    assert ideas_count_2 == 1

    # 3. Third call is also idempotent
    idea3 = opportunity_service.draft_opportunity(db, item.id)
    assert idea3.id == idea1.id
    assert db.query(Idea).filter(Idea.source_item_id == item.id).count() == 1

    # 4. IGNORED item cannot be drafted accidentally
    ignored_item = SourceItem(
        source_id="test_idempotent",
        source_type="rss",
        external_id="opp-ignored-1",
        title="Ignored Article",
        content="Should not be drafted.",
        status="IGNORED"
    )
    db.add(ignored_item)
    db.commit()
    db.refresh(ignored_item)

    res = opportunity_service.draft_opportunity(db, ignored_item.id)
    assert res is None
    assert ignored_item.status == "IGNORED"
    assert db.query(Idea).filter(Idea.source_item_id == ignored_item.id).count() == 0

# 9. Hardening: Future-dated freshness scoring
def test_future_dated_freshness_scoring():
    now = datetime.now(timezone.utc)

    # 1. Normal recent item (2h ago)
    recent_res = score_opportunity("Title", "Content", published_at=now - timedelta(hours=2))
    assert recent_res.freshness_score == 20

    # 2. Minor future clock skew (1h in future) -> conservative neutral score (8), NOT 20
    skew_res = score_opportunity("Title", "Content", published_at=now + timedelta(hours=1))
    assert skew_res.freshness_score == 8
    assert skew_res.freshness_score < recent_res.freshness_score

    # 3. Significantly future-dated item (48h in future) -> minimum score (2), NOT 20
    far_future_res = score_opportunity("Title", "Content", published_at=now + timedelta(hours=48))
    assert far_future_res.freshness_score == 2

    # 4. Old item (30d ago) -> minimum score (2)
    old_res = score_opportunity("Title", "Content", published_at=now - timedelta(days=30))
    assert old_res.freshness_score == 2

    # 5. Missing date -> neutral score (8)
    nodate_res = score_opportunity("Title", "Content", published_at=None)
    assert nodate_res.freshness_score == 8

# 10. Hardening: Response size limit
def test_rss_adapter_response_size_limit():
    conf = SourceConfig(id="test_limit", type="rss", name="Test Limit", url="https://example.com/feed")
    # Adapter with small 100-byte cap
    adapter = RSSSourceAdapter(conf, max_bytes=100)
    assert adapter.max_bytes == 100

    # Parsing XML directly still works
    items = adapter.parse_xml(RSS_SAMPLE_XML)
    assert len(items) == 2

