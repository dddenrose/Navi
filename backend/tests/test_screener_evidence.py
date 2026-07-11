"""Evidence gate 揭露內容的守門測試."""

from services.screener.evidence import get_evidence


def test_momentum_is_backtested_with_caveats():
    ev = get_evidence("momentum")
    assert ev["profile"] == "momentum"
    assert ev["status"] == "backtested"
    # 有回測必須同時揭露方法、期間、警語 —— 缺一不可
    assert ev["backtest_period"]
    assert ev["method"]
    assert ev["metrics"]["hold_13w"]["excess_cagr"] is not None
    assert any("倖存者偏差" in c for c in ev["caveats"])
    assert any("過去績效" in c for c in ev["caveats"])


def test_value_is_experimental_and_says_why():
    ev = get_evidence("value")
    assert ev["status"] == "experimental"
    assert ev["metrics"] == {}
    assert any("無法誠實回測" in c or "look-ahead" in c for c in ev["caveats"])
    # 金融股結構性排除的透明化揭露
    assert any("金融" in c for c in ev["caveats"])
