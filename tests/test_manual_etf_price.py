import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from astock.domain import Quote, dec, now_cn
from astock.window import MainWindow


@pytest.mark.parametrize("symbol,tick", [("158000.SZ", ".001"), ("159915.SZ", ".001"),
                                       ("551300.SH", ".001"), ("600000.SH", ".01")])
@pytest.mark.parametrize("side", [0, 1])
def test_opposite_price_uses_instrument_tick_for_new_etf_codes(qtbot, tmp_path, symbol, tick, side):
    window = MainWindow(tmp_path, start_workers=False)
    qtbot.addWidget(window)
    at = now_cn()
    window.quotes[symbol] = Quote(symbol, at, at, dec("1.234"), bid=dec("1.233"), ask=dec("1.235"))
    window.manual_symbol.setText(symbol)
    window.manual_side.setCurrentIndex(side)
    window.slippage.setValue(2)
    window.use_opposite_price()
    expected = dec("1.235") + dec(tick) * 2 if side == 0 else dec("1.233") - dec(tick) * 2
    assert window.manual_price.value() == pytest.approx(float(expected))
    window.close()
