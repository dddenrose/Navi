"""twse_parsers 欄位對應測試 — fixture 取自 2026-07-02 TWSE 實際 API 回應.

這些測試鎖定 T86 / MI_MARGN 的欄位順序。若 TWSE 改版導致欄數改變，
parser 會 raise ValueError（寧可失敗也不錯位），此處同時驗證該行為。
"""

import pytest

from services.twse_parsers import (
    parse_int,
    parse_margn_row,
    parse_t86_row,
    shares_to_lots,
)

# 2026-07-02 T86 selectType=ALL 的 2330 實際回應列（19 欄）
T86_2330 = [
    "2330", "台積電          ",
    "16,678,234", "28,931,760", "-12,253,526",   # 外陸資 買/賣/淨（不含外資自營商）
    "0", "0", "0",                                # 外資自營商 買/賣/淨
    "1,229,949", "204,100", "1,025,849",          # 投信 買/賣/淨
    "216,739",                                    # 自營商買賣超（合計）
    "195,700", "90,000", "105,700",               # 自營商自行 買/賣/淨
    "346,041", "235,002", "111,039",              # 自營商避險 買/賣/淨
    "-11,010,938",                                # 三大法人合計
]

# 2026-07-02 MI_MARGN tables[1] 的 2330 實際回應列（16 欄）
MARGN_2330 = [
    "2330", "台積電",
    "1,552", "460", "12", "32,433", "33,513", "6,483,092",  # 融資
    "10", "6", "0", "67", "63", "6,483,092",                # 融券
    "2", " ",                                               # 資券互抵 / 註記
]


class TestParseT86Row:
    def test_foreign_includes_foreign_dealer(self):
        parsed = parse_t86_row(T86_2330)
        assert parsed.code == "2330"
        assert parsed.foreign_buy == 16_678_234
        assert parsed.foreign_sell == 28_931_760
        assert parsed.foreign_net == -12_253_526

    def test_trust_maps_to_columns_8_to_10(self):
        """投信是 row[8:11]，不是舊版誤用的 row[5:8]（那是外資自營商）。"""
        parsed = parse_t86_row(T86_2330)
        assert parsed.trust_buy == 1_229_949
        assert parsed.trust_sell == 204_100
        assert parsed.trust_net == 1_025_849

    def test_dealer_combines_proprietary_and_hedge(self):
        """自營商淨額取合計欄 row[11]，買賣為自行+避險。"""
        parsed = parse_t86_row(T86_2330)
        assert parsed.dealer_net == 216_739
        assert parsed.dealer_buy == 195_700 + 346_041
        assert parsed.dealer_sell == 90_000 + 235_002

    def test_total_is_column_18_and_internally_consistent(self):
        parsed = parse_t86_row(T86_2330)
        assert parsed.total_net == -11_010_938
        assert (
            parsed.foreign_net + parsed.trust_net + parsed.dealer_net
            == parsed.total_net
        )

    def test_short_row_raises(self):
        """舊版 12 欄 schema 應該直接失敗，而不是靜默錯位。"""
        with pytest.raises(ValueError, match="columns"):
            parse_t86_row(T86_2330[:12])


class TestParseMargnRow:
    def test_margin_fields(self):
        parsed = parse_margn_row(MARGN_2330)
        assert parsed.code == "2330"
        assert parsed.margin_buy == 1_552
        assert parsed.margin_sell == 460
        assert parsed.margin_cash_repay == 12
        assert parsed.margin_prev_balance == 32_433
        assert parsed.margin_balance == 33_513
        assert parsed.margin_limit == 6_483_092
        # 帳務自洽：前餘 + 買 - 賣 - 現償 = 今餘
        assert (
            parsed.margin_prev_balance
            + parsed.margin_buy
            - parsed.margin_sell
            - parsed.margin_cash_repay
            == parsed.margin_balance
        )

    def test_short_buy_sell_not_swapped(self):
        """row[8]=融券買進、row[9]=融券賣出（舊版把兩者對調）。

        以帳務自洽驗證方向：融券餘額 前餘 - 買(回補) + 賣(新增) - 現券償還 = 今餘。
        """
        parsed = parse_margn_row(MARGN_2330)
        assert parsed.short_buy == 10
        assert parsed.short_sell == 6
        assert (
            parsed.short_prev_balance
            - parsed.short_buy
            + parsed.short_sell
            - parsed.short_repay
            == parsed.short_balance
        )

    def test_short_balance_is_today_not_yesterday(self):
        """融券餘額取 row[12]（今日），不是舊版 chips_data 誤用的 row[11]（前日）。"""
        parsed = parse_margn_row(MARGN_2330)
        assert parsed.short_balance == 63
        assert parsed.short_prev_balance == 67

    def test_offset_is_column_14(self):
        """資券互抵是 row[14]，不是舊版誤用的 row[13]（融券限額）。"""
        parsed = parse_margn_row(MARGN_2330)
        assert parsed.offset == 2
        assert parsed.short_limit == 6_483_092

    def test_short_row_raises(self):
        with pytest.raises(ValueError, match="columns"):
            parse_margn_row(MARGN_2330[:13])


class TestHelpers:
    def test_parse_int_handles_twse_formats(self):
        assert parse_int("1,234") == 1234
        assert parse_int("--") == 0
        assert parse_int("") == 0
        assert parse_int(None) == 0

    def test_shares_to_lots_truncates_toward_zero(self):
        assert shares_to_lots(1_500) == 1
        assert shares_to_lots(-500) == 0  # floor division 會變 -1，這裡必須朝零截斷
        assert shares_to_lots(-1_500) == -1
