import os
import yaml
from dataclasses import dataclass, field
from typing import List, Optional
from core.logging import get_logger

logger = get_logger(__name__)

@dataclass
class XQueryConfig:
    id: str
    query: str
    enabled: bool = True
    description: str = ""
    max_results: int = 10
    topic: str = "Technology"

def load_x_sources_config(filepath: str = "config/x_sources.yaml") -> List[XQueryConfig]:
    """Loads and validates X search queries from YAML configuration."""
    if not os.path.exists(filepath):
        logger.warning(f"X sources config file not found: {filepath}")
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            return []

        raw_queries = data.get("queries", [])
        if not isinstance(raw_queries, list):
            return []

        configs: List[XQueryConfig] = []
        for q in raw_queries:
            if not isinstance(q, dict):
                continue
            q_id = q.get("id")
            q_query = q.get("query")

            if not q_id or not q_query:
                continue

            # Bound max_results between 10 and 100 per official X API limits
            max_results = int(q.get("max_results", 10))
            max_results = max(10, min(100, max_results))

            configs.append(XQueryConfig(
                id=str(q_id),
                query=str(q_query),
                enabled=bool(q.get("enabled", True)),
                description=str(q.get("description", "")),
                max_results=max_results,
                topic=str(q.get("topic", "Technology"))
            ))
        return configs
    except Exception as e:
        logger.error(f"Error reading X sources config from {filepath}: {e}")
        return []
