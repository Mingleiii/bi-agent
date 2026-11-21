"""衍生指标预计算：占比、同比差值等在代码里算好，禁止 LLM 心算。

预计算结果：
1. 计入数字校验器的合法数值集（allowed numbers）；
2. 作为 extended_metrics 附加进 prompt 数据区，供解读分析引用。
"""
from app.contracts.schemas import DataSnapshot


def derive(snapshot: DataSnapshot) -> list[dict]:
    derived: list[dict] = []
    metrics = snapshot.metrics
    total = sum(m.value for m in metrics if m.value > 0)
    if metrics and total > 0:
        for m in metrics:
            if m.value > 0 and m.name:
                derived.append(
                    {"name": f"{m.name}占比", "value": round(m.value / total, 4), "unit": ""}
                )
    return derived


def build_allowed_values(snapshot: DataSnapshot) -> dict[str, float]:
    """源数值 -> 语义标签：数字校验器据此刻画合法数值集。"""
    allowed: dict[str, float] = {}
    for m in snapshot.metrics:
        allowed[m.name] = m.value
        if m.yoy is not None:
            allowed[f"{m.name}同比"] = m.yoy
        if m.mom is not None:
            allowed[f"{m.name}环比"] = m.mom
    for d in derive(snapshot):
        allowed[d["name"]] = d["value"]
    return allowed
