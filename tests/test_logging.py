import json
import logging
from core.logging import get_logger, log_action
import io

def test_structured_logging():
    # Create a string buffer to capture log output
    log_capture_string = io.StringIO()
    handler = logging.StreamHandler(log_capture_string)
    
    # Needs to match our formatter
    from core.logging import StructuredFormatter
    handler.setFormatter(StructuredFormatter())
    
    test_logger = logging.getLogger("test_logger")
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(handler)
    
    log_action(test_logger, logging.INFO, "test_component", "test_action", "success", "obj_123", "Test message")
    
    log_contents = log_capture_string.getvalue()
    log_dict = json.loads(log_contents)
    
    assert log_dict["component"] == "test_component"
    assert log_dict["action"] == "test_action"
    assert log_dict["status"] == "success"
    assert log_dict["object_id"] == "obj_123"
    assert log_dict["message"] == "Test message"
    assert "timestamp" in log_dict
    assert log_dict["level"] == "INFO"
