"""数据预览 skill：多模态模型识别截图的结构/层级，输出概括 + 组件表格。"""
from app.contracts.schemas import PreviewDescription
from app.guardrails.fallback import preview_fallback
from app.guardrails.number_validator import ValidationResult, validate_numbers
from app.skills.base import BaseSkill, SkillContext
from app.skills.briefing import GenerationError

# 组件数量上限：超出视为结构识别异常，触发重试/降级
_MAX_COMPONENT_COUNT = 100


class PreviewSkill(BaseSkill):
    name = "preview"

    def build_messages(self, ctx: SkillContext, history: list[dict]) -> list[dict]:
        # 截图由编排层传给 backend.complete(image=...)；数据块随消息提供，
        # 帮助模型对齐组件标题与指标名（不允许在 summary 中引用数值）
        return [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content": f"{ctx.request.message}\n\n（截图见附件）\n\n{ctx.data_block()}"},
        ]

    def render_output(self, raw: str, ctx: SkillContext) -> str:
        try:
            desc = PreviewDescription.model_validate(self.parse_json(raw))
        except ValueError as e:
            raise GenerationError(
                f"结构化输出不合法（{e}），请严格按 system 要求的 JSON 结构输出。"
            )
        self._validate_components(desc)
        return self._render(desc)

    def _validate_components(self, desc: PreviewDescription) -> None:
        """组件清单合理性校验（生产可扩展：与前端组件树比对，禁止编造组件）。"""
        for c in desc.components:
            if c.count < 1 or c.count > _MAX_COMPONENT_COUNT:
                raise GenerationError(f"组件 {c.title or c.type} 数量 {c.count} 不合理，请核对截图后重新输出。")

    def _render(self, desc: PreviewDescription) -> str:
        lines = ["| 组件类型 | 内容 | 数量 |", "| --- | --- | --- |"]
        for c in desc.components:
            label = {"kpi": "指标卡", "chart": "图表", "table": "表格", "filter": "筛选器", "text": "文本", "image": "图片", "other": "其他"}
            lines.append(f"| {label.get(c.type, c.type)} | {c.title or '-'} | {c.count} |")
        return f"{desc.summary}\n\n" + "\n".join(lines)

    def validate(self, output: str, ctx: SkillContext) -> ValidationResult:
        # summary 不允许出现业务数值（规则已约束），仍统一走数字校验兜底
        return validate_numbers(output, ctx.allowed_values)

    def fallback(self, ctx: SkillContext) -> str:
        return preview_fallback(ctx.request.data_snapshot)
