"""进程内 TTL 缓存。"""

import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    """简单的内存 TTL 缓存。

    适合当前单进程部署；键带过期时间，读取时惰性删除过期项。
    多实例部署时应替换为 Redis 等共享缓存。
    """

    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() < expires_at:
            return value
        self._data.pop(key, None)
        return None

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self._data[key] = (time.monotonic() + ttl_seconds, value)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
