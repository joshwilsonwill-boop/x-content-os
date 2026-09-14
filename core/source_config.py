import yaml
import os
from dataclasses import dataclass, field
from typing import List, Optional
from core.logging import get_logger

logger = get_logger(__name__)

@dataclass
class SourceConfig:
    id: str
    type: str
    name: str
    url: str
    enabled: bool = True
    topics: List[str] = field(default_factory=list)

def load_sources_config(filepath: str = "config/sources.yaml") -> List[SourceConfig]:
    """Loads and validates sources from YAML configuration."""
    if not os.path.exists(filepath):
        logger.warning(f"Sources config file not found: {filepath}")
        return []
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            
        if not data or not isinstance(data, dict):
            return []
            
        raw_sources = data.get("sources", [])
        if not isinstance(raw_sources, list):
            return []
            
        configs = []
        for s in raw_sources:
            if not isinstance(s, dict):
                continue
            s_id = s.get("id")
            s_type = s.get("type")
            s_name = s.get("name", s_id)
            s_url = s.get("url")
            
            if not s_id or not s_type or not s_url:
                continue
                
            configs.append(SourceConfig(
                id=str(s_id),
                type=str(s_type),
                name=str(s_name),
                url=str(s_url),
                enabled=bool(s.get("enabled", True)),
                topics=list(s.get("topics", []))
            ))
        return configs
    except Exception as e:
        logger.error(f"Error reading sources config from {filepath}: {e}")
        return []
