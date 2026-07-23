"""Structured operational logging with deterministic secret redaction."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

SECRET_NAMES = ("api_key", "token", "secret", "password", "authorization", "credential")
SECRET_VALUE_RE = re.compile(r"(?i)(api[_-]?key|token|authorization|password|secret|credential)(\s*[=:]\s*)([^\s,;]+)")


def _redact_string(value: str) -> str:
    return SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: ("[REDACTED]" if any(secret in str(key).lower() for secret in SECRET_NAMES) else _redact(value)) for key, value in sorted(obj.items())}
    if isinstance(obj, list):
        return [_redact(value) for value in obj]
    if isinstance(obj, tuple):
        return tuple(_redact(value) for value in obj)
    if isinstance(obj, set):
        return sorted(_redact(value) for value in obj)
    if isinstance(obj, str):
        return _redact_string(obj)
    return obj


def log_record(
    *,
    execution_id: str,
    stage: str,
    severity: str,
    event_code: str,
    context: dict[str, Any] | None = None,
    exception: BaseException | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    record = {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "execution_id": execution_id,
        "stage": stage,
        "severity": severity,
        "event_code": event_code,
        "context": _redact(context or {}),
    }
    if exception:
        record["exception"] = {"type": type(exception).__name__, "message": _redact_string(str(exception))}
    return record
