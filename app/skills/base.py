"""Skill 抽象基类：三个 skill 是同一套抽象的三个实例。

统一接口保证编排层可以无差别地调度任意 skill，并共享
护栏（校验/重试/降级）与审计链路。
"""
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from app.contracts.schemas import ChatRequest
from app.guardrails.number_validator import ValidationResult

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "v1"


@dataclass
class SkillContext:
    """一次请求中该 skill 可用的全部环境。"""
    request: ChatRequest
    slimmed: dict                        # 裁剪 + 注入隔离后的数据快照
    extended: list[dict] = field(default_factory=list)  # 预计算衍生指标
    allowed_values: dict[str, float] = field(default_factory=dict)  # 合法数值集

    def data_block(self) -> str:
        """数据区：<data> 边界包裹（注入隔离后的数据 + 衍生指标）。"""
        payload = dict(self.slimmed)
        if self.extended:
            payload["derived_metrics"] = self.extended
        return f"<data>\n{json.dumps(payload, ensure_ascii=False)}\n</data>"


class BaseSkill(ABC):
    name: str = ""

    def system_prompt(self) -> str:
        """prompt 版本化：v1 目录，当前版本固定 v1，迭代需新建目录并过回归。"""
        return (_PROMPT_DIR / f"{self.name}.md").read_text(encoding="utf-8")

    @abstractmethod
    def build_messages(self, ctx: SkillContext, history: list[dict]) -> list[dict]:
        """构建 LLM 消息序列。"""

    @abstractmethod
    def render_output(self, raw: str, ctx: SkillContext) -> str:
        """LLM 原始输出 -> 用户可见文本（结构化 skill 在此做解析与渲染）。"""

    @abstractmethod
    def validate(self, output: str, ctx: SkillContext) -> ValidationResult:
        """对最终用户可见文本做数字校验。"""

    @abstractmethod
    def fallback(self, ctx: SkillContext) -> str:
        """零幻觉降级模板。"""

    def parse_json(self, raw: str) -> dict:
        """解析结构化输出；模型可能带 ```json 围栏，做容错剥离。"""
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
