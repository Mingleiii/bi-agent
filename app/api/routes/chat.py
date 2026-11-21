"""POST /api/chat：SSE 主接口。

事件协议（契约层定义的最终形态）：
  routing -> chunk* -> done          正常链路
  routing -> clarify                 低置信反问
  error                              任意阶段异常
"""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import orchestrator
from app.api import deps
from app.contracts.schemas import ChatRequest
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger, get_trace_id

router = APIRouter(prefix="/api", tags=["chat"])
log = get_logger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(
    request: ChatRequest,
    _auth: None = Depends(deps.verify_api_key),
    _rate: None = Depends(deps.check_rate_limit),
) -> StreamingResponse:
    async def event_stream():
        try:
            async for event_name, payload in orchestrator.handle(request):
                yield _sse(event_name, payload)
        except AppError as e:
            yield _sse(
                "error",
                {"code": e.code, "message": e.user_message, "trace_id": get_trace_id()},
            )
        except Exception:  # noqa: BLE001 兜底：任何未知异常都转为 error 事件，绝不悬挂连接
            log.exception("unexpected error in chat stream")
            code, msg, _ = ErrorCode.INTERNAL
            yield _sse("error", {"code": code, "message": msg, "trace_id": get_trace_id()})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
