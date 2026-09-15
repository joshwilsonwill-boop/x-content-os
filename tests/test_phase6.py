import os
import json
import pytest
import typing
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.models import SourceItem, Idea, Draft
from core.x_source_config import load_x_sources_config, XQueryConfig
from core.x_source import (
    XSourceAdapter,
    XAPIError,
    XAuthError,
    XRateLimitError
)
from core.opportunity_scoring import score_opportunity
from core.services.ingestion_service import (
    is_duplicate,
    ingest_raw_items,
    run_x_ingestion
)
from core.services import opportunity_service
from core.telegram_bot import (
    build_opportunity_keyboard,
    format_opportunity_card
)

# Mock X API v2 responses
MOCK_TWEET_PAYLOAD = {
    "data": [
        {
            "id": "18001001",
            "text": "Critical memory corruption bug in SQLite distributed consensus. We refactored the database engine and reduced latency by 45%. Here is our postmortem on simple systems architecture.",
            "created_at": "2026-09-14T12:00:00.000Z",
            "author_id": "9001",
            "conversation_id": "18001001",
            "lang": "en",
            "public_metrics": {
                "retweet_count": 8,
                "reply_count": 12,
                "like_count": 85,
                "quote_count": 3,
                "impression_count": 4500
            }
        },
        {
            "id": "18001002",
            "text": "Simple tips for maintaining software durability without unnecessary tech debt.",
            "created_at": "2026-09-14T10:00:00.000Z",
            "author_id": "9002",
            "conversation_id": "18001002",
            "lang": "en",
            "public_metrics": {
                "retweet_count": 2,
                "reply_count": 4,
                "like_count": 20,
                "quote_count": 0,
                "impression_count": 1100
            }
        }
    ],
    "includes": {
        "users": [
            {
                "id": "9001",
                "name": "Alice Systems",
                "username": "alice_sys"
            },
            {
                "id": "9002",
                "name": "Bob Builder",
                "username": "bob_builder"
            }
        ]
    },
    "meta": {
        "newest_id": "18001001",
        "oldest_id": "18001002",
        "result_count": 2,
        "next_token": "page_token_abc123"
    }
}

MOCK_PAGE_2_PAYLOAD = {
    "data": [
        {
            "id": "18001003",
            "text": "Page 2 discussion on backend systems refactoring.",
            "created_at": "2026-09-14T08:00:00.000Z",
            "author_id": "9001",
            "public_metrics": {"reply_count": 1, "like_count": 5}
        }
    ],
    "includes": {
        "users": [{"id": "9001", "name": "Alice Systems", "username": "alice_sys"}]
    },
    "meta": {
        "result_count": 1
    }
}

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
def test_x_source_config_loading(tmp_path):
    config_file = tmp_path / "test_x_sources.yaml"
    config_file.write_text("""
queries:
  - id: ai_dev
    query: "AI developer -is:retweet"
    enabled: true
    max_results: 15
    topic: "Technology"
  - id: disabled_q
    query: "crypto airdrop"
    enabled: false
    max_results: 5  # should be clamped to min 10
""", encoding="utf-8")

    configs = load_x_sources_config(str(config_file))
    assert len(configs) == 2
    assert configs[0].id == "ai_dev"
    assert configs[0].enabled is True
    assert configs[0].max_results == 15
    assert configs[1].enabled is False
    assert configs[1].max_results == 10  # Clamped to official min 10

    # Nonexistent file
    assert load_x_sources_config("nonexistent_x.yaml") == []

# 2. Authentication & Error Isolation tests
def test_x_source_adapter_auth_missing():
    conf = XQueryConfig(id="test_q", query="test query")
    # Adapter without token raises XAuthError
    adapter = XSourceAdapter(conf, bearer_token="")
    with pytest.raises(XAuthError) as exc_info:
        adapter.fetch()
    assert "X_BEARER_TOKEN is not configured" in str(exc_info.value)

