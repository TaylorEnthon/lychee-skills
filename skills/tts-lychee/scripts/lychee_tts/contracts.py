from __future__ import annotations

import uuid
from typing import Any, Dict, Optional


SCHEMA_VERSION = "1.0"


def new_run_id() -> str:
    return uuid.uuid4().hex


def event_record(
    operation: str,
    run_id: str,
    event: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "type": "event",
        "operation": operation,
        "run_id": run_id,
        "event": event,
        **(details or {}),
    }


def result_record(
    operation: str,
    run_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "type": "result",
        "operation": operation,
        "run_id": run_id,
        **payload,
    }


def error_record(
    operation: str,
    run_id: str,
    error: BaseException,
) -> Dict[str, Any]:
    if isinstance(error, KeyboardInterrupt):
        defaults = ("cancelled", "streaming", False, "操作已取消")
    elif isinstance(error, FileExistsError):
        defaults = ("conflict", "validation", False, str(error))
    elif isinstance(error, ValueError):
        defaults = ("invalid_arguments", "validation", False, str(error))
    else:
        defaults = ("internal_error", "runtime", False, str(error))

    error_code = str(getattr(error, "error_code", None) or defaults[0])
    stage = str(getattr(error, "stage", None) or defaults[1])
    retryable = bool(getattr(error, "retryable", defaults[2]))
    message = str(error) or defaults[3] or error.__class__.__name__
    result: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "type": "error",
        "operation": operation,
        "run_id": run_id,
        "success": False,
        "error": message,
        "error_code": error_code,
        "stage": stage,
        "retryable": retryable,
    }
    partial_output = getattr(error, "partial_output", None)
    if partial_output:
        result["partial_output"] = str(partial_output)
    return result
