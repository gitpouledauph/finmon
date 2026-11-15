import pandas as pd
import pytest

from finmon.analytics import portfolio
from finmon.importers import boursorama
from finmon.parsing import read_csv_auto, stable_ids, to_number


def test_to_number_formats():
    assert to_number("-1 234,56") == -1234.56
    assert to_number("1,234.56") == 1234.56
    assert to_number("12,5 €") == 12.5
    assert to_number("") is None


def _market(days, usd_rates, price_usd):
    prices = pd.DataFrame({"symbol": "X", "date": days.strftime("%Y-%m-%d"), "close": price_usd})
    fx = pd.DataFrame({"currency": "USD", "date": days.strftime("%Y-%m-%d"), "rate": usd_rates})
    inst = pd.DataFrame([{"isin": "US0000000001", "name": "X", "ticker": "X", "currency": "USD",
                          "asset_class": "Actions", "region": "Amérique du Nord", "sector": None,
                          "exposure": '{"USD": 1}', "regions": '{"Amérique du Nord": 1}', "sectors": "{}",
                          "resolved_by": "test"}])
    return prices, fx, inst


def _trades(rows):
    return pd.DataFrame(rows, columns=["id", "account_id", "date", "kind", "isin", "name", "quantity",
                                       "amount", "fees", "taxes", "source"])


EMPTY_SNAP = pd.DataFrame(columns=["account_id", "date", "isin", "name", "quantity", "price", "avg_cost", "value"])


def test_fx_effect_isolated():
    """Prix constant en USD, l'euro monte de 25 % : perte 100 % change."""
    days = pd.date_range("2025-01-01", "2025-01-10")
    rates = [1.0] * 5 + [1.25] * 5
    prices, fx, inst = _market(days, rates, [100.0] * 10)
    tr = _trades([("1", "a", "2025-01-01", "buy", "US0000000001", "X", 10, -1000.0, 0, 0, "t")])
    res = portfolio.build(tr, EMPTY_SNAP, inst, prices, fx, today=days[-1].date())
    last = res.current.iloc[0]
    assert last["value"] == pytest.approx(800.0)
    assert last["fx"] == pytest.approx(-200.0)
    assert last["local"] == pytest.approx(0.0, abs=1e-6)


def test_local_and_fx_split_sums_to_total():
    days = pd.date_range("2025-01-01", "2025-01-10")
    rates = [1.0] * 5 + [1.1] * 5
    prices, fx, inst = _market(days, rates, [100.0] * 5 + [130.0] * 5)
    tr = _trades([("1", "a", "2025-01-01", "buy", "US0000000001", "X", 10, -1000.0, 0, 0, "t")])
    res = portfolio.build(tr, EMPTY_SNAP, inst, prices, fx, today=days[-1].date())
    last = res.current.iloc[0]
    assert last["local"] == pytest.approx(300.0)                 # +30 % sous-jacent
    assert last["fx"] == pytest.approx(1000 * (1 / 1.1 - 1))     # −9,1 % change
    assert last["local"] + last["fx"] + last["cross"] == pytest.approx(last["latent"])


def test_pmp_realized_on_sell():
    days = pd.date_range("2025-01-01", "2025-01-05")
    prices, fx, inst = _market(days, [1.0] * 5, [100, 100, 120, 120, 120])
    tr = _trades([
        ("1", "a", "2025-01-01", "buy", "US0000000001", "X", 10, -1000.0, 0, 0, "t"),
        ("2", "a", "2025-01-03", "sell", "US0000000001", "X", 5, 600.0, 0, 0, "t"),
    ])
    res = portfolio.build(tr, EMPTY_SNAP, inst, prices, fx, today=days[-1].date())
    assert res.realized["realized"].iloc[0] == pytest.approx(100.0)
    assert res.current.iloc[0]["qty"] == pytest.approx(5)
    assert res.current.iloc[0]["cost"] == pytest.approx(500.0)


def test_twr_ignores_flows():
    total = pd.Series([0, 100, 110, 210, 231.0])
    flow = pd.Series([0, 100, 0, 100, 0.0])
    t = portfolio.twr(total, flow)
    assert t.iloc[-1] == pytest.approx(100 * 1.10 * 1.10)


def test_stable_ids_repeat_import():
    df = pd.DataFrame({"a": ["x", "x", "y"], "b": [1, 1, None]})
    ids1 = stable_ids(df, ["a", "b"], "p")
    ids2 = stable_ids(df.copy(), ["a", "b"], "p")
    assert list(ids1) == list(ids2)
    assert ids1.nunique() == 3


def test_boursorama_detection(tmp_path):
    p = tmp_path / "ops.csv"
    p.write_text("dateOp;dateVal;label;category;categoryParent;supplierFound;amount;comment;accountNum;accountLabel;accountbalance\n"
                 "2025-01-02;2025-01-02;CARTE 01/01/25 MONOPRIX;Courses;Alimentation;monoprix;-12,30;;0001;COMPTE;100,00\n",
                 encoding="utf-8")
    assert boursorama.detect(read_csv_auto(p)) == "operations"
