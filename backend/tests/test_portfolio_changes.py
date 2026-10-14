"""持股變更：股票辨識、單位換算、驗證、待確認清單文字與確認後寫入."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from services import portfolio_changes as pc
from services.portfolio_service import Holding

# 測試不連 TWSE：名稱 / 代號 → yfinance ticker 用固定表
_TICKERS = {
    "台積電": "2330.TW",
    "2330": "2330.TW",
    "2330.TW": "2330.TW",
    "鴻海": "2317.TW",
    "2317": "2317.TW",
    "南亞科": "2408.TW",
    "2408": "2408.TW",
    "0050": "0050.TW",
    "環球晶": "6488.TWO",
    "AAPL": "AAPL",
}
_NAMES = {
    "2330": "台積電",
    "2317": "鴻海",
    "2408": "南亞科",
    "0050": "元大台灣50",
    "6488": "環球晶",
}


def _normalize(raw: str) -> str:
    raw = raw.strip()
    return _TICKERS.get(raw, _TICKERS.get(raw.upper(), raw.upper()))


def _search(code: str, limit: int = 10) -> list[dict]:
    return [{"code": code, "name": _NAMES[code]}] if code in _NAMES else []


@pytest.fixture(autouse=True)
def offline_stocks():
    with (
        patch.object(pc, "normalize_ticker", side_effect=_normalize),
        patch.object(pc, "search_tw_stocks", side_effect=_search),
    ):
        yield


def _holding(ticker: str, shares: float, avg_cost: float, hid: str = "h1") -> Holding:
    return Holding(id=hid, ticker=ticker, name="", shares=shares, avg_cost=avg_cost)


def _trade(**overrides) -> dict:
    trade = {"stock": "台積電", "action": "buy", "quantity": 2, "unit": "張", "price": 600}
    trade.update(overrides)
    return trade


# ── 股票辨識與持股比對 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("台積電", ("2330.TW", "台積電")),
        ("2330", ("2330.TW", "台積電")),
        ("台積電 2330", ("2330.TW", "台積電")),  # 名稱加代號，以代號為準
        ("環球晶", ("6488.TWO", "環球晶")),  # 上櫃
        ("AAPL", ("AAPL", "AAPL")),
    ],
)
def test_resolve_stock(text, expected):
    assert pc.resolve_stock(text) == expected


@pytest.mark.parametrize("text", ["台基店", "", "  "])
def test_unknown_stock_is_rejected(text):
    assert pc.resolve_stock(text) is None


def test_existing_holding_matches_however_the_web_stored_it():
    holdings = [_holding("南亞科", 1000, 50, "a"), _holding("0050", 500, 120, "b")]

    assert pc.find_holding(holdings, "2408.TW").id == "a"
    assert pc.find_holding(holdings, "0050.TW").id == "b"
    assert pc.find_holding(holdings, "2330.TW") is None


# ── build_trades ─────────────────────────────────────────────────────────────


def test_lots_are_converted_to_shares_and_date_defaults_to_today():
    items, errors = pc.build_trades([], [_trade()])

    assert errors == []
    assert items == [
        {
            "ticker": "2330.TW",
            "name": "台積電",
            "action": "buy",
            "shares": 2000,
            "price": 600.0,
            "fee": None,
            "trade_date": pc.today_taipei().isoformat(),
        }
    ]


def test_odd_lot_shares_are_kept():
    items, _ = pc.build_trades([], [_trade(quantity=37, unit="股")])
    assert items[0]["shares"] == 37


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"stock": "台基店"}, "找不到股票「台基店」"),
        ({"action": "hold"}, "買進還是賣出"),
        ({"quantity": 0}, "數量必須大於 0"),
        ({"quantity": "兩"}, "數量不是數字"),
        ({"unit": "口"}, "單位要是張或股"),
        ({"quantity": 1.5, "unit": "股"}, "台股股數必須是整數"),
        ({"price": 0}, "價格必須大於 0"),
        ({"fee": -1}, "手續費不能是負數"),
        ({"trade_date": "2026/10/14"}, "YYYY-MM-DD"),
    ],
)
def test_invalid_trade_is_rejected(overrides, message):
    items, errors = pc.build_trades([], [_trade(**overrides)])

    assert items == []
    assert len(errors) == 1
    assert errors[0].startswith("第 1 筆：")
    assert message in errors[0]


def test_future_trade_date_is_rejected():
    tomorrow = (pc.today_taipei() + timedelta(days=1)).isoformat()
    _, errors = pc.build_trades([], [_trade(trade_date=tomorrow)])
    assert "未來" in errors[0]


def test_past_trade_date_is_kept():
    items, _ = pc.build_trades([], [_trade(trade_date="2026-10-01")])
    assert items[0]["trade_date"] == "2026-10-01"


def test_one_bad_trade_blocks_the_whole_batch():
    items, errors = pc.build_trades([], [_trade(), _trade(stock="台基店")])
    assert items == []
    assert errors == ["第 2 筆：找不到股票「台基店」"]


def test_selling_more_than_held_is_rejected():
    holdings = [_holding("2330", 1000, 500)]
    _, errors = pc.build_trades(holdings, [_trade(action="sell", quantity=2)])
    assert errors == ["第 1 筆：賣出 2,000 股超過目前持有的 1,000 股"]


def test_sell_counts_buys_earlier_in_the_same_batch():
    trades = [_trade(quantity=1), _trade(action="sell", quantity=2000, unit="股")]
    items, errors = pc.build_trades([_holding("台積電", 1000, 500)], trades)
    assert errors == []
    assert [i["action"] for i in items] == ["buy", "sell"]


def test_too_many_trades_rejected():
    _, errors = pc.build_trades([], [_trade()] * (pc.MAX_ITEMS + 1))
    assert errors == [f"一次最多 {pc.MAX_ITEMS} 筆"]


# ── build_holdings ───────────────────────────────────────────────────────────


def test_screenshot_rows_become_holdings():
    rows = [
        {"stock": "台積電 2330", "quantity": 2000, "unit": "股", "avg_cost": 598.5},
        {"stock": "0050", "quantity": 1.2, "unit": "張", "avg_cost": 128.3},
    ]
    items, errors = pc.build_holdings([], rows)

    assert errors == []
    assert [(i["ticker"], i["shares"], i["avg_cost"]) for i in items] == [
        ("2330.TW", 2000, 598.5),
        ("0050.TW", 1200, 128.3),
    ]


def test_same_stock_twice_is_rejected():
    rows = [
        {"stock": "台積電", "quantity": 1, "unit": "張", "avg_cost": 600},
        {"stock": "2330", "quantity": 2, "unit": "張", "avg_cost": 600},
    ]
    _, errors = pc.build_holdings([], rows)
    assert errors == ["第 2 檔：台積電 重複出現"]


def test_holding_needs_a_positive_avg_cost():
    _, errors = pc.build_holdings([], [{"stock": "台積電", "quantity": 1, "unit": "張"}])
    assert "均價不是數字" in errors[0]


# ── 待確認清單 ────────────────────────────────────────────────────────────────


def test_trade_summary_shows_shares_lots_costs_and_date():
    items, _ = pc.build_trades(
        [_holding("2330", 3000, 500)],
        [
            _trade(trade_date="2026-10-14"),
            _trade(action="sell", quantity=500, unit="股", price=650),
        ],
    )

    text = pc.summarize(pc.TRADES, items, [], minutes=10)

    assert text.splitlines() == [
        "📝 待確認的持股變更（10 分鐘內有效）",
        "1. 買進 台積電（2330）2,000 股（2 張）× 600 元｜手續費約 1,710 元｜2026-10-14",
        f"2. 賣出 台積電（2330）500 股 × 650 元｜手續費約 463.12 元、證交稅約 975 元"
        f"｜{pc.today_taipei().isoformat()}",
        "回覆「確認」寫入，回覆「取消」放棄。",
    ]


def test_user_given_fee_is_shown_as_is():
    items, _ = pc.build_trades([], [_trade(fee=20)])
    assert "手續費 20 元" in pc.summarize(pc.TRADES, items, [], minutes=10)


def test_holdings_summary_shows_what_changes():
    current = [_holding("台積電", 1000, 550)]
    items, _ = pc.build_holdings(
        current,
        [
            {"stock": "台積電", "quantity": 2, "unit": "張", "avg_cost": 598.5},
            {"stock": "鴻海", "quantity": 500, "unit": "股", "avg_cost": 152},
        ],
    )

    text = pc.summarize(pc.HOLDINGS, items, current, minutes=10)

    assert (
        "1. 台積電（2330）設為 2,000 股（2 張），均價 598.5 元（原本 1,000 股，均價 550 元）"
        in text
    )
    assert "2. 鴻海（2317）新增 500 股，均價 152 元" in text
    assert "沒列在這裡的持股不會變動。" in text


# ── 確認後寫入 ────────────────────────────────────────────────────────────────


@pytest.fixture
def portfolio():
    with patch.object(pc, "portfolio_service") as service:
        service.estimate_costs.return_value = (0.0, 0.0)
        yield service


def test_trade_updates_the_matched_holding(portfolio):
    portfolio.list_holdings.return_value = [_holding("南亞科", 1000, 50, "h-nanya")]
    items, _ = pc.build_trades(
        portfolio.list_holdings.return_value,
        [_trade(stock="南亞科", action="sell", quantity=500, unit="股", price=80)],
    )

    result = pc.apply("uid-1", pc.TRADES, items)

    kwargs = portfolio.add_transaction.call_args.kwargs
    assert portfolio.add_transaction.call_args.args == ("uid-1",)
    assert kwargs["ticker"] == "2408.TW"
    assert kwargs["holding_id"] == "h-nanya"
    assert kwargs["action"] == "sell"
    assert kwargs["shares"] == 500
    assert result.splitlines()[0] == "✅ 已寫入 1 筆"


def test_new_stock_trade_has_no_holding_id(portfolio):
    portfolio.list_holdings.return_value = []
    items, _ = pc.build_trades([], [_trade()])

    pc.apply("uid-1", pc.TRADES, items)

    assert portfolio.add_transaction.call_args.kwargs["holding_id"] is None


def test_holdings_are_updated_or_added(portfolio):
    portfolio.list_holdings.return_value = [_holding("0050", 500, 120, "h-0050")]
    items, _ = pc.build_holdings(
        [],
        [
            {"stock": "0050", "quantity": 1200, "unit": "股", "avg_cost": 128.3},
            {"stock": "鴻海", "quantity": 500, "unit": "股", "avg_cost": 152},
        ],
    )

    result = pc.apply("uid-1", pc.HOLDINGS, items)

    portfolio.update_holding.assert_called_once_with("uid-1", "h-0050", shares=1200, avg_cost=128.3)
    portfolio.add_holding.assert_called_once_with("uid-1", "2317.TW", 500, 152.0, name="鴻海")
    assert "✅ 已寫入 2 筆" in result
    assert "・元大台灣50（0050）設為 1,200 股，均價 128.3 元" in result


def test_one_failure_does_not_stop_the_rest(portfolio):
    portfolio.list_holdings.return_value = []
    portfolio.add_transaction.side_effect = [ValueError("未持有 2317.TW，無法賣出"), MagicMock()]
    items = [
        {**pc.build_trades([], [_trade(stock="鴻海")])[0][0], "action": "sell"},
        pc.build_trades([], [_trade()])[0][0],
    ]

    result = pc.apply("uid-1", pc.TRADES, items)

    assert portfolio.add_transaction.call_count == 2
    assert "✅ 已寫入 1 筆" in result
    assert "⚠️ 有 1 筆沒有寫入" in result
    assert "賣出 鴻海（2317）2,000 股（2 張）× 600 元：未持有 2317.TW，無法賣出" in result


def test_unexpected_error_is_reported_without_details(portfolio):
    portfolio.list_holdings.return_value = []
    portfolio.add_holding.side_effect = RuntimeError("firestore down")
    items, _ = pc.build_holdings(
        [], [{"stock": "鴻海", "quantity": 1, "unit": "張", "avg_cost": 1}]
    )

    result = pc.apply("uid-1", pc.HOLDINGS, items)

    assert "寫入失敗，請稍後再試" in result
    assert "firestore" not in result


def test_today_is_taipei_date():
    assert isinstance(pc.today_taipei(), date)
