import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.models import Idea
from core.db import Base

@pytest.fixture(scope="module")
def engine():
    # Use in-memory SQLite for testing
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

def test_create_idea(db_session):
    idea = Idea(
        source="manual",
        raw_text="Overengineering is the death of indie projects.",
        topic="Engineering",
        pillar="Building Business",
        metadata_json={"author": "me"}
    )
    db_session.add(idea)
    db_session.commit()
    db_session.refresh(idea)

    assert idea.id is not None
    assert idea.source == "manual"
    assert idea.raw_text == "Overengineering is the death of indie projects."
    
def test_idea_query(db_session):
    idea = db_session.query(Idea).filter_by(source="manual").first()
    assert idea is not None
    assert idea.pillar == "Building Business"
