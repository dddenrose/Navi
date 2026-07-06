"""投資組合交易層測試 — 平均成本法、已實現損益、台股費稅計算.

用 in-memory fake Firestore 驗證帳務數學（錢相關計算必須有回歸測試）。
"""

from unittest.mock import patch

import pytest

from services.portfolio_service import (
    TW_MIN_COMMISSION,
    add_transaction,
    estimate_costs,
    get_realized_pnl,
)


# ── In-memory fake Firestore（僅覆蓋本模組用到的 API）─────────────────────────


class FakeDoc:
    def __init__(self, coll, doc_id, data):
        self._coll = coll
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, coll, doc_id):
        self._coll = coll
        self._id = doc_id

    def update(self, patch_data):
        self._coll._docs[self._id].update(patch_data)

    def delete(self):
        self._coll._docs.pop(self._id, None)


class FakeCollection:
    def __init__(self):
        self._docs: dict[str, dict] = {}
        self._next = 0

    def add(self, data):
        self._next += 1
        doc_id = f"doc{self._next}"
        self._docs[doc_id] = dict(data)
        return (None, FakeDoc(self, doc_id, self._docs[doc_id]))

    def stream(self):
        return [FakeDoc(self, k, v) for k, v in list(self._docs.items())]

    def document(self, doc_id):
        return FakeDocRef(self, doc_id)


@pytest.fixture
def fake_store():
    holdings = FakeCollection()
    transactions = FakeCollection()
    with (
        patch("services.portfolio_service._holdings_ref", return_value=holdings),
        patch("services.portfolio_service._transactions_ref", return_value=transactions),
    ):
        yield holdings, transactions


# ── 費稅估算 ──────────────────────────────────────────────────────────────────


class TestEstimateCosts:
    def test_tw_buy_fee_no_tax(self):
        fee, tax = estimate_costs("2330.TW", "buy", 1000, 600)
        assert fee == round(600_000 * 0.001425, 2)
        assert tax == 0.0

    def test_tw_sell_has_tax(self):
        fee, tax = estimate_costs("2330.TW", "sell", 1000, 600)
        assert tax == round(600_000 * 0.003, 2)

    def test_min_commission(self):
        fee, _ = estimate_costs("2330.TW", "buy", 10, 100)  # 1000 元 → 費率僅 1.4 元
        assert fee == TW_MIN_COMMISSION

    def test_us_ticker_free(self):
        assert estimate_costs("AAPL", "sell", 100, 200) == (0.0, 0.0)


# ── 交易 → 持股維護 ───────────────────────────────────────────────────────────


class TestAddTransaction:
    def test_buy_creates_holding_with_fee_in_cost(self, fake_store):
        holdings, _ = fake_store
        add_transaction("u1", "2330.TW", "buy", 1000, 600)
        docs = holdings.stream()
        assert len(docs) == 1
        d = docs[0].to_dict()
        expected_avg = (600_000 + 600_000 * 0.001425) / 1000
        assert d["shares"] == 1000
        assert abs(d["avg_cost"] - expected_avg) < 0.01

    def test_buy_averages_cost(self, fake_store):
        holdings, _ = fake_store
        add_transaction("u1", "2330.TW", "buy", 1000, 500, fee=0)
        add_transaction("u1", "2330.TW", "buy", 1000, 700, fee=0)
        d = holdings.stream()[0].to_dict()
        assert d["shares"] == 2000
        assert abs(d["avg_cost"] - 600.0) < 0.01

    def test_sell_realizes_pnl_net_of_costs(self, fake_store):
        _, _ = fake_store
        add_transaction("u1", "2330.TW", "buy", 1000, 500, fee=0)
        tx = add_transaction("u1", "2330.TW", "sell", 1000, 600)
        gross = 600_000
        fee = round(gross * 0.001425, 2)
        tax = round(gross * 0.003, 2)
        assert tx.realized_pnl == round(gross - fee - tax - 500_000, 2)

    def test_sell_all_deletes_holding(self, fake_store):
        holdings, _ = fake_store
        add_transaction("u1", "2330.TW", "buy", 1000, 500, fee=0)
        add_transaction("u1", "2330.TW", "sell", 1000, 600)
        assert holdings.stream() == []

    def test_partial_sell_keeps_avg_cost(self, fake_store):
        holdings, _ = fake_store
        add_transaction("u1", "2330.TW", "buy", 2000, 500, fee=0)
        add_transaction("u1", "2330.TW", "sell", 500, 600)
        d = holdings.stream()[0].to_dict()
        assert d["shares"] == 1500
        assert abs(d["avg_cost"] - 500.0) < 0.01

    def test_oversell_rejected(self, fake_store):
        add_transaction("u1", "2330.TW", "buy", 100, 500, fee=0)
        with pytest.raises(ValueError, match="超過持有股數"):
            add_transaction("u1", "2330.TW", "sell", 200, 600)

    def test_sell_without_holding_rejected(self, fake_store):
        with pytest.raises(ValueError, match="未持有"):
            add_transaction("u1", "2330.TW", "sell", 100, 600)

    def test_realized_pnl_accumulates(self, fake_store):
        add_transaction("u1", "2330.TW", "buy", 1000, 500, fee=0)
        add_transaction("u1", "2330.TW", "sell", 500, 600, fee=0)
        add_transaction("u1", "2330.TW", "sell", 500, 400, fee=0)
        # 兩筆賣出：+ (300000*0.997-250000) 與 (200000*0.997-250000)
        expected = round(300_000 * 0.997 - 250_000, 2) + round(200_000 * 0.997 - 250_000, 2)
        assert abs(get_realized_pnl("u1") - round(expected, 2)) < 0.01

    def test_invalid_action_rejected(self, fake_store):
        with pytest.raises(ValueError, match="buy 或 sell"):
            add_transaction("u1", "2330.TW", "hold", 100, 500)
