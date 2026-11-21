"""API 依赖：鉴权 + 内存滑动窗口限流（生产替换为 Redis，接口不变）。"""
import time

from fastapi import Header, Request

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger

log = get_logger(__name__)

# (调用方标识, 分钟桶) -> 计数
_rate_buckets: dict[tuple[str, int], int] = {}


async def verify_api_key(x_api_key: str = Header(default="")) -> None:
    """API Key 鉴权；配置为空表示开发模式放行（生产必须设置密钥）。"""
    settings = get_settings()
    if settings.api_key and x_api_key != settings.api_key:
        raise AppError(*ErrorCode.UNAUTHORIZED)


async def check_rate_limit(request: Request, _key=Header(default="", alias="X-API-Key")) -> None:
    """按调用方（API Key 或客户端 IP）做每分钟请求数限制。"""
    settings = get_settings()
    caller = _key or (request.client.host if request.client else "unknown")
    bucket = int(time.time() // 60)
    key = (caller, bucket)
    count = _rate_buckets.get(key, 0) + 1
    _rate_buckets[key] = count
    # 清理过期桶，防内存增长
    if len(_rate_buckets) > 10000:
        stale = [k for k in _rate_buckets if k[1] < bucket - 1]
        for k in stale:
            _rate_buckets.pop(k, None)
    if count > settings.rate_limit_per_min:
        raise AppError(*ErrorCode.RATE_LIMITED, detail=f"caller={caller}")
