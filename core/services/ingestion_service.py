from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from core.models import SourceItem
from core.source_config import load_sources_config, SourceConfig
from core.sources import RSSSourceAdapter, RawSourceItem
from core.normalization import normalize_source_item
from core.opportunity_scoring import score_opportunity
from core.repetition import calculate_similarity
from core.logging import get_logger, log_action

logger = get_logger(__name__)

@dataclass
class IngestionResult:
    sources_checked: int = 0
    items_fetched: int = 0
    new_items: int = 0
    duplicates: int = 0
    high_opportunity_items: int = 0
    errors: int = 0
    error_details: List[str] = field(default_factory=list)

def is_duplicate(db: Session, source_id: str, external_id: str, canonical_url: str, content_hash: str, title: str) -> bool:
    """
    Checks if a source item is a duplicate based on:
    1. external_id for the same source_id
    2. canonical_url
    3. content_hash
    4. Conservative lexical similarity on titles within the last 14 days (> 0.85 Jaccard)
    """
    # 1. Exact match on external_id, url, or content_hash
    query = db.query(SourceItem).filter(
        or_(
            (SourceItem.source_id == source_id) & (SourceItem.external_id == external_id),
            (SourceItem.url == canonical_url) & (canonical_url != ""),
            (SourceItem.content_hash == content_hash)
        )
    )
    if query.first() is not None:
        return True

    # 2. Conservative title similarity with recent items
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    recent_items = db.query(SourceItem.title).filter(SourceItem.discovered_at >= cutoff).all()
    for (rec_title,) in recent_items:
        if rec_title:
            sim = calculate_similarity(title, rec_title)
            if sim >= 0.85:
                return True

    return False

def ingest_raw_items(db: Session, raw_items: List[RawSourceItem]) -> IngestionResult:
    """Processes and normalizes raw items, deduplicates, scores, and stores them in DB."""
    result = IngestionResult()
    result.items_fetched = len(raw_items)

    for raw in raw_items:
        norm_title, norm_content, canon_url, content_hash = normalize_source_item(raw)
        
        # Deduplication check
        if is_duplicate(db, raw.source_id, raw.external_id, canon_url, content_hash, norm_title):
            result.duplicates += 1
            continue

        # Score opportunity
        score_res = score_opportunity(
            title=norm_title,
            content=norm_content,
            published_at=raw.published_at,
            topic=raw.topic
        )

        item = SourceItem(
            source_id=raw.source_id,
            source_type=raw.source_type,
            external_id=raw.external_id,
            title=norm_title,
            content=norm_content,
            url=canon_url,
            author=raw.author,
            topic=raw.topic or score_res.matched_pillar,
            content_hash=content_hash,
            raw_metadata=raw.raw_metadata,
            opportunity_score=score_res.overall_score,
            relevance_score=score_res.relevance_score,
            freshness_score=score_res.freshness_score,
            original_angle_score=score_res.original_angle_score,
            audience_value_score=score_res.audience_value_score,
            conversation_score=score_res.conversation_score,
            spam_risk_score=score_res.spam_risk_score,
            status="NEW",
            published_at=raw.published_at
        )
        db.add(item)
        result.new_items += 1
        if score_res.overall_score >= 70:
            result.high_opportunity_items += 1

    db.commit()
    return result

def run_ingestion(db: Session, config_path: str = "config/sources.yaml") -> IngestionResult:
    """Main ingestion coordinator. Loads sources, executes adapters, and logs results."""
    configs = load_sources_config(config_path)
    total_result = IngestionResult()

    for conf in configs:
        if not conf.enabled:
            continue
            
        total_result.sources_checked += 1
        try:
            if conf.type.lower() == "rss":
                adapter = RSSSourceAdapter(conf)
                raw_items = adapter.fetch()
                res = ingest_raw_items(db, raw_items)
                total_result.items_fetched += res.items_fetched
                total_result.new_items += res.new_items
                total_result.duplicates += res.duplicates
                total_result.high_opportunity_items += res.high_opportunity_items
            else:
                logger.warning(f"Unsupported source type '{conf.type}' for source '{conf.id}'")
        except Exception as e:
            total_result.errors += 1
            err_msg = f"Error ingesting source '{conf.id}': {e}"
            total_result.error_details.append(err_msg)
            logger.error(err_msg)

    log_action(
        logger, 20, "ingestion", "run", "success",
        msg=f"Checked {total_result.sources_checked} sources, {total_result.new_items} new items, {total_result.duplicates} duplicates, {total_result.errors} errors"
    )
    return total_result
