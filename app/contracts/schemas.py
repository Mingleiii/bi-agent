"""契约层：输入/输出/SSE 事件/LLM 结构化输出的唯一事实源。

前端与后端都对着这份契约开发；字段变更必须走版本评审。
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field

SkillName = Literal["interpret", "briefing", "preview"]


# ---------- 前端输入 ----------

class Metric(BaseModel):
    """大屏单个指标：LLM 产出的数字只允许来自这里（及预处理派生值）。"""
    name: str = Field(..., description="指标名，如 GMV")
    value: float = Field(..., description="指标值")
    unit: str = ""
    yoy: Optional[float] = Field(None, description="同比，小数形式，0.12 表示 +12%")
    mom: Optional[float] = Field(None, description="环比，小数形式")


class DataSnapshot(BaseModel):
    """大屏数据快照：由前端在请求时采集。"""
    title: str = ""
    metrics: list[Metric] = Field(default_factory=list)
    updated_at: str = ""


class ChatRequest(BaseModel):
    screen_id: str = Field(..., min_length=1)
    data_snapshot: DataSnapshot
    # 仅 preview skill 需要；接 base64（不带 data:image 前缀亦可）
    screenshot: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=4000)
    # 用户在前端显式选择 skill 时直通，不做 LLM 路由
    skill: Optional[SkillName] = None
    session_id: Optional[str] = None


# ---------- SSE 事件 ----------

class RoutingEvent(BaseModel):
    skill: SkillName
    confidence: float = 1.0
    routed_by: Literal["explicit", "rule", "llm"] = "explicit"


class ClarifyEvent(BaseModel):
    """低置信路由时的反问。"""
    question: str


class ChunkEvent(BaseModel):
    delta: str


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class DoneEvent(BaseModel):
    usage: UsageInfo = Field(default_factory=UsageInfo)
    cached: bool = False
    degraded: bool = False


class ErrorEvent(BaseModel):
    code: str
    message: str
    trace_id: str = ""


# ---------- LLM 结构化输出 ----------

class BriefingSlotMetric(BaseModel):
    name: str
    value: float
    unit: str = ""
    yoy: Optional[float] = None


class BriefingSection(BaseModel):
    title: str
    metrics: list[BriefingSlotMetric] = Field(default_factory=list)


class BriefingSlots(BaseModel):
    """简报 skill 的槽位结构：LLM 只负责把源数据填进槽位，不允许出现槽位外的数字。"""
    report_title: str = "数据简报"
    sections: list[BriefingSection] = Field(default_factory=list)


class PreviewComponent(BaseModel):
    type: Literal["kpi", "chart", "table", "filter", "text", "image", "other"]
    title: str = ""
    count: int = 1


class PreviewDescription(BaseModel):
    """数据预览 skill 的结构化输出：页面结构概括 + 组件表格。"""
    summary: str
    components: list[PreviewComponent] = Field(default_factory=list)
