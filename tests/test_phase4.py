import pytest
from core.preview import generate_preview_html, load_preview_settings
from core.models import Idea, Draft
from core.db import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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

def test_preview_generation(db_session):
    # Setup test idea and draft
    idea = Idea(source="test", raw_text="A simple idea", pillar="Business")
    db_session.add(idea)
    db_session.commit()
    db_session.refresh(idea)
    
    # 1. Valid Draft Preview with Unicode and URLs
    valid_text = "Here is a good post 👨‍👩‍👧‍👦 with a link https://example.com"
    draft = Draft(idea_id=idea.id, text=valid_text, format="observation", status="UNDER_REVIEW", character_count=48)
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)
    
    html_preview = generate_preview_html(db_session, draft)
    
    assert "<b>X PREVIEW</b>" in html_preview
    assert valid_text in html_preview # Exact preservation of original draft text
    assert "Pillar: Business" in html_preview
    assert "Structure: observation" in html_preview
    assert "Status: <b>PASS</b>" in html_preview
    assert "weighted characters" in html_preview

def test_preview_html_escaping(db_session):
    idea = Idea(source="test", raw_text="A simple idea", pillar="Business")
    db_session.add(idea)
    db_session.commit()
    
    # HTML injection text
    danger_text = "Look at this <script>alert(1)</script> and <b>bold</b> text."
    draft = Draft(idea_id=idea.id, text=danger_text, format="observation", status="UNDER_REVIEW")
    db_session.add(draft)
    db_session.commit()
    
    html_preview = generate_preview_html(db_session, draft)
    
    assert "<script>" not in html_preview
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_preview
    assert "&lt;b&gt;bold&lt;/b&gt;" in html_preview

def test_preview_failed_status(db_session):
    idea = Idea(source="test", raw_text="A simple idea", pillar="Business")
    db_session.add(idea)
    db_session.commit()
    
    # Over-limit text
    long_text = "A" * 285
    draft = Draft(idea_id=idea.id, text=long_text, format="observation", status="UNDER_REVIEW")
    db_session.add(draft)
    db_session.commit()
    
    html_preview = generate_preview_html(db_session, draft)
    assert "Status: <b>FAILED</b>" in html_preview
    assert "Exceeds absolute maximum" in html_preview
    
def test_preview_warning_status(db_session):
    idea = Idea(source="test", raw_text="A simple idea", pillar="Business")
    db_session.add(idea)
    db_session.commit()
    
    # Trigger warning by pattern fatigue, not exact duplicate
    # We need 3 approved drafts with the same opening
    for i in range(3):
        d = Draft(idea_id=idea.id, text=f"Most founders don't understand concept {i}. Here is a completely unique explanation for it.", status="APPROVED")
        db_session.add(d)
    db_session.commit()
    
    # Draft with same opening but different body so similarity is low
    draft = Draft(idea_id=idea.id, text="Most founders don't care about this totally different and entirely new unmentioned concept at all.", format="observation", status="UNDER_REVIEW")
    db_session.add(draft)
    db_session.commit()
    
    html_preview = generate_preview_html(db_session, draft)
    assert "Status: <b>WARNING</b>" in html_preview
    assert "PATTERN FATIGUE" in html_preview
