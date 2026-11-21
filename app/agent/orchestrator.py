"""编排器：一次请求的完整生命周期。

trace中间件 -> 鉴权/限流(deps) -> 路由 -> 预处理 -> 缓存
-> skill 生成 -> 护栏(数字校验) -> 重试 -> 降级 -> SSE 事件流。

事件序列：routing -> (clarify) -> chunk* -> done | error
"""
import time
from collections.abc import AsyncIterator

from app.agent import intent_router, session
from app.cache import response_cache
from app.contracts.schemas import ChatRequest
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger, get_trace_id
from app.guardrails.injection import sanitize
from app.llm.client import get_backend
from app.llm.model_router import resolve_model
from app.observability import audit
from app.preprocessing.derive import build_allowed_values, derive
from app.preprocessing.fingerprint import fingerprint
from app.preprocessing.slimming import slim
from app.skills.base import SkillContext
from app.skills.briefing import BriefingSkill, GenerationError
from app.skills.interpret import InterpretSkill
from app.skills.preview import PreviewSkill

log = get_logger(__name__)

SKILLS = {
    "interpret": InterpretSkill(),
    "briefing": BriefingSkill(),
    "preview": PreviewSkill(),
}


class Orchestrator:
    """handle() 是唯一入口，产出 (event_name, payload) 事件流。"""

    async def handle(self, request: ChatRequest) -> AsyncIterator[tuple[str, dict]]:
        # ---------- 1. 预处理：裁剪 + 注入隔离 + 预计算 ----------
        snapshot = request.data_snapshot
        slimmed = sanitize(slim(snapshot))
        ctx = SkillContext(
            request=request,
            slimmed=slimmed,
            extended=derive(snapshot),
            allowed_values=build_allowed_values(snapshot),
        )

        # ---------- 2. 意图路由 ----------
        route_result = await intent_router.route(request)
        if route_result is None:
            yield "clarify", {
                "question": "你想让我做什么？可直接选择：解读分析、生成简报、页面结构预览。"
            }
            return
        yield "routing", {
            "skill": route_result.skill,
            "confidence": route_result.confidence,
            "routed_by": route_result.routed_by,
        }
        skill = SKILLS[route_result.skill]

        # 预览 skill 的前置条件
        if skill.name == "preview" and not request.screenshot:
            raise AppError(*ErrorCode.MISSING_SCREENSHOT)

        # ---------- 3. 缓存 ----------
        fp = fingerprint(slimmed, skill.name, request.message)
        cached = response_cache.get(fp)
        if cached is not None:
            yield "chunk", {"delta": cached["text"]}
            yield "done", {"usage": {}, "cached": True, "degraded": False}
            return

        # ---------- 4. 生成 + 护栏 ----------
        started = time.monotonic()
        text, degraded = await self._generate(skill, ctx)
        latency_ms = int((time.monotonic() - started) * 1000)

        # ---------- 5. 会话与缓存 ----------
        if not degraded:
            # 只缓存通过护栏的结果；降级结果不落缓存，避免瞬时故障被放大
            response_cache.put(fp, {"text": text})

        # ---------- 6. 产出事件 ----------
        yield "chunk", {"delta": text}
        yield "done", {
            "usage": {},
            "cached": False,
            "degraded": degraded,
        }

        # ---------- 7. 会话记录 + 审计（不影响主链路） ----------
        session.append_turn(request.session_id, request.message, text)
        audit.write_audit(
            {
                "skill": skill.name,
                "screen_id": request.screen_id,
                "message": request.message[:200],
                "cached": False,
                "degraded": degraded,
                "model": resolve_model(skill.name),
                "latency_ms": latency_ms,
            }
        )

    async def _generate(self, skill, ctx: SkillContext) -> tuple[str, bool]:
        """生成 -> 校验 -> 带反馈重试一次 -> 仍失败/模型故障则模板降级。"""
        settings = get_settings()
        backend = get_backend()
        model = resolve_model(skill.name)
        base_messages = skill.build_messages(ctx, session.get_history(ctx.request.session_id))
        image = ctx.request.screenshot if skill.name == "preview" else None
        json_mode = skill.name != "interpret"

        feedback: str | None = None
        last_raw = ""
        for _attempt in range(2):  # 1 次生成 + 1 次带反馈重试
            messages = list(base_messages)
            if feedback is not None:
                messages.append({"role": "assistant", "content": last_raw})
                messages.append({"role": "user", "content": f"修正要求：{feedback}"})
            try:
                raw = await backend.complete(
                    messages, json_mode=json_mode, model=model, image=image
                )
            except AppError as e:
                # 模型超时/不可用/熔断：不再重试生成，直接模板降级，接口永远有响应
                log.warning("llm unavailable, degrade to fallback: %s", e)
                return skill.fallback(ctx), True

            last_raw = raw
            # 渲染（结构化解析与槽位校验在此触发）
            try:
                text = skill.render_output(raw, ctx)
                gen_error: GenerationError | None = None
            except GenerationError as e:
                gen_error = e

            if gen_error is not None:
                feedback = gen_error.feedback
                continue

            if not settings.guardrail_on:
                return text, False
            verdict = skill.validate(text, ctx)
            if verdict.ok:
                return text, False
            feedback = verdict.error_feedback()
            log.info(
                "number validation failed, retrying",
                extra={"mismatches": [m.raw for m in verdict.mismatches]},
            )

        log.warning("guardrail retry exhausted, degrade to fallback")
        return skill.fallback(ctx), True


orchestrator = Orchestrator()
