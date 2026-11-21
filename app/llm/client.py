"""LLM 统一客户端（防腐层）。

设计要点：
- LLMBackend 是唯一的模型访问入口，业务层不直接依赖任何 SDK。
  这样 DeepAgent / LangChain 等框架后续接入时，只需实现一个 Backend，
  核心链路（编排/护栏/审计）零改动。
- mock 后端：确定性输出，用于开发与测试，全链路可跑、可断言。
- openai 后端：OpenAI 兼容 /chat/completions（含 DeepSeek、Qwen、
  内网网关等），带超时、指数退避重试、简单熔断。

接入 DeepAgent 框架的示例（后续迭代）：

    from deepagents import create_deep_agent

    class DeepAgentBackend(LLMBackend):
        def __init__(self, agent):
            self._agent = agent
        async def complete(self, messages, *, json_mode=False, model=None, image=None):
            result = await self._agent.ainvoke({"messages": messages})
            return result["messages"][-1].content
"""
import asyncio
import json
import re
import time
from abc import ABC, abstractmethod

import httpx

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger

log = get_logger(__name__)

Message = dict  # {"role": "system" | "user" | "assistant", "content": str}

_DATA_RE = re.compile(r"<data>(.*?)</data>", re.S)


class LLMBackend(ABC):
    """模型后端抽象。"""

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        *,
        json_mode: bool = False,
        model: str | None = None,
        image: str | None = None,
    ) -> str:
        """返回模型输出文本；json_mode 时要求输出合法 JSON。"""

    async def ready(self) -> bool:
        return True


# ---------------------------------------------------------------- mock 后端

class MockLLMBackend(LLMBackend):
    """确定性 mock：按 system prompt 的任务标识生成回复。

    fail_mode 用于测试护栏链路：
    - ok: 正常输出（数字全部取自源数据，可通过数字校验）
    - bad_numbers: 解读输出篡改数字（触发校验失败 -> 重试 -> 降级）
    - timeout: 抛超时（触发超时错误路径）
    """

    def __init__(self, fail_mode: str = "ok"):
        self.fail_mode = fail_mode

    def _extract_snapshot(self, messages: list[Message]) -> dict:
        """从任意一条消息中提取 <data> 数据块（重试消息在最后，数据块在前）。"""
        for m in reversed(messages):
            if m["role"] != "user":
                continue
            match = _DATA_RE.search(m["content"])
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        return {}

    async def complete(self, messages, *, json_mode=False, model=None, image=None) -> str:
        await asyncio.sleep(0)  # 保持 async 形态
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        snapshot = self._extract_snapshot(messages)

        if self.fail_mode == "timeout":
            raise TimeoutError("mock timeout")

        if "意图路由" in system:
            return json.dumps(self._route(self._last_user(messages)), ensure_ascii=False)
        if "简报" in system:
            return json.dumps(self._briefing(snapshot), ensure_ascii=False)
        if "预览" in system:
            return json.dumps(self._preview(snapshot, image), ensure_ascii=False)
        return self._interpret(snapshot)

    @staticmethod
    def _last_user(messages: list[Message]) -> str:
        return next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    def _route(self, user_text: str) -> dict:
        if any(k in user_text for k in ("简报", "日报", "周报", "汇报")):
            return {"skill": "briefing", "confidence": 0.92}
        if any(k in user_text for k in ("截图", "预览", "结构", "布局", "页面")):
            return {"skill": "preview", "confidence": 0.9}
        return {"skill": "interpret", "confidence": 0.88}

    def _fmt(self, v: float) -> str:
        from app.core.formatting import fmt_num

        return fmt_num(v)

    def _pct(self, v: float) -> str:
        return f"{v * 100:.1f}%"

    def _interpret(self, snapshot: dict) -> str:
        metrics = snapshot.get("metrics", [])
        title = snapshot.get("title") or "当前大屏"
        if not metrics:
            return f"本期「{title}」暂无有效指标数据，请检查大屏数据源。"
        lines = []
        for m in metrics[:5]:
            seg = f"- {m['name']}：{self._fmt(m['value'])}{m.get('unit', '')}"
            if m.get("yoy") is not None:
                seg += f"，同比 {self._pct(m['yoy'])}"
            if m.get("mom") is not None:
                seg += f"，环比 {self._pct(m['mom'])}"
            lines.append(seg)
        rising = sum(1 for m in metrics if (m.get("yoy") or 0) > 0)
        body = "\n".join(lines)
        if self.fail_mode == "bad_numbers":
            # 故意篡改最大指标值：用于验证数字校验 -> 重试 -> 模板降级链路
            big = max(metrics, key=lambda x: abs(x["value"]))
            return (
                f"本期「{title}」核心指标表现强势：{big['name']} 高达 "
                f"{self._fmt(big['value'] * 3)}{big.get('unit', '')}，"
                f"同比 {self._pct((big.get('yoy') or 0) * 5)}。\n{body}"
            )
        return (
            f"「{title}」本期共 {len(metrics)} 项核心指标：\n{body}\n"
            f"整体看，{rising} 项指标同比增长，建议关注同比为负的指标的归因分析。"
        )

    def _briefing(self, snapshot: dict) -> dict:
        metrics = snapshot.get("metrics", [])
        return {
            "report_title": f"{snapshot.get('title') or '大屏'}数据简报",
            "sections": [
                {
                    "title": "核心指标",
                    "metrics": [
                        {
                            "name": m["name"],
                            "value": m["value"],
                            "unit": m.get("unit", ""),
                            "yoy": m.get("yoy"),
                        }
                        for m in metrics[:5]
                    ],
                }
            ],
        }

    def _preview(self, snapshot: dict, image: str | None) -> dict:
        n = len(snapshot.get("metrics", []))
        return {
            "summary": (
                "页面为典型经营分析大屏布局：顶部为标题与全局筛选区，"
                f"中部为 {min(n, 8)} 个 KPI 指标卡，下方为趋势图表与明细表格。"
            ),
            "components": [
                {"type": "kpi", "title": "核心指标卡", "count": min(n, 8)},
                {"type": "chart", "title": "趋势分析", "count": 1},
                {"type": "filter", "title": "全局筛选", "count": 1},
            ],
        }


