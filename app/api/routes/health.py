"""健康检查：/livez 存活探针；/readyz 就绪探针（探测模型后端可用性）。"""
from fastapi import APIRouter

from app.core.config import get_settings
from app.llm.client import get_backend

router = APIRouter(tags=["health"])


@router.get("/livez")
async def livez() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict:
    """readyz = 进程存活 + 模型后端可用，防止流量打到已降级实例。"""
    settings = get_settings()
    backend = get_backend()
    ready = await backend.ready()
    return {
        "status": "ok" if ready else "degraded",
        "llm_provider": settings.llm_provider,
        "ready": ready,
    }
