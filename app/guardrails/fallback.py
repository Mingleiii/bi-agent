"""模板降级：校验失败或模型不可用时的零幻觉兜底（纯本地字符串渲染，不经 LLM）。"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.contracts.schemas import BriefingSection, BriefingSlotMetric, BriefingSlots, DataSnapshot
from app.core.formatting import fmt_num

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(default=False),  # 输出 markdown，不转义 HTML
    keep_trailing_newline=True,
    trim_blocks=True,  # markdown 模板：去掉块标签后的换行，避免多余空行
)


def _pct(v: float | None) -> str:
    if v is None:
        return "-"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.1f}%"


def render_briefing(slots: BriefingSlots) -> str:
    """简报渲染（正常路径与降级路径共用同一模板）。"""
    sections = [
        {
            "title": s.title,
            "rows": [
                {
                    "name": m.name,
                    "value": f"{fmt_num(m.value)}{m.unit}",
                    "yoy": _pct(m.yoy),
                }
                for m in s.metrics
            ],
        }
        for s in slots.sections
        if s.metrics
    ]
    tpl = _env.get_template("briefing.md.j2")
    return tpl.render(report_title=slots.report_title, sections=sections).strip()


def briefing_fallback(snapshot: DataSnapshot) -> str:
    """简报降级：直接从源数据构建槽位（本地填数，零幻觉）。"""
    slots = BriefingSlots(
        report_title=f"{snapshot.title or '大屏'}数据简报",
        sections=[
            BriefingSection(
                title="核心指标",
                metrics=[
                    BriefingSlotMetric(
                        name=m.name, value=m.value, unit=m.unit, yoy=m.yoy
                    )
                    for m in snapshot.metrics[:8]
                ],
            )
        ],
    )
    return render_briefing(slots)


def interpret_fallback(snapshot: DataSnapshot) -> str:
    """解读降级：模板化罗列事实数据。"""
    lines = []
    for m in snapshot.metrics[:6]:
        seg = f"- {m.name}：{fmt_num(m.value)}{m.unit}"
        if m.yoy is not None:
            seg += f"，同比 {_pct(m.yoy)}"
        if m.mom is not None:
            seg += f"，环比 {_pct(m.mom)}"
        lines.append(seg)
    tpl = _env.get_template("fallback_interpret.md.j2")
    return tpl.render(
        title=snapshot.title or "当前大屏",
        n=len(snapshot.metrics),
        lines="\n".join(lines),
    ).strip()


def preview_fallback(snapshot: DataSnapshot) -> str:
    """预览降级：说明无法解析截图，仅给出基于数据快照的概要。"""
    n = len(snapshot.metrics)
    return (
        f"当前大屏「{snapshot.title or ''}」包含 {n} 项核心指标。"
        "页面结构解析暂不可用，可稍后重试或查看大屏原始布局。"
    )
