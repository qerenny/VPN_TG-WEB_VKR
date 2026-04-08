import time
import pytest
from backend.utils.ttl_cache import TTLCache


def test_ttl_cache_set_get():
    cache = TTLCache(ttl=60)
    cache.set("key", "value")
    assert cache.get("key") == "value"


def test_ttl_cache_expiration():
    cache = TTLCache(ttl=1)
    cache.set("key", "value")
    time.sleep(1.1)
    assert cache.get("key") is None


def test_ttl_cache_max_size():
    cache = TTLCache(ttl=60, max_size=2)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    cache.set("k3", "v3")

    assert cache.get("k1") is None
    assert cache.get("k2") == "v2"
    assert cache.get("k3") == "v3"


def test_ttl_cache_lru_behavior():
    cache = TTLCache(ttl=60, max_size=2)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    # Access k1 to make it recently used
    cache.get("k1")
    cache.set("k3", "v3")

    # k2 should be evicted (least recently used)
    assert cache.get("k1") == "v1"
    assert cache.get("k2") is None
    assert cache.get("k3") == "v3"


def test_ttl_cache_update_refresh():
    cache = TTLCache(ttl=60, max_size=2)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    # Update k1
    cache.set("k1", "new_v1")
    cache.set("k3", "v3")

    # k2 should be evicted because k1 was updated (became most recent)
    assert cache.get("k1") == "new_v1"
    assert cache.get("k2") is None
    assert cache.get("k3") == "v3"
