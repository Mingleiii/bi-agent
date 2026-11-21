"""意图路由：显式指定直通 -> 关键词规则 -> LLM 路由（失败回落规则）。

置信度低于阈值时返回 None，由编排层下发 clarify 反问事件。
"""
import json

from app.contracts.schemas import ChatRequest
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.client import get_backend
from app.llm.model_router import resolve_model

log = get_logger(__name__)

_RULES: list[tuple[tuple[str, ...], str]] = [
    (("简报", "日报", "周报", "汇报", "briefing"), "briefing"),
    (("截图", "预览", "页面结构", "布局", "组件"), "preview"),
    (("解读", "分析", "怎么看", "总结", "interpret"), "interpret"),
]

_ROUTER_PROMPT = None  # 延迟加载


def _router_prompt() -> str:
    global _ROUTER_PROMPT
    if _ROUTER_PROMPT is None:
        from pathlib import Path

        p = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "v1" / "router.md"
        _ROUTER_PROMPT = p.read_text(encoding="utf-8")
    return _ROUTER_PROMPT


class RouteResult:
    def __init__(self, skill: str, confidence: float, routed_by: str):
        self.skill = skill
        self.confidence = confidence
        self.routed_by = routed_by  # explicit | rule | llm


async def route(request: ChatRequest) -> RouteResult | None:
    """返回路由结果；None 表示低置信需要反问。"""
    # 1. 显式指定直通：快且确定
    if request.skill:
        return RouteResult(request.skill, 1.0, "explicit")

    # 2. 关键词规则：零成本、可解释
    for keywords, skill in _RULES:
        if any(k in request.message for k in keywords):
            return RouteResult(skill, 0.95, "rule")

    # 3. LLM 路由：小模型 + JSON 输出；异常回落 interpret（最通用场景）
    threshold = get_settings().route_confidence_threshold
    try:
        backend = get_backend()
        raw = await backend.complete(
            [
                {"role": "system", "content": _router_prompt()},
                {"role": "user", "content": request.message},
            ],
            json_mode=True,
            model=resolve_model("routing"),
        )
        result = json.loads(raw)
        skill, confidence = result["skill"], float(result.get("confidence", 0))
        if skill not in ("interpret", "briefing", "preview"):
            raise ValueError(f"unknown skill: {skill}")
    except Exception:  # noqa: BLE001 路由失败不阻断：回落默认 skill
        log.warning("llm routing failed, fallback to interpret", exc_info=True)
        return RouteResult("interpret", 0.5, "rule")

    if confidence < threshold:
        return None
    return RouteResult(skill, confidence, "llm")
