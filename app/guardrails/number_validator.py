"""数字校验器（命门）：LLM 产出文本中的每个数字，都必须能在源数据中找到。

比对策略：
1. 合法数值集 = 指标值 + 同比/环比 + 预计算衍生值 + 单位换算（万/亿）+ 百分比形式。
2. 容差：相对误差 <= 0.5% 视为四舍五入等价（如 12345678 -> "1234.57万"）。
3. 豁免：非百分比的 0~100 整数（计数用语，如"3 项指标"）、1900~2099 年份。
   百分比数字不豁免，必须与同比/环比/占比对应。
"""
import re
from dataclasses import dataclass, field

# 千分位 + 小数的数字 token（含其后的 % 判定）
_TOKEN_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


@dataclass
class NumberMismatch:
    raw: str
    value: float
    reason: str


@dataclass
class ValidationResult:
    ok: bool = True
    mismatches: list[NumberMismatch] = field(default_factory=list)

    def error_feedback(self) -> str:
        """给重试调用的错误清单。"""
        lines = [f"数字 {m.raw} {m.reason}" for m in self.mismatches]
        return "以下数字与源数据不一致，请修正：\n" + "\n".join(lines)


def _rel_close(a: float, b: float, rel_tol: float = 0.005, abs_tol: float = 0.05) -> bool:
    if a == b:
        return True
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def build_allowed_numbers(allowed_values: dict[str, float]) -> list[float]:
    """由「语义标签 -> 数值」扩展出完整合法数值集（含换算与百分比形式）。"""
    numbers: list[float] = []
    for v in allowed_values.values():
        numbers.append(v)
        numbers.append(v * 100)  # 小数 0.12 的百分比形式 12
        if abs(v) >= 10000:
            numbers.append(v / 1e4)  # 万
            numbers.append(v / 1e8)  # 亿
    return numbers


def _is_exempt(value: float, is_percent: bool) -> bool:
    if is_percent:
        return False  # 百分比必须对应源数据，不豁免
    if value == int(value) and 0 <= value <= 100:
        return True  # 计数类
    if 1900 <= value <= 2099 and value == int(value):
        return True  # 年份
    return False


def validate_numbers(text: str, allowed_values: dict[str, float]) -> ValidationResult:
    """校验文本中所有数字是否都能在合法数值集中找到对应。"""
    allowed = build_allowed_numbers(allowed_values)
    result = ValidationResult()
    for m in _TOKEN_RE.finditer(text):
        raw = m.group()
        value = float(raw.replace(",", ""))
        # 判定 token 后（跳过空白）是否紧跟百分号
        rest = text[m.end():]
        is_percent = bool(re.match(r"\s*%", rest))
        # 负号还原：token 前是独立负号（前一个字符非数字，排除日期/区间）时取负
        # 仅对百分比启用——负同比/环比是 BI 文本中最常见的负数形态
        if is_percent and value > 0:
            before = text[:m.start()].rstrip()
            if before.endswith("-") and (len(before) == 1 or not before[-2].isdigit()):
                value = -value

        if _is_exempt(value, is_percent):
            continue
        if not any(_rel_close(value, a) for a in allowed):
            result.ok = False
            reason = (
                f"（{value}）未在源数据的同比/环比/占比中找到对应值"
                if is_percent
                else f"（{value}）未在源数据指标中找到对应值"
            )
            result.mismatches.append(NumberMismatch(raw=raw, value=value, reason=reason))
    return result
