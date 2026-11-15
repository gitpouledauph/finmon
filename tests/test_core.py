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


# ---------------------------------------------------------------- imports historiques
from finmon.db import DB  # noqa: E402
from finmon.importers import binance, ibkr  # noqa: E402
from finmon import manual  # noqa: E402


def _db_with_market(tmp_path):
    db = DB(tmp_path / "t.db")
    days = pd.date_range("2024-01-01", "2024-12-31").strftime("%Y-%m-%d")
    db.upsert("prices", pd.DataFrame({"symbol": "BTC-USD", "date": days, "close": 50000.0}))
    db.upsert("prices", pd.DataFrame({"symbol": "ETH-USD", "date": days, "close": 2500.0}))
    db.upsert("fx_rates", pd.DataFrame({"currency": "USD", "date": days, "rate": 1.25}))
    return db


def test_binance_ledger(tmp_path):
    db = _db_with_market(tmp_path)
    df = pd.DataFrame([
        ["1", "2024-02-01 10:00:00", "Spot", "Deposit", "EUR", "1000"],
        ["1", "2024-02-02 10:00:00", "Spot", "Buy", "BTC", "0.02"],
        ["1", "2024-02-02 10:00:00", "Spot", "Buy", "EUR", "-800"],
        ["1", "2024-02-02 10:00:00", "Spot", "Transaction Fee", "BTC", "-0.00002"],
        ["1", "2024-03-01 10:00:00", "Earn", "Simple Earn Flexible Interest", "BTC", "0.0001"],
        ["1", "2024-03-02 10:00:00", "Spot", "Simple Earn Flexible Subscription", "BTC", "-0.01"],
        ["1", "2024-04-01 10:00:00", "Spot", "Binance Convert", "BTC", "-0.005"],
        ["1", "2024-04-01 10:00:00", "Spot", "Binance Convert", "ETH", "0.1"],
    ], columns=["User_ID", "UTC_Time", "Account", "Operation", "Coin", "Change"])
    n, warn = binance.import_ledger(db, df, online=False)
    assert n == 6  # dépôt, achat, frais, intérêt, conversion (vente + achat) ; souscription Earn ignorée
    buy = db.read("SELECT * FROM trades WHERE kind='buy' AND isin='CRYPTO-BTC'")
    assert buy["amount"].iloc[0] == pytest.approx(-800)
    conv = db.read("SELECT * FROM trades WHERE kind='buy' AND isin='CRYPTO-ETH'")
    assert conv["amount"].iloc[0] == pytest.approx(-0.1 * 2500 / 1.25)   # valeur EUR de l'ETH reçu
    assert db.read("SELECT COUNT(*) n FROM trades WHERE kind='reward'")["n"][0] == 1


IBKR_SAMPLE = """Statement,Header,Field Name,Field Value
Statement,Data,Period,"January 1, 2024 - December 31, 2024"
Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code
Trades,Data,Order,Stocks,USD,AAPL,"2024-03-01, 10:15:22",10,180,181,-1800,-1,1801,0,0,O
Trades,Data,Order,Forex,EUR,EUR.USD,"2024-03-01, 10:00:00",-1000,1.25,1.25,1250,-2,0,0,0,
Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount
Deposits & Withdrawals,Data,EUR,2024-02-28,Electronic Fund Transfer,5000
Deposits & Withdrawals,Data,Total,,,5000
Dividends,Header,Currency,Date,Description,Amount
Dividends,Data,USD,2024-05-16,AAPL(US0378331005) Cash Dividend USD 0.25 per Share,2.5
Financial Instrument Information,Header,Asset Category,Symbol,Description,Conid,Security ID,Underlying,Listing Exch,Multiplier,Type,Code
Financial Instrument Information,Data,Stocks,AAPL,APPLE INC,265598,US0378331005,AAPL,NASDAQ,1,COMMON,
"""


