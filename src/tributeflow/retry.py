"""Small retry helper for flaky network calls (Sheets, GitHub, SMTP)."""

from __future__ import annotations

import logging
import time
from functools import wraps

log = logging.getLogger(__name__)


def with_retries(attempts: int = 3, base_delay: float = 1.0, retry_on: tuple = (Exception,)):
    """Retry a function with exponential backoff. Re-raises the last error."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except retry_on as exc:  # noqa: PERF203
                    last_exc = exc
                    if attempt < attempts - 1:
                        delay = base_delay * (2**attempt)
                        log.warning(
                            "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                            fn.__name__, attempt + 1, attempts, exc, delay,
                        )
                        time.sleep(delay)
            raise last_exc

        return wrapper

    return decorator
