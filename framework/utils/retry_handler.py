"""Fault-tolerant retry logic for flaky instrument / DUT operations.

Provides both a ``@retry`` decorator for simple cases and a
:class:`RetryHandler` class for programmatic retry control with
configurable exponential back-off.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Any, Callable, Optional, Sequence, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# -- decorator ----------------------------------------------------------------

def retry(
    max_attempts: int = 3,
    backoff_factor: float = 1.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator that retries a function on specified exceptions.

    Args:
        max_attempts: Maximum total invocation attempts.
        backoff_factor: Multiplier for exponential back-off (seconds).
        exceptions: Tuple of exception types that trigger a retry.

    Returns:
        Decorated function with retry behaviour.

    Example::

        @retry(max_attempts=5, backoff_factor=0.5, exceptions=(IOError,))
        def read_sensor():
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            handler = RetryHandler()
            return handler.execute_with_retry(
                func,
                args=args,
                kwargs=kwargs,
                max_attempts=max_attempts,
                backoff=backoff_factor,
                retryable_exceptions=exceptions,
            )
        return wrapper  # type: ignore[return-value]
    return decorator


# -- class-based handler ------------------------------------------------------

class RetryHandler:
    """Programmatic retry executor with exponential back-off.

    Example::

        handler = RetryHandler()
        result = handler.execute_with_retry(
            my_func, args=(42,), max_attempts=3, backoff=0.5,
        )
    """

    DEFAULT_MAX_DELAY: float = 30.0

    def execute_with_retry(
        self,
        func: Callable[..., Any],
        args: Sequence[Any] = (),
        kwargs: Optional[dict[str, Any]] = None,
        max_attempts: int = 3,
        backoff: float = 1.0,
        retryable_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    ) -> Any:
        """Execute *func* with automatic retries on failure.

        Args:
            func: Callable to execute.
            args: Positional arguments for *func*.
            kwargs: Keyword arguments for *func*.
            max_attempts: Maximum total attempts (>= 1).
            backoff: Base delay multiplier for exponential back-off.
            retryable_exceptions: Exception types that trigger a retry.

        Returns:
            Return value of *func* on success.

        Raises:
            The last exception if all attempts are exhausted.
        """
        if kwargs is None:
            kwargs = {}
        last_exc: Optional[BaseException] = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = func(*args, **kwargs)
                if attempt > 1:
                    logger.info("Succeeded on attempt %d/%d", attempt, max_attempts)
                return result
            except retryable_exceptions as exc:
                last_exc = exc
                if not self._should_retry(exc, attempt, max_attempts):
                    logger.error("Not retrying after attempt %d: %s", attempt, exc)
                    raise
                delay = self._exponential_backoff(attempt, backoff, self.DEFAULT_MAX_DELAY)
                logger.warning(
                    "Attempt %d/%d failed (%s: %s). Retrying in %.2f s ...",
                    attempt, max_attempts, type(exc).__name__, exc, delay,
                )
                time.sleep(delay)

        # All attempts exhausted
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("RetryHandler: all attempts exhausted with no exception captured")

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _exponential_backoff(attempt: int, base_delay: float, max_delay: float) -> float:
        """Compute the back-off delay with jitter.

        Args:
            attempt: Current attempt number (1-based).
            base_delay: Base delay in seconds.
            max_delay: Maximum allowable delay in seconds.

        Returns:
            Delay in seconds.
        """
        delay = base_delay * (2 ** (attempt - 1))
        delay = min(delay, max_delay)
        # Add up to 25 % jitter to avoid thundering herd
        jitter = delay * 0.25 * random.random()
        return delay + jitter

    @staticmethod
    def _should_retry(exception: BaseException, attempt: int, max_attempts: int = 3) -> bool:
        """Decide whether a retry is appropriate.

        Args:
            exception: The caught exception.
            attempt: Current attempt number.
            max_attempts: Maximum total attempts.

        Returns:
            ``True`` if the operation should be retried.
        """
        if attempt >= max_attempts:
            return False
        # Never retry keyboard interrupts or system exits
        if isinstance(exception, (KeyboardInterrupt, SystemExit)):
            return False
        return True
