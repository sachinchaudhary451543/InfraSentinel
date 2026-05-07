"""
core/retry.py
=============
Retry layer for SharePoint upload operations.

Public API:
    sp_upload_with_retry(fn, *args, creds=None, max_attempts=3, **kwargs)
        Call fn(*args, **kwargs). On failure:
          1. Classify the error (transient vs schema)
          2. If schema error: invalidate provisioning cache, re-provision, retry
          3. If transient (throttle, timeout): wait with exponential backoff, retry
          4. After max_attempts: re-raise

    RetryableError          — base class for errors worth retrying
    SchemaError             — missing list or column (triggers re-provision)
    ThrottleError           — HTTP 429 / service busy

Design:
    - Retries are bounded (default max 3 attempts total)
    - Exponential backoff: 2s, 4s, 8s (jitter ±20%)
    - Schema errors trigger one provisioning pass then one more upload attempt
    - Never retries authentication errors (401/403) — user must fix creds
    - Never retries 400 Bad Request — data problem, not infra
    - All retry activity is logged at WARNING level
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable

log = logging.getLogger("SPRetry")

# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

class RetryableError(Exception):
    """Base for errors that may succeed on retry."""

class SchemaError(RetryableError):
    """SP list or column missing — trigger re-provision before retry."""

class ThrottleError(RetryableError):
    """HTTP 429 or SP service busy — wait then retry."""

# Error substrings that classify a SharePoint exception
_SCHEMA_SIGNALS = (
    "does not exist",
    "list does not exist",
    "cannot be found",
    "field or property",
    "column",
    "no field",
    "invalidfieldorproperty",
)

_THROTTLE_SIGNALS = (
    "429",
    "throttl",
    "too many requests",
    "service unavailable",
    "503",
    "temporarily unavailable",
)

_AUTH_SIGNALS = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "access denied",
    "invalid client",
    "aadsts",
)

_BAD_REQUEST_SIGNALS = (
    "400",
    "bad request",
)


def _classify(exc: Exception) -> str:
    """
    Return one of: 'schema', 'throttle', 'auth', 'bad_request', 'transient'.
    'transient' = retry with backoff but no special action.
    'auth' / 'bad_request' = do not retry.
    """
    msg = str(exc).lower()
    if any(s in msg for s in _AUTH_SIGNALS):
        return "auth"
    if any(s in msg for s in _BAD_REQUEST_SIGNALS):
        return "bad_request"
    if any(s in msg for s in _THROTTLE_SIGNALS):
        return "throttle"
    if any(s in msg for s in _SCHEMA_SIGNALS):
        return "schema"
    return "transient"


# ---------------------------------------------------------------------------
# Backoff helper
# ---------------------------------------------------------------------------

def _backoff(attempt: int, base: float = 2.0, jitter: float = 0.2) -> float:
    """
    Exponential backoff with ±jitter.
    attempt=1 → ~2s, attempt=2 → ~4s, attempt=3 → ~8s.
    """
    delay = base ** attempt
    delay *= 1 + random.uniform(-jitter, jitter)
    return delay


# ---------------------------------------------------------------------------
# Core retry wrapper
# ---------------------------------------------------------------------------

def sp_upload_with_retry(
    fn: Callable,
    *args: Any,
    creds: dict | None = None,
    config: dict | None = None,
    max_attempts: int = 3,
    **kwargs: Any,
) -> Any:
    """
    Call fn(*args, **kwargs) with retry logic.

    On each failure:
        - Schema error  → re-provision (once), then retry immediately
        - Throttle      → wait with exponential backoff, then retry
        - Transient     → wait with exponential backoff, then retry
        - Auth / 400    → raise immediately (no retry)

    Args:
        fn:           The callable to invoke (e.g. push_metrics_to_sharepoint).
        *args:        Positional arguments passed to fn.
        creds:        SharePoint credentials dict (passed to provisioning).
        config:       Full config dict (used for re-provisioning). If None,
                      schema errors fall back to transient behaviour.
        max_attempts: Total attempts allowed (default 3).
        **kwargs:     Keyword arguments passed to fn.

    Returns:
        Whatever fn returns on success.

    Raises:
        The last exception if all attempts are exhausted.
    """
    last_exc: Exception | None = None
    reproved = False   # only re-provision once per call to avoid SP hammering

    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)

        except Exception as exc:
            last_exc = exc
            kind = _classify(exc)

            log.warning(
                "SP upload attempt %d/%d failed [%s]: %s",
                attempt, max_attempts, kind, str(exc)[:200],
            )

            # --- Non-retryable ---
            if kind == "auth":
                log.error(
                    "Authentication error — check client_id / client_secret. "
                    "Re-run 'python installer/wizard.py' to update credentials."
                )
                raise

            if kind == "bad_request":
                log.error("Bad request error — payload problem, not retrying: %s", exc)
                raise

            # --- Schema error: re-provision then continue ---
            if kind == "schema" and not reproved and config is not None:
                log.warning("Schema mismatch detected — running re-provisioning.")
                try:
                    from core.provisioning import run_provisioning, invalidate_cache
                    invalidate_cache()
                    result = run_provisioning(config)
                    reproved = True
                    if not result.provisioned:
                        log.error(
                            "Re-provisioning could not fix the schema. "
                            "Errors: %s", result.errors
                        )
                except Exception as prov_exc:
                    log.error("Re-provisioning failed: %s", prov_exc)
                # Don't sleep after schema fix — retry immediately
                continue

            # --- Throttle / transient: wait then retry ---
            if attempt < max_attempts:
                wait = _backoff(attempt)
                log.warning("Waiting %.1fs before retry.", wait)
                time.sleep(wait)

    log.error("All %d upload attempts failed. Last error: %s", max_attempts, last_exc)
    raise last_exc   # type: ignore[misc]


# ---------------------------------------------------------------------------
# Convenience decorator
# ---------------------------------------------------------------------------

def retryable_upload(max_attempts: int = 3, config_getter: Callable | None = None):
    """
    Decorator factory. Wraps a function with sp_upload_with_retry.

    Usage:
        @retryable_upload(max_attempts=3)
        def push_metrics_to_sharepoint(creds=None): ...

    The decorated function receives the same arguments as the original.
    config_getter, if provided, is called with no arguments to obtain the
    current config dict for re-provisioning.
    """
    def decorator(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            cfg = config_getter() if config_getter else None
            return sp_upload_with_retry(
                fn, *args,
                config=cfg,
                max_attempts=max_attempts,
                **kwargs,
            )
        wrapper.__name__ = fn.__name__
        wrapper.__doc__  = fn.__doc__
        return wrapper
    return decorator