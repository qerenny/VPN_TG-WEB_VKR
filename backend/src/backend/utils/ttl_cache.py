import time
from collections import OrderedDict
from typing import Any, Optional


class TTLCache:
    """
    A simple TTL (Time-To-Live) cache with LRU (Least Recently Used) eviction policy.
    Uses OrderedDict for O(1) access and update.
    """

    def __init__(self, ttl: int, max_size: int = 1000):
        self.ttl = ttl
        self.max_size = max_size
        self.cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self.cache:
            return None

        timestamp, value = self.cache[key]
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            return None

        # Move to end to mark as recently used
        self.cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)

        self.cache[key] = (time.time(), value)

        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def clear(self) -> None:
        self.cache.clear()
