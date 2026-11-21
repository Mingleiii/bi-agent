"""响应缓存：内存 LRU + TTL（生产替换为 Redis，键即数据指纹）。"""
import time
from collections import OrderedDict

from app.core.config import get_settings

_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_MAX_ENTRIES = 512


def get(key: str) -> dict | None:
    if not get_settings().cache_on:
        return None
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > get_settings().cache_ttl_seconds:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return value


def put(key: str, value: dict) -> None:
    if not get_settings().cache_on:
        return
    _cache[key] = (time.monotonic(), value)
    _cache.move_to_end(key)
    while len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)


def reset() -> None:
    """测试辅助。"""
    _cache.clear()
