"""同步调用的重试与超时工具。"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from time import sleep
from typing import Callable, TypeVar

T = TypeVar("T")


def run_with_retry(
    operation: Callable[[], T],
    *,
    operation_name: str,
    timeout_seconds: float = 30,
    max_attempts: int = 3,
    backoff_seconds: tuple[float, ...] = (1, 2),
) -> T:
    """在单次超时限制内执行同步操作，失败后按指数退避重试。"""
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(operation)
            try:
                return future.result(timeout=timeout_seconds)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except (FutureTimeoutError, TimeoutError) as exc:
            last_error = TimeoutError(f"{operation_name} 超时（{timeout_seconds:g} 秒）")
            future.cancel()
        except Exception as exc:
            last_error = exc

        if attempt < max_attempts - 1:
            sleep(backoff_seconds[min(attempt, len(backoff_seconds) - 1)])

    raise last_error or RuntimeError(f"{operation_name} 调用失败")
