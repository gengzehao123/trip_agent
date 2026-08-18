"""异步调用的重试与超时工具。"""

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def arun_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str,
    timeout_seconds: float = 30,
    max_attempts: int = 3,
    backoff_seconds: tuple[float, ...] = (1, 2),
) -> T:
    """在单次超时限制内执行异步操作，失败后按退避重试。"""
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            last_error = TimeoutError(f"{operation_name} 超时（{timeout_seconds:g} 秒）")
        except Exception as exc:
            last_error = exc

        if attempt < max_attempts - 1:
            await asyncio.sleep(backoff_seconds[min(attempt, len(backoff_seconds) - 1)])

    raise last_error or RuntimeError(f"{operation_name} 调用失败")
