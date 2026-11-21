"""FastAPI 入口：中间件、路由注册、全局异常处理。

启动：uvicorn app.main:app --reload --port 8600
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import chat, health
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger, setup_logging
from app.observability.tracing import TraceMiddleware

setup_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # 预热：提前初始化后端单例（连接池/密钥问题在启动期暴露）
    from app.llm.client import get_backend

    get_backend()
    log.info("bi-agent started", extra={"env": settings.env, "provider": settings.llm_provider})
    yield
    log.info("bi-agent stopped")


app = FastAPI(title="BI Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceMiddleware)
app.include_router(chat.router)
app.include_router(health.router)


# ---- 全局异常：统一错误码体系 ----

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.user_message},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # pydantic 校验失败统一转 E1001，信息走日志不外泄细节
    log.warning("invalid request: %s", exc.errors()[:3])
    code, msg, status = ErrorCode.INVALID_INPUT
    return JSONResponse(status_code=status, content={"code": code, "message": msg})