# ---------------------------------------------------------------- openai 兼容后端

class OpenAICompatBackend(LLMBackend):
    """OpenAI 兼容接口 + 超时 + 指数退避重试 + 简单熔断。"""

    FAILURE_THRESHOLD = 5
    OPEN_SECONDS = 30.0

    def __init__(self):
        s = get_settings()
        self._client = httpx.AsyncClient(
            base_url=s.llm_base_url,
            headers={"Authorization": f"Bearer {s.llm_api_key}"},
            timeout=s.llm_timeout_seconds,
        )
        self._failures = 0
        self._opened_at = 0.0

    # -- 熔断 --
    def _allow(self) -> bool:
        if self._failures < self.FAILURE_THRESHOLD:
            return True
        if time.monotonic() - self._opened_at > self.OPEN_SECONDS:
            self._failures = 0  # 半开：放行试探
            return True
        return False

    def _record(self, ok: bool) -> None:
        if ok:
            self._failures = 0
        else:
            self._failures += 1
            if self._failures == self.FAILURE_THRESHOLD:
                self._opened_at = time.monotonic()
                log.warning("llm circuit opened")

    async def ready(self) -> bool:
        try:
            r = await self._client.get("/models", timeout=3.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def complete(self, messages, *, json_mode=False, model=None, image=None) -> str:
        if not self._allow():
            raise AppError(*ErrorCode.MODEL_UNAVAILABLE, detail="circuit open")

        s = get_settings()
        payload: dict = {"model": model or s.model_large, "messages": [], "temperature": 0.2}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        # 图片走多模态 content 结构（仅最后一条 user 消息支持携带）
        for m in messages:
            if m["role"] == "user" and image:
                payload["messages"].append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": m["content"]},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}},
                        ],
                    }
                )
            else:
                payload["messages"].append(m)

        last_err: Exception | None = None
        for attempt in range(s.llm_max_retries + 1):
            try:
                r = await self._client.post("/chat/completions", json=payload)
                r.raise_for_status()
                text = r.json()["choices"][0]["message"]["content"]
                if json_mode:
                    json.loads(text)  # 尽早暴露非法 JSON
                self._record(True)
                return text
            except TimeoutError:
                last_err = None
                raise AppError(*ErrorCode.MODEL_TIMEOUT, detail=f"attempt={attempt}")
            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
                last_err = e
                self._record(False)
                if attempt < s.llm_max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))  # 指数退避
        raise AppError(*ErrorCode.MODEL_UNAVAILABLE, detail=str(last_err))


# ---------------------------------------------------------------- 工厂

_backend: LLMBackend | None = None


def get_backend() -> LLMBackend:
    """按配置返回后端单例；测试可 monkeypatch 本函数注入定制后端。"""
    global _backend
    if _backend is None:
        s = get_settings()
        _backend = MockLLMBackend() if s.llm_provider == "mock" else OpenAICompatBackend()
    return _backend


def reset_backend() -> None:
    """测试辅助：强制重建后端。"""
    global _backend
    _backend = None
