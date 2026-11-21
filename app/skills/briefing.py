"""简报 skill：LLM 槽位填数 + Jinja2 模板渲染。

流程：结构化输出（槽位 JSON）-> 槽位值与源数据比对 -> 渲染 markdown ->
对最终 markdown 再做数字校验（校验的是用户真正看到的东西）。
"""
from app.contracts.schemas import BriefingSlots
from app.guardrails.fallback import briefing_fallback, render_briefing
from app.guardrails.number_validator import (
    NumberMismatch,
    ValidationResult,
    _rel_close,
    validate_numbers,
)
from app.skills.base import BaseSkill, SkillContext


class GenerationError(Exception):
    """生成质量错误（JSON 不合法 / 槽位值不一致）：可带反馈重试。"""

    def __init__(self, feedback: str):
        self.feedback = feedback
        super().__init__(feedback)


class BriefingSkill(BaseSkill):
    name = "briefing"

    def build_messages(self, ctx: SkillContext, history: list[dict]) -> list[dict]:
        # 简报为单轮任务，不携带历史，避免数字来源被污染
        return [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": f"需要汇报的指标说明：{ctx.request.message}\n\n{ctx.data_block()}",
            },
        ]

    def render_output(self, raw: str, ctx: SkillContext) -> str:
        try:
            slots = BriefingSlots.model_validate(self.parse_json(raw))
        except ValueError as e:
            raise GenerationError(
                f"结构化输出不合法（{e}），请严格按 system 要求的 JSON 槽位结构输出。"
            )
        self._validate_slots(slots, ctx)
        return render_briefing(slots)

    def _validate_slots(self, slots: BriefingSlots, ctx: SkillContext) -> None:
        """槽位值必须与源数据一致（LLM 只允许复制，不允许换算）。"""
        mismatches = []
        for s in slots.sections:
            for m in s.metrics:
                src = ctx.allowed_values.get(m.name)
                if src is None or not _rel_close(m.value, src):
                    mismatches.append(
                        NumberMismatch(
                            raw=str(m.value),
                            value=m.value,
                            reason=f"指标 {m.name} 的槽位值与源数据不一致",
                        )
                    )
        if mismatches:
            vr = ValidationResult(ok=False, mismatches=mismatches)
            raise GenerationError(vr.error_feedback())

    def validate(self, output: str, ctx: SkillContext) -> ValidationResult:
        # 渲染后的 markdown 表格数字来自已校验槽位，仍走统一数字校验器兜底
        return validate_numbers(output, ctx.allowed_values)

    def fallback(self, ctx: SkillContext) -> str:
        return briefing_fallback(ctx.request.data_snapshot)
