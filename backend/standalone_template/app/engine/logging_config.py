import json
import logging
import time


class JSONFormatter(logging.Formatter):
    def format(self, record):
        value = {"time": time.time(), "level": record.levelname, "event": record.getMessage(), "logger": record.name}
        for key in ("request_id", "method", "path", "status", "latency_ms", "job_id", "chunks", "error_type"):
            if hasattr(record, key):
                value[key] = getattr(record, key)
        return json.dumps(value)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # Access logs can expose widget query-string capabilities; use safe structured middleware.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Parser diagnostics may quote raw document bytes. Surface only our safe job errors.
    logging.getLogger("pypdf").setLevel(logging.CRITICAL + 1)
