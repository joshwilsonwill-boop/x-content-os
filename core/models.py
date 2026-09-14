from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.db import Base

class Idea(Base):
    __tablename__ = "ideas"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False)
    source_url = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=False)
    topic = Column(String(100), nullable=True)
    pillar = Column(String(100), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    source_item_id = Column(Integer, ForeignKey("source_items.id"), nullable=True)
    
    novelty_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    timeliness_score = Column(Float, nullable=True)
    personal_fit_score = Column(Float, nullable=True)
    usefulness_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    
    status = Column(String(50), nullable=False, default="RAW")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    drafts = relationship("Draft", back_populates="idea")

    def __repr__(self):
        return f"<Idea(id={self.id}, source='{self.source}', status='{self.status}')>"

class Draft(Base):
    __tablename__ = "drafts"
    
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(String(50), nullable=True)
    variant_number = Column(Integer, nullable=True)
    generation_method = Column(String(50), nullable=True)
    idea_id = Column(Integer, ForeignKey("ideas.id"), nullable=False)
    text = Column(Text, nullable=False)
    format = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False, default="DRAFT")
    character_count = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    idea = relationship("Idea", back_populates="drafts")
    
class AppState(Base):
    __tablename__ = "application_state"
    
    key = Column(String(100), primary_key=True, index=True)
    value = Column(String(255), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SourceItem(Base):
    __tablename__ = "source_items"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String(100), nullable=False, index=True) # e.g. "techcrunch_rss"
    source_type = Column(String(50), nullable=False) # e.g. "rss", "manual"
    external_id = Column(String(255), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)
    url = Column(String(500), nullable=True)
    author = Column(String(100), nullable=True)
    topic = Column(String(100), nullable=True)
    
    # Metadata and deduplication
    content_hash = Column(String(128), nullable=True, index=True)
    raw_metadata = Column(JSON, nullable=True)
    
    # Opportunity Scoring
    opportunity_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    freshness_score = Column(Float, nullable=True)
    original_angle_score = Column(Float, nullable=True)
    audience_value_score = Column(Float, nullable=True)
    conversation_score = Column(Float, nullable=True)
    spam_risk_score = Column(Float, nullable=True)
    
    status = Column(String(50), nullable=False, default="NEW", index=True) # NEW, REVIEWED, SAVED, DRAFTED, IGNORED, EXPIRED
    
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    discovered_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    ideas = relationship("Idea", backref="source_item")