def test_ibkr_statement(tmp_path):
    db = _db_with_market(tmp_path)
    assert ibkr.detect_text(IBKR_SAMPLE)
    n, warn = ibkr.import_statement(db, IBKR_SAMPLE, online=False)
    assert n == 3
    buy = db.read("SELECT * FROM trades WHERE kind='buy'").iloc[0]
    assert buy["isin"] == "US0378331005"
    assert buy["amount"] == pytest.approx(-1801 / 1.25)
    div = db.read("SELECT amount FROM trades WHERE kind='dividend'")["amount"].iloc[0]
    assert div == pytest.approx(2.0)


def test_manual_buy_in_usd(tmp_path):
    db = _db_with_market(tmp_path)
    acc = manual.ensure_account(db, "Mon CTO", "cto")
    from datetime import date

    row = manual.add_operation(db, account_id=acc, kind="buy", d=date(2024, 6, 3), ticker="AAPL",
                               isin="US0378331005", name="Apple", quantity=2, price=200, currency="USD",
                               fees=1.25, online=False, fund_with_deposit=True)
    assert row["amount"] == pytest.approx(-(400 + 1.25) / 1.25)
    assert db.read("SELECT COUNT(*) n FROM trades WHERE kind='deposit'")["n"][0] == 1
    assert manual.ensure_account(db, "mon cto") == acc


# ---------------------------------------------------------------- formats réels (anonymisés)
from pathlib import Path  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def test_ibkr_french_statement(tmp_path):
    db = _db_with_market(tmp_path)
    text = (FIX / "ibkr_activity_fr.csv").read_text(encoding="utf-8")
    assert ibkr.detect_text(text)
    n, warn = ibkr.import_statement(db, text, online=False)
    assert n == 1
    dep = db.read("SELECT kind, amount, date FROM trades").iloc[0]
    assert (dep["kind"], dep["amount"], dep["date"]) == ("deposit", 100.0, "2025-03-14")


def test_binance_spot_trades_french(tmp_path):
    db = _db_with_market(tmp_path)
    days = pd.date_range("2025-01-01", "2026-12-31").strftime("%Y-%m-%d")
    db.upsert("fx_rates", pd.DataFrame({"currency": "USD", "date": days, "rate": 1.25}), mode="replace")
    db.upsert("prices", pd.DataFrame({"symbol": "BTC-USD", "date": days, "close": 80000.0}), mode="replace")
    db.upsert("prices", pd.DataFrame({"symbol": "ETH-USD", "date": days, "close": 2500.0}), mode="replace")
    df = read_csv_auto(FIX / "binance_spot_trades_fr.csv")
    assert binance.detect(df) and binance.detect_spot(df)
    led = binance.spot_to_ledger(df)
    n, warn = binance.import_ledger(db, led, online=False)
    t = db.read("SELECT date, kind, isin, quantity, amount FROM trades ORDER BY date, kind")
    btc_eur = t[(t["date"] == "2026-02-06") & (t["kind"] == "buy")]
    assert btc_eur["quantity"].iloc[0] == pytest.approx(0.00100 + 0.00800)          # 2 exécutions, 1 ordre
    assert btc_eur["amount"].iloc[0] == pytest.approx(-(60.00 + 480.00))   # montant EUR exact
    eth_usdc = t[(t["isin"] == "CRYPTO-ETH") & (t["kind"] == "buy")]
    assert eth_usdc["amount"].iloc[0] == pytest.approx(-1000.00 / 1.25)          # USDC = liquidités en USD
    sell = t[(t["kind"] == "sell") & (t["date"] == "2026-01-19")]
    assert sell["amount"].iloc[0] == pytest.approx(1350.00 / 1.25)
    assert db.read("SELECT COUNT(*) n FROM trades WHERE isin = 'CRYPTO-USDC'")["n"][0] == 0


