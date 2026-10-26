"""Bounded retries for transient LLM-provider failures.

Chat latency matters, so the total wait is capped. Quota exhaustion is retried
once at most: a daily quota will not recover within seconds, and retrying it
only delays the fallback answer.
"""
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS = {500, 502, 503, 504}

def _status_code(exc):
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    if code is None:
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None

def _retry_after_seconds(exc):
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    value = headers.get("retry-after") if hasattr(headers, "get") else None
    if value:
        try:
            return float(value)
        except ValueError:
            pass
    match = re.search(r"(?:try again in|retry after)\s+([\d.]+)\s*s", str(exc), re.I)
    return float(match.group(1)) if match else None

def is_transient(exc):
    """True for timeouts, connection drops and 5xx/429 responses worth one more try."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)):
        return True
    code = _status_code(exc)
    if code in _TRANSIENT_STATUS:
        return True
    if code == 429:
        return True
    return False

def call_with_retry(operation, *, label="LLM call", attempts=3, max_total_wait=6.0, retry_rate_limit=True):
    """Run operation(); retry transient failures with capped, honoured backoff.

    A 429 (quota/rate limit) gets one retry at most, and none when retry_rate_limit
    is False: latency-sensitive callers should fail over to another provider instead.
    """
    waited = 0.0
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 - re-raised below when not retryable
            last_exc = exc
            if not is_transient(exc) or attempt == attempts:
                raise
            if _status_code(exc) == 429 and (not retry_rate_limit or attempt >= 2):
                raise
            delay = _retry_after_seconds(exc)
            if delay is None:
                delay = min(2.0 ** (attempt - 1), 4.0)
            delay = min(delay, max_total_wait - waited)
            if delay <= 0:
                raise
            logger.warning("%s transient failure (%s); retrying in %.1fs", label, type(exc).__name__, delay)
            time.sleep(delay)
            waited += delay
    raise last_exc