# 3. Payload Parsing & Normalization tests
def test_x_source_adapter_parsing():
    conf = XQueryConfig(id="sys_query", query="SQLite architecture", topic="Software")
    adapter = XSourceAdapter(conf, bearer_token="mock_token")

    items, next_token = adapter.parse_response(MOCK_TWEET_PAYLOAD)
    assert len(items) == 2
    assert next_token == "page_token_abc123"

    item1 = items[0]
    assert item1.source_id == "x_sys_query"
    assert item1.source_type == "x"
    assert item1.external_id == "18001001"
    assert item1.author == "@alice_sys (Alice Systems)"
    assert item1.url == "https://x.com/alice_sys/status/18001001"
    assert "Critical memory corruption bug" in item1.title
    assert "Critical memory corruption bug" in item1.content
    assert item1.published_at == datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    assert item1.raw_metadata["public_metrics"]["reply_count"] == 12

    # Empty payload
    empty_items, empty_token = adapter.parse_response({"data": []})
    assert empty_items == []
    assert empty_token is None

    # Malformed payload
    malformed_items, _ = adapter.parse_response({})
    assert malformed_items == []

# 4. Bounded Pagination tests
def test_x_source_pagination_bounds():
    conf = XQueryConfig(id="page_q", query="test pagination")
    adapter = XSourceAdapter(conf, bearer_token="mock_token", max_pages=1)
    assert adapter.max_pages == 1

    adapter2 = XSourceAdapter(conf, bearer_token="mock_token", max_pages=10)
    # Capped at hard upper limit MAX_PAGES (2)
    assert adapter2.max_pages == 2

# 5. Cross-Query Deduplication tests
def test_x_post_deduplication_across_queries(db):
    conf_a = XQueryConfig(id="query_alpha", query="architecture")
    conf_b = XQueryConfig(id="query_beta", query="database")

    adapter_a = XSourceAdapter(conf_a, bearer_token="mock")
    adapter_b = XSourceAdapter(conf_b, bearer_token="mock")

    items_a, _ = adapter_a.parse_response(MOCK_TWEET_PAYLOAD)
    items_b, _ = adapter_b.parse_response(MOCK_TWEET_PAYLOAD)

    # First ingestion from Query Alpha
    res1 = ingest_raw_items(db, items_a)
    assert res1.new_items == 2
    assert res1.duplicates == 0

    # Second ingestion from Query Beta with the exact same tweets
    res2 = ingest_raw_items(db, items_b)
    assert res2.new_items == 0
    assert res2.duplicates == 2  # Deduplicated across queries!

# 6. Scoring with X metrics tests
def test_x_opportunity_scoring_with_metrics():
    now = datetime.now(timezone.utc)

    # High-signal technical conversation with active replies
    tech_metrics = {"reply_count": 14, "quote_count": 3, "retweet_count": 10, "like_count": 80}
    tech_res = score_opportunity(
        title="Distributed Database Architecture Postmortem",
        content="Our consensus latency dropped by 45% after SQLite engine refactoring.",
        published_at=now - timedelta(hours=3),
        topic="Software",
        raw_metadata={"public_metrics": tech_metrics},
        source_type="x"
    )
    assert tech_res.relevance_score >= 10
    assert tech_res.conversation_score >= 5
    assert tech_res.audience_value_score >= 10
    assert tech_res.overall_score >= 70
    assert "Active X discussion" in tech_res.why_it_matters

    # Viral post with 100,000 likes but NO relevance to developer pillars
    viral_metrics = {"reply_count": 500, "like_count": 100000, "retweet_count": 25000}
    viral_res = score_opportunity(
        title="Check out this cute puppy playing in the park today!",
        content="He loves running around chasing tennis balls in the sun.",
        published_at=now - timedelta(hours=1),
        topic="General",
        raw_metadata={"public_metrics": viral_metrics},
        source_type="x"
    )
    # Relevance is low because it has no Content DNA overlap
    assert viral_res.relevance_score <= 6
    # Overall score must NOT reach high opportunity despite massive viral likes
    assert viral_res.overall_score < 70

    # Promotional / spam crypto post
    spam_metrics = {"reply_count": 20, "like_count": 500}
    spam_res = score_opportunity(
        title="Airdrop alert! 100x guaranteed profit presale",
        content="Free giveaway limited time offer! Revolutionary next-gen token.",
        published_at=now - timedelta(hours=1),
        topic="Web3",
        raw_metadata={"public_metrics": spam_metrics},
        source_type="x"
    )
    assert spam_res.spam_risk_score >= 7
    assert spam_res.overall_score < tech_res.overall_score