def test_ibkr_french_2026_trades_and_exchanges(tmp_path):
    db = _db_with_market(tmp_path)
    days = pd.date_range("2026-01-01", "2026-12-31").strftime("%Y-%m-%d")
    db.upsert("fx_rates", pd.DataFrame({"currency": "USD", "date": days, "rate": 1.25}), mode="replace")
    text = (FIX / "ibkr_activity_fr_2026.csv").read_text(encoding="utf-8")
    n, warn = ibkr.import_statement(db, text, online=False)
    t = db.read("SELECT kind, isin, quantity, amount FROM trades ORDER BY date, kind").set_index(["kind", "isin"])
    assert n == 5  # 2 achats, 1 versement, 1 intérêt, 1 retenue — pas de ligne Forex
    assert t.loc[("buy", "IE00BYZK4552"), "amount"] == pytest.approx(-185.0)
    assert t.loc[("buy", "US02079K3059"), "amount"] == pytest.approx(-701 / 1.25)
    inst = db.read("SELECT isin, ticker FROM instruments").set_index("isin")["ticker"]
    assert inst["IE00BYZK4552"] == "RBOT.MI" and inst["US02079K3059"] == "GOOGL"   # bourse d'achat
    snap = db.read("SELECT isin, quantity, date FROM position_snapshots")
    assert set(snap["date"]) == {"2026-11-13"} and len(snap) == 2


def test_ibkr_exchange_to_yahoo():
    assert ibkr.yahoo_ticker("RBOT", "BVME.ETF") == "RBOT.MI"
    assert ibkr.yahoo_ticker("JEDG", "LSEETF") == "JEDG.L"
    assert ibkr.yahoo_ticker("BRK B", "NYSE") == "BRK-B"
    assert ibkr.yahoo_ticker("MC", "SBF") == "MC.PA"
    assert ibkr.yahoo_ticker("XYZ", "INCONNUE") is None


def test_boursorama_positions_comptables(tmp_path):
    db = DB(tmp_path / "t.db")
    p = FIX / "boursorama_export-positions-comptables-01-02-2026_10-00-00.csv"
    df = read_csv_auto(p)
    assert boursorama.detect(df) == "positions"
    n = boursorama.import_positions(db, df, source=p.name, account_hint="pea")
    s = db.read("SELECT * FROM position_snapshots").set_index("isin")
    assert n == 3 and set(s["account_id"]) == {"bourso:pea"} and set(s["date"]) == {"2026-02-01"}
    assert s.loc["FR001400AEE3", "quantity"] == pytest.approx(2.5)
    assert s.loc["FR0011871128", "avg_cost"] == pytest.approx(45.0)
    assert s.loc["FR0011871128", "value"] == pytest.approx(500.0)


def test_save_holdings_crypto_full_statement(tmp_path):
    from datetime import date as _d

    db = _db_with_market(tmp_path)
    db.upsert("accounts", pd.DataFrame([{"id": "binance", "institution": "Binance", "name": "Binance",
                                         "type": "crypto", "currency": "EUR"}]))
    lines = pd.DataFrame({"ticker": ["BTC", "SOL", "ETH"], "isin": ["", "", ""], "name": ["", "", ""],
                          "quantity": [0.19, 4.5, None]})
    n = manual.save_holdings(db, "binance", _d(2026, 11, 15), lines, crypto=True, online=False)
    s = db.read("SELECT isin, quantity FROM position_snapshots").set_index("isin")["quantity"]
    assert n == 2 and s["CRYPTO-SOL"] == 4.5 and "CRYPTO-ETH" not in s   # quantité vide = ligne sortie
    assert db.read("SELECT ticker FROM instruments WHERE isin='CRYPTO-SOL'")["ticker"][0] == "SOL-USD"
    # Ré-enregistrer le même jour remplace le relevé.
    manual.save_holdings(db, "binance", _d(2026, 11, 15), lines.iloc[:1], crypto=True, online=False)
    assert len(db.read("SELECT * FROM position_snapshots")) == 1
