"""数字校验器单测（命门模块，覆盖换算/百分比/豁免/篡改）。"""
from app.guardrails.number_validator import validate_numbers


ALLOWED = {
    "GMV": 12345678,
    "GMV同比": 0.12,
    "GMV环比": -0.03,
    "订单量": 88000,
    "客单价占比": 0.352,  # 衍生指标（小数形式）
}


def test_source_value_passes():
    r = validate_numbers("本期GMV为12345678元，表现稳健。", ALLOWED)
    assert r.ok


def test_wan_conversion_passes():
    r = validate_numbers("GMV约1234.57万。", ALLOWED)
    assert r.ok


def test_yi_conversion_passes():
    r = validate_numbers("GMV约0.12亿。", ALLOWED)
    assert r.ok


def test_thousand_separator_passes():
    r = validate_numbers("本期GMV为12,345,678元。", ALLOWED)
    assert r.ok


def test_yoy_percent_passes():
    r = validate_numbers("GMV同比增长12.0%。", ALLOWED)
    assert r.ok


def test_derived_percent_passes():
    r = validate_numbers("客单价占比35.2%。", ALLOWED)
    assert r.ok


def test_fabricated_number_fails():
    r = validate_numbers("GMV高达99999999元。", ALLOWED)
    assert not r.ok
    assert any(m.value == 99999999 for m in r.mismatches)


def test_fabricated_percent_fails():
    r = validate_numbers("GMV同比暴涨45.6%。", ALLOWED)
    assert not r.ok


def test_counting_exempt():
    r = validate_numbers("大屏共 3 项核心指标，其中 2 项增长。", ALLOWED)
    assert r.ok


def test_year_exempt():
    r = validate_numbers("2026年整体表现平稳。", ALLOWED)
    assert r.ok


def test_mixed_valid_and_invalid():
    r = validate_numbers("GMV为12345678元，但订单量达到500000。", ALLOWED)
    assert not r.ok
    assert len(r.mismatches) == 1  # 只有 500000 不合法