# 7. Telegram formatting & provenance tests
def test_telegram_x_opportunity_card_and_provenance(db):
    x_item = SourceItem(
        id=77,
        source_id="x_cybersecurity",
        source_type="x",
        external_id="18009999",
        author="@sec_guru (Security Guru)",
        title="Critical zero-day in Linux kernel networking stack",
        content="A deep dive into the memory corruption vulnerability in the socket buffer layer.",
        url="https://x.com/sec_guru/status/18009999",
        topic="Cybersecurity",
        opportunity_score=86,
        relevance_score=18,
        freshness_score=20,
        original_angle_score=16,
        audience_value_score=18,
        conversation_score=9,
        spam_risk_score=1,
        status="NEW",
        raw_metadata={"public_metrics": {"reply_count": 18, "retweet_count": 25, "like_count": 150}}
    )
    db.add(x_item)
    db.commit()
    db.refresh(x_item)

    # Card formatting
    card = format_opportunity_card(x_item)
    assert "POTENTIAL X CONVERSATION #77" in card
    assert "@sec_guru (Security Guru)" in card
    assert "18 replies | 25 reposts | 150 likes" in card
    assert "86/100" in card

    # Keyboard has OPEN POST url button
    kb = build_opportunity_keyboard(x_item)
    urls = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
    assert "https://x.com/sec_guru/status/18009999" in urls

    # Provenance tracking: DRAFT action
    idea = opportunity_service.draft_opportunity(db, x_item.id)
    assert idea is not None
    assert idea.source_item_id == x_item.id
    assert idea.source == "x"
    assert idea.source_url == "https://x.com/sec_guru/status/18009999"
    assert x_item.status == "DRAFTED"

# 8. Defensive fixes verification
def test_phase6_audit_defensive_fixes(db):
    # Fix 1: Verify type hints on score_opportunity resolve without NameError
    hints = typing.get_type_hints(score_opportunity)
    assert "raw_metadata" in hints
    assert hints["raw_metadata"] == typing.Optional[typing.Dict[str, typing.Any]]

    # Fix 2: Defensive public_metrics handling in format_opportunity_card
    # Case A: public_metrics is explicitly None
    opp_null_metrics = SourceItem(
        id=88,
        source_id="x_test",
        source_type="x",
        external_id="18008888",
        author="@null_author",
        title="Post with null public metrics",
        content="Testing defensive fallback when public_metrics is null.",
        url="https://x.com/i/status/18008888",
        raw_metadata={"public_metrics": None},
        status="NEW"
    )
    card_a = format_opportunity_card(opp_null_metrics)
    assert "POTENTIAL X CONVERSATION #88" in card_a
    assert "0 replies | 0 reposts | 0 likes" in card_a

    # Case B: raw_metadata is None
    opp_none_meta = SourceItem(
        id=89,
        source_id="x_test",
        source_type="x",
        external_id="18008889",
        author="@no_meta",
        title="Post with None raw_metadata",
        content="Testing defensive fallback when raw_metadata is None.",
        url="https://x.com/i/status/18008889",
        raw_metadata=None,
        status="NEW"
    )
    card_b = format_opportunity_card(opp_none_meta)
    assert "POTENTIAL X CONVERSATION #89" in card_b
    assert "0 replies | 0 reposts | 0 likes" in card_b

    # Case C: raw_metadata is empty dict
    opp_empty_meta = SourceItem(
        id=90,
        source_id="x_test",
        source_type="x",
        external_id="18008890",
        author="@empty_meta",
        title="Post with empty raw_metadata",
        content="Testing defensive fallback when raw_metadata is {}.",
        url="https://x.com/i/status/18008890",
        raw_metadata={},
        status="NEW"
    )
    card_c = format_opportunity_card(opp_empty_meta)
    assert "POTENTIAL X CONVERSATION #90" in card_c
    assert "0 replies | 0 reposts | 0 likes" in card_c

    # Optional Fix: Unresolved author fallback URL
    conf = XQueryConfig(id="test_unresolved", query="test")
    adapter = XSourceAdapter(conf, bearer_token="mock")
    payload_no_users = {
        "data": [{
            "id": "18007777",
            "text": "Tweet with unresolved author user object",
            "author_id": "99999"
        }],
        "includes": {}
    }
    items, _ = adapter.parse_response(payload_no_users)
    assert len(items) == 1
    assert items[0].url == "https://x.com/i/status/18007777"

