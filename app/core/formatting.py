"""数值显示格式化：禁用科学计数法（BI 场景 1.23457e+07 不可读且过不了数字校验）。"""


def fmt_num(v: float) -> str:
    """整数不带小数点，非整数保持原值。"""
    if v == int(v):
        return str(int(v))
    return str(v)
