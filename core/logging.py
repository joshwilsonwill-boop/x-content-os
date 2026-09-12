import logging
import json
from datetime import datetime, timezone

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", "unknown"),
            "action": getattr(record, "action", "unknown"),
            "status": getattr(record, "status", "unknown"),
            "object_id": getattr(record, "object_id", None),
            "message": record.getMessage()
        }
        # Remove empty fields
        log_data = {k: v for k, v in log_data.items() if v is not None}
        return json.dumps(log_data)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = StructuredFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

# Convenience function for structured logging
def log_action(logger: logging.Logger, level: int, component: str, action: str, status: str, object_id: str = None, msg: str = ""):
    extra = {
        "component": component,
        "action": action,
        "status": status,
    }
    if object_id:
        extra["object_id"] = object_id
    logger.log(level, msg, extra=extra)
