import pytest
from core.x_character_count import validate
from core.repetition import calculate_similarity, detect_opening_pattern
from core.content_dna import load_content_dna
from core.draft_generator import TemplateDraftGenerator
from core.models import Idea, Draft
from core.db import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.services.draft_generation_service import generate_drafts
from core.quality_gate import run_quality_gate

def test_character_count():
    assert validate("Hello world", 265).weighted_count == 11
    assert validate("こんにちは", 265).weighted_count == 10 # 5 CJK chars * 2 = 10
    
    # URL testing
    assert validate("Hello https://example.com/very/long/url", 265).weighted_count == 29 # 6 + 23
    assert validate("Check this www.example.com", 265).weighted_count == 34 # "Check this " (11) + URL (23)
    assert validate("http://a.co and https://b.com", 265).weighted_count == 51 # 2 URLs (46) + " and " (5)
    
    # Emojis and Complex Unicode
    assert validate("🚀", 265).weighted_count == 2
    assert validate("👍🏽", 265).weighted_count == 2 # Emoji with skin tone (grapheme cluster)
    assert validate("👨‍👩‍👧‍👦", 265).weighted_count == 2 # ZWJ family sequence
    assert validate("é", 265).weighted_count == 2 # Combining mark e + acute (our simple heuristic counts multi-codepoint as 2 for safety)
    
    # Edge Cases
    assert validate("\n \t", 265).weighted_count == 3
    assert validate("A" * 280, 280).weighted_count == 280
    assert validate("A" * 280, 280).valid
    
    res = validate("A" * 281, 280)
    assert not res.valid
    assert "Exceeds absolute maximum" in res.reason
    
    res = validate("A" * 270, 265)
    assert not res.valid
    assert "Exceeds internal target" in res.reason

def test_content_dna():
    dna = load_content_dna()
    assert isinstance(dna.banned_phrases, list)
    assert "game changer" in [p.lower() for p in dna.banned_phrases]
    
def test_repetition():
    text1 = "Most founders don't need more tools. They need fewer open loops."
    text2 = "Most startup founders don't need another piece of software. They need to eliminate unnecessary open loops."
    text3 = "Here is a completely unrelated post about cybersecurity."
    
    sim1 = calculate_similarity(text1, text2)
    sim2 = calculate_similarity(text1, text3)
    
    assert sim1 > sim2 # text1 and text2 are more similar
    assert detect_opening_pattern(text1) == "most founders dont"
    assert detect_opening_pattern("Most people think") == "most people think"

@pytest.fixture(scope="module")
def engine():
    return create_engine("sqlite:///:memory:")

@pytest.fixture(scope="module")
def tables(engine):
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(engine, tables):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()

def test_quality_gate(db_session):
    # Empty fails
    res = run_quality_gate(db_session, "")
    assert not res.passed
    assert "EMPTY DRAFT" in res.warnings
    
    # Banned phrase fails
    res = run_quality_gate(db_session, "This is a Game Changer for the industry.")
    assert not res.passed
    assert any("BANNED PHRASE" in w for w in res.warnings)
    
    # Valid passes
    res = run_quality_gate(db_session, "A normal observation about software engineering that doesn't use banned words.")
    assert res.passed
    assert res.overall_score > 0

def test_generation_service(db_session):
    idea = Idea(source="test", raw_text="Test idea")
    db_session.add(idea)
    db_session.commit()
    db_session.refresh(idea)
    
    generator = TemplateDraftGenerator()
    drafts = generate_drafts(db_session, idea.id, "observation", generator, variant_count=3)
    
    assert len(drafts) == 3
    assert drafts[0].status == "UNDER_REVIEW" # because "Test idea" is valid text
    assert drafts[0].format == "observation"
    assert drafts[0].character_count > 0
    assert drafts[0].variant_number == 1
    assert drafts[1].variant_number == 2
    
    # test failures:
    idea_bad = Idea(source="test", raw_text="game changer idea")
    db_session.add(idea_bad)
    db_session.commit()
    
    drafts_bad = generate_drafts(db_session, idea_bad.id, "observation", generator, variant_count=1)
    assert drafts_bad[0].status == "FAILED" # because it contains banned phrase
