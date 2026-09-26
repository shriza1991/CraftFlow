"""Structured logging foundation with request ID correlation and PII protection."""

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Context variable to track correlation request_id across async call chains
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="system")

SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "access_token",
    "refresh_token",
    "credit_card",
}


def mask_sensitive_data(data: Any) -> Any:
    """Recursively mask sensitive values in dictionaries and lists."""
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            if any(sensitive in k.lower() for sensitive in SENSITIVE_KEYS):
                masked[k] = "******"
            else:
                masked[k] = mask_sensitive_data(v)
        return masked
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data


class StructuredLogFormatter(logging.Formatter):
    """Custom formatter producing JSON-ready structured logs with correlation metadata."""

    def __init__(self, service_name: str = "ai-business-automation"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", None) or request_id_ctx.get()
        event_name = getattr(record, "event", record.funcName or "app_event")

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "request_id": req_id,
            "event": event_name,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Include structured extra payload if provided
        extra = getattr(record, "extra_payload", None)
        if extra and isinstance(extra, dict):
            payload["data"] = mask_sensitive_data(extra)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload)


def setup_logging(log_level: str = "INFO", service_name: str = "ai-business-automation") -> None:
    """Initialize structured logging across the root logger."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(StructuredLogFormatter(service_name=service_name))
    root_logger.addHandler(console_handler)

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Helper to get a logger with structured logging capabilities."""
    return logging.getLogger(name)
