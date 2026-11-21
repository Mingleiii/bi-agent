"""大屏 JSON 裁剪：白名单字段提取，剔除样式/坐标等与解读无关的字段。

前端快照可能携带颜色、位置等展示字段；进入 prompt 前统一瘦身，
降低 token 成本并缩小注入面。
"""
from app.contracts.schemas import DataSnapshot

# 允许进入 prompt 的字段白名单；新增字段必须在此登记
_METRIC_FIELDS = ("name", "value", "unit", "yoy", "mom")
_SNAPSHOT_FIELDS = ("title", "metrics", "updated_at")


def slim(snapshot: DataSnapshot) -> dict:
    return {
        "title": snapshot.title,
        "updated_at": snapshot.updated_at,
        "metrics": [
            {k: m.model_dump()[k] for k in _METRIC_FIELDS if m.model_dump().get(k) is not None}
            for m in snapshot.metrics
        ],
    }
