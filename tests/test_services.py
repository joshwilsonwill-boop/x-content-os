import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.models import Idea, Draft, AppState
from core.db import Base
from core.services import idea_service, draft_service, system_service

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

def test_idea_service(db_session):
    idea = idea_service.create_idea(db_session, "Test raw idea")
    assert idea.id is not None
    assert idea.raw_text == "Test raw idea"
    assert idea.status == "RAW"
    
    ideas = idea_service.get_all_ideas(db_session)
    assert len(ideas) == 1

def test_draft_service(db_session):
    idea = idea_service.create_idea(db_session, "Draft idea test")
    draft = draft_service.create_draft(db_session, idea.id, "Draft text")
    
    assert draft.status == "UNDER_REVIEW"
    
    drafts = draft_service.get_drafts_awaiting_review(db_session)
    assert len(drafts) == 1
    assert drafts[0].id == draft.id
    
    draft_service.update_draft_status(db_session, draft.id, "APPROVED")
    
    drafts = draft_service.get_drafts_awaiting_review(db_session)
    assert len(drafts) == 0
    
    draft_service.update_draft_text(db_session, draft.id, "New text")
    # should be returned to UNDER_REVIEW
    drafts = draft_service.get_drafts_awaiting_review(db_session)
    assert len(drafts) == 1
    assert drafts[0].text == "New text"

def test_system_service(db_session):
    assert system_service.get_system_mode(db_session) == "RUNNING"
    system_service.set_system_mode(db_session, "PAUSED")
    assert system_service.get_system_mode(db_session) == "PAUSED"
    
    stats = system_service.get_stats(db_session)
    assert "ideas" in stats
    assert "drafts_review" in stats
