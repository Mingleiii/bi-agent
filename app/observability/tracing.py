"""trace_id 中间件：前端可透传 X-Request-ID，否则自动生成；全链路日志/审计共用。"""
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import set_trace_id


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Request-ID") or uuid4().hex[:16]
        set_trace_id(trace_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = trace_id
        return response
