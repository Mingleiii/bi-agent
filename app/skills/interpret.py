"""解读分析 skill：基于大屏数据快照输出简洁、准确的事实性解读。"""
from app.guardrails.fallback import interpret_fallback
from app.guardrails.number_validator import ValidationResult, validate_numbers
from app.skills.base import BaseSkill, SkillContext


class InterpretSkill(BaseSkill):
    name = "interpret"

    def build_messages(self, ctx: SkillContext, history: list[dict]) -> list[dict]:
        messages = [{"role": "system", "content": self.system_prompt()}]
        messages.extend(history)  # 多轮上下文（session 层已截断）
        messages.append(
            {
                "role": "user",
                "content": f"{ctx.request.message}\n\n{ctx.data_block()}",
            }
        )
        return messages

    def render_output(self, raw: str, ctx: SkillContext) -> str:
        return raw.strip()  # 自由文本 skill，原样透出（数字护栏兜底）

    def validate(self, output: str, ctx: SkillContext) -> ValidationResult:
        return validate_numbers(output, ctx.allowed_values)

    def fallback(self, ctx: SkillContext) -> str:
        return interpret_fallback(ctx.request.data_snapshot)
