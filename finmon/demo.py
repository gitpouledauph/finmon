"""Génère un profil de démonstration complet, sans réseau.

Les fichiers sont écrits aux formats réels (export Boursorama, pytr) puis
importés par les vrais importeurs : la démo teste donc toute la chaîne.
"""
from __future__ import annotations

import shutil
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import get_profile
from .db import DB
from .sync import import_inbox

START = date(2024, 11, 1)

INSTRUMENTS = [
    # isin, nom, ticker, devise de cotation, prix initial, drift, vol, exposition, régions, classe
    ("IE00B4L5Y983", "iShares Core MSCI World", "DEMO-IWDA", "USD", 98.0, 0.10, 0.15,
     '{"USD": 0.72, "EUR": 0.08, "JPY": 0.05, "GBP": 0.035, "CAD": 0.03, "CHF": 0.025, "AUD": 0.02, "AUTRE": 0.04}',
     '{"Amérique du Nord": 0.75, "Europe": 0.15, "Japon": 0.05, "Asie-Pacifique": 0.05}', "Actions",
     '{"Technologie": 0.26, "Finance": 0.16, "Santé": 0.11, "Industrie": 0.11, "Conso. cyclique": 0.10, "Communication": 0.08, "Conso. de base": 0.06, "Énergie": 0.04, "Matériaux": 0.04, "Services publics": 0.03, "Immobilier": 0.01}'),
    ("IE00B5BMR087", "iShares Core S&P 500", "DEMO-CSPX", "USD", 560.0, 0.12, 0.16,
     '{"USD": 1.0}', '{"Amérique du Nord": 1.0}', "Actions",
     '{"Technologie": 0.32, "Finance": 0.13, "Santé": 0.10, "Conso. cyclique": 0.10, "Communication": 0.09, "Industrie": 0.08, "Conso. de base": 0.06, "Énergie": 0.04, "Autres": 0.08}'),
    ("US0378331005", "Apple Inc.", "DEMO-AAPL", "USD", 225.0, 0.08, 0.27,
     '{"USD": 1.0}', '{"Amérique du Nord": 1.0}', "Actions", '{"Technologie": 1.0}'),
    ("LU1681043599", "Amundi MSCI World (PEA)", "DEMO-CW8", "EUR", 520.0, 0.10, 0.15,
     '{"USD": 0.72, "EUR": 0.08, "JPY": 0.05, "GBP": 0.035, "CAD": 0.03, "CHF": 0.025, "AUD": 0.02, "AUTRE": 0.04}',
     '{"Amérique du Nord": 0.75, "Europe": 0.15, "Japon": 0.05, "Asie-Pacifique": 0.05}', "Actions",
     '{"Technologie": 0.26, "Finance": 0.16, "Santé": 0.11, "Industrie": 0.11, "Conso. cyclique": 0.10, "Communication": 0.08, "Conso. de base": 0.06, "Énergie": 0.04, "Matériaux": 0.04, "Services publics": 0.03, "Immobilier": 0.01}'),
    ("FR0000120271", "TotalEnergies", "DEMO-TTE", "EUR", 55.0, 0.02, 0.22,
     '{"EUR": 1.0}', '{"Europe": 1.0}', "Actions", '{"Énergie": 1.0}'),
    ("FR0000120073", "Air Liquide", "DEMO-AI", "EUR", 165.0, 0.07, 0.18,
     '{"EUR": 1.0}', '{"Europe": 1.0}', "Actions", '{"Matériaux": 1.0}'),
    ("US5949181045", "Microsoft", "DEMO-MSFT", "USD", 415.0, 0.10, 0.24,
     '{"USD": 1.0}', '{"Amérique du Nord": 1.0}', "Actions", '{"Technologie": 1.0}'),
]
CRYPTO = {"BTC": (90000.0, 0.25, 0.55), "ETH": (3400.0, 0.15, 0.70), "BNB": (650.0, 0.1, 0.5)}

FX = {"USD": (1.08, 1.165, 0.07), "JPY": (163.0, 172.0, 0.09), "GBP": (0.835, 0.865, 0.05),
      "CAD": (1.49, 1.61, 0.06), "CHF": (0.94, 0.93, 0.05), "AUD": (1.65, 1.78, 0.08)}


def _path(rng, n, start, drift, vol, end=None):
    dt = 1 / 365
    z = rng.standard_normal(n)
    logp = np.cumsum((drift - 0.5 * vol**2) * dt + vol * np.sqrt(dt) * z)
    p = start * np.exp(logp)
    if end is not None:  # pont : arrive sur la valeur cible
        p = p * np.linspace(1, end / p[-1], n)
    return p


def build(today: date | None = None) -> str:
    today = today or date.today()
    profile = get_profile("demo")
    shutil.rmtree(profile.data_dir, ignore_errors=True)
    profile = get_profile("demo")
    rng = np.random.default_rng(42)
    days = pd.date_range(START, today, freq="D")
    n = len(days)

    fx = {c: pd.Series(_path(rng, n, a, 0, v, end=b), index=days) for c, (a, b, v) in FX.items()}
    px = {}
    for isin, name, tick, ccy, p0, mu, vol, *_ in INSTRUMENTS:
        px[tick] = pd.Series(_path(rng, n, p0, mu, vol), index=days)
    bench = px["DEMO-IWDA"] / fx["USD"] * 0.95  # IWDA.AS : même indice, coté en EUR

    def eur(tick, ccy, d):
        p = px[tick][d]
        return p / fx[ccy][d] if ccy != "EUR" else p

    # ------------------------------------------------------------------
    # Compte courant + Livret A Boursorama (format export « Mes comptes »)
    # ------------------------------------------------------------------
    ops = []
    LIV = []

    def fmt(x):
        return f"{x:.2f}".replace(".", ",")

    def op(d, label, amount, cat="", parent="", supplier=""):
        ops.append([d, label, cat, parent, supplier, amount])

    months = pd.period_range(START, today, freq="M")
    trips = [  # (début, fin, devise, lieux)
        (date(2025, 4, 18), date(2025, 4, 27), "JPY", ["7-ELEVEN TOKYO", "JR EAST", "ICHIRAN SHIBUYA", "HOTEL GRACERY", "DON QUIJOTE", "SUSHI ZANMAI"]),
        (date(2025, 8, 2), date(2025, 8, 16), None, ["RESTAURANT O POTE LISBOA", "PINGO DOCE", "HOTEL LISBOA", "UBER LISBOA", "PASTEIS DE BELEM"]),
        (date(2026, 7, 10), date(2026, 7, 24), "USD", ["WHOLE FOODS NYC", "MTA NYC", "SHAKE SHACK", "MARRIOTT NYC", "UBER *TRIP NYC", "MOMA NEW YORK"]),
    ]
    for m in months:
        y, mo = m.year, m.month
        def d_(day):
            dd = date(y, mo, min(day, 28))
            return dd if dd <= today else None
        if d_(27): op(d_(27), "VIR SEPA RECU /DE ACME SAS /MOTIF SALAIRE", 3800.0 + (1800 if mo == 12 else 0), "Salaires", "Revenus")
        if d_(2): op(d_(2), "PRLV SEPA FONCIA LOYER", -980.0, "Loyer", "Logement")
        if d_(5): op(d_(5), "PRLV SEPA EDF CLIENTS PARTICULIERS", -round(rng.uniform(45, 95), 2), "Électricité, gaz", "Logement")
        if d_(8): op(d_(8), "PRLV SEPA FREE MOBILE", -19.99, "Téléphonie", "Abonnements")
        if d_(11): op(d_(11), "CARTE " + f"{d_(11):%d/%m/%y}" + " NETFLIX.COM CB*1234", -13.49, "Multimédia", "Loisirs et sorties")
        if d_(12): op(d_(12), "CARTE " + f"{d_(12):%d/%m/%y}" + " SPOTIFY CB*1234", -11.12, "Multimédia", "Loisirs et sorties")
        if d_(3): op(d_(3), "PRLV SEPA ALAN SA", -28.0, "Mutuelle", "Santé")
        if d_(15): op(d_(15), "CARTE " + f"{d_(15):%d/%m/%y}" + " NAVIGO IDF MOBILITES", -88.80, "Transports en commun", "Transports")
        if d_(28):
            op(d_(28), "VIR VERS LIVRET A", -300.0, "Virements internes", "Mouvements internes")
            LIV.append([d_(28), "VIR DEPUIS COMPTE COURANT", 300.0])
            op(d_(28), "VIR SEPA TRADE REPUBLIC BANK", -700.0, "Virements émis", "Mouvements internes")
        if mo == 1 and d_(1):
            LIV.append([d_(1), "INTERETS CREDITEURS", round(2.4 / 100 * 300 * 12 * (y - 2024), 2)])
        if mo == 10 and d_(15): op(d_(15), "PRLV SEPA DGFIP IMPOT", -410.0, "Impôts", "Impôts et taxes")
        # dépenses courantes
        for _ in range(rng.integers(6, 10)):
            dd = d_(int(rng.integers(1, 29)))
            if dd is None: continue
            shop = rng.choice(["CARREFOUR CITY", "MONOPRIX", "FRANPRIX", "PICARD", "BIOCOOP", "LIDL"])
            op(dd, f"CARTE {dd:%d/%m/%y} {shop} CB*1234", -round(rng.uniform(12, 85), 2), "Alimentation", "Alimentation")
        for _ in range(rng.integers(3, 7)):
            dd = d_(int(rng.integers(1, 29)))
            if dd is None: continue
            r = rng.choice(["LE PETIT CAFE", "BISTROT PAUL", "PIZZERIA BELLA", "UBER EATS", "SUSHI SHOP", "BAR LE PERCHOIR"])
            op(dd, f"CARTE {dd:%d/%m/%y} {r} CB*1234", -round(rng.uniform(14, 70), 2), "Restaurants, bars", "Loisirs et sorties")
        for _ in range(rng.integers(1, 4)):
            dd = d_(int(rng.integers(1, 29)))
            if dd is None: continue
            s = rng.choice(["AMAZON EU SARL", "FNAC", "DECATHLON", "ZARA", "UNIQLO", "IKEA"])
            op(dd, f"CARTE {dd:%d/%m/%y} {s} CB*1234", -round(rng.uniform(15, 160), 2), "Shopping", "Achats et shopping")
        if rng.random() < 0.6 and d_(20):
            op(d_(20), f"CARTE {d_(20):%d/%m/%y} UGC CINE CITE", -12.9, "Cinéma", "Loisirs et sorties")
        if rng.random() < 0.5 and d_(18):
            op(d_(18), f"CARTE {d_(18):%d/%m/%y} PHARMACIE DU MARCHE", -round(rng.uniform(8, 40), 2), "Pharmacie", "Santé")
        if rng.random() < 0.4 and d_(22):
            op(d_(22), f"CARTE {d_(22):%d/%m/%y} UBER *TRIP", -round(rng.uniform(9, 30), 2), "Taxi", "Transports")
        if rng.random() < 0.2 and d_(9):
            op(d_(9), "RETRAIT DAB 0123 PARIS", -60.0, "Retraits", "Retraits d'espèces")
        if rng.random() < 0.15 and d_(14):
            op(d_(14), f"CARTE {d_(14):%d/%m/%y} BOUTIQUE CADEAUX", -round(rng.uniform(20, 90), 2), "", "")
    for start, end, ccy, places in trips:
        if start > today: continue
        bk = start - timedelta(days=45)
        op(bk, f"CARTE {bk:%d/%m/%y} AIR FRANCE CB*1234", -round(rng.uniform(480, 950), 2), "Avion", "Voyages")
        d = start
        while d <= min(end, today):
            for _ in range(rng.integers(2, 5)):
                pl = rng.choice(places)
                amt = round(rng.uniform(8, 120), 2)
                if ccy:
                    rate = fx[ccy][pd.Timestamp(d)]
                    loc = amt * rate
                    op(d, f"CARTE {d:%d/%m/%y} {pl} {fmt(loc)} {ccy} 1 EURO = {rate:.6f} {ccy}", -amt, "", "Voyages")
                    if rng.random() < 0.3:
                        op(d, f"COMMISSION PAIEMENT HORS ZONE EURO {pl}", -round(amt * 0.0194, 2), "Frais bancaires", "Banque")
                else:
                    op(d, f"CARTE {d:%d/%m/%y} {pl} CB*1234", -amt, "", "Voyages")
            d += timedelta(days=1)

    cc = pd.DataFrame(ops, columns=["dateOp", "label", "category", "categoryParent", "supplierFound", "amount"])
    cc = cc.sort_values("dateOp", ascending=False)
    bal_cc = 4200.0 + cc["amount"].sum()
    lv = pd.DataFrame(LIV, columns=["dateOp", "label", "amount"]).sort_values("dateOp", ascending=False)
    bal_lv = 8000.0 + lv["amount"].sum()

    def write_bourso(df, num, alabel, bal, path):
        out = pd.DataFrame({
            "dateOp": pd.to_datetime(df["dateOp"]).dt.strftime("%Y-%m-%d"),
            "dateVal": pd.to_datetime(df["dateOp"]).dt.strftime("%Y-%m-%d"),
            "label": df["label"], "category": df.get("category", ""), "categoryParent": df.get("categoryParent", ""),
            "supplierFound": df.get("supplierFound", ""), "amount": df["amount"].map(fmt), "comment": "",
            "accountNum": num, "accountLabel": alabel, "accountbalance": fmt(bal)})
        out.to_csv(path, sep=";", index=False, encoding="utf-8-sig")

    inbox = profile.inbox
    write_bourso(cc, "00040111111", "BOURSORAMA BANQUE - COMPTE COURANT", bal_cc, inbox / "boursorama" / "export-operations-courant.csv")
    write_bourso(lv, "00040222222", "LIVRET A", bal_lv, inbox / "boursorama" / "export-operations-livret.csv")

    # ------------------------------------------------------------------
    # Trade Republic (format pytr export_transactions --lang en)
    # ------------------------------------------------------------------
    tr_rows = []
    qty = {}
    for m in months:
        d = date(m.year, m.month, 1)
        if d > today: break
        dep = date(m.year, m.month, 1)
        if dep <= today:
            tr_rows.append([dep, "Deposit", 700.0, "Virement entrant", "", "", "", ""])
        for isin, tick, ccy, amt in (("IE00B4L5Y983", "DEMO-IWDA", "USD", 300.0), ("IE00B5BMR087", "DEMO-CSPX", "USD", 150.0)):
            dd = date(m.year, m.month, 2)
            if dd > today: continue
            p = eur(tick, ccy, pd.Timestamp(dd))
            q = round(amt / p, 6)
            qty[isin] = qty.get(isin, 0) + q
            tr_rows.append([dd, "Buy", -round(q * p, 2), "Savings plan", isin, q, "", ""])
        if m.month in (2, 5, 8, 11) and date(m.year, m.month, 15) <= today and qty.get("US0378331005"):
            tr_rows.append([date(m.year, m.month, 15), "Dividend", round(qty["US0378331005"] * 0.25 / fx["USD"][pd.Timestamp(date(m.year, m.month, 15))] * 0.85, 2),
                            "Apple Inc.", "US0378331005", qty["US0378331005"], "", ""])
        di = date(m.year, m.month, 1)
        tr_rows.append([di, "Interest", round(rng.uniform(2, 9), 2), "Interest", "", "", "", ""])
    for dd, q in ((date(2024, 12, 10), 8), (date(2025, 4, 9), 6), (date(2025, 9, 18), 4)):
        p = eur("DEMO-AAPL", "USD", pd.Timestamp(dd))
        qty["US0378331005"] = qty.get("US0378331005", 0) + q
        tr_rows.append([dd, "Buy", -round(q * p + 1, 2), "Apple Inc.", "US0378331005", q, -1.0, ""])
    sd = date(2026, 3, 12)
    p = eur("DEMO-AAPL", "USD", pd.Timestamp(sd))
    qty["US0378331005"] -= 5
    tr_rows.append([sd, "Sell", round(5 * p - 1, 2), "Apple Inc.", "US0378331005", 5, -1.0, ""])
    for dd, merch, amt in ((date(2026, 2, 7), "PAUL BOULANGERIE", -6.4), (date(2026, 5, 3), "MONOPRIX", -23.1)):
        tr_rows.append([dd, "Removal", amt, f"Card Payment - {merch}", "", "", "", ""])
    tr = pd.DataFrame(tr_rows, columns=["Date", "Type", "Value", "Note", "ISIN", "Shares", "Fees", "Taxes"]).sort_values("Date")
    tr["Date"] = pd.to_datetime(tr["Date"]).dt.strftime("%Y-%m-%dT10:00:00")
    tr["ISIN2"], tr["Shares2"] = "", ""
    tr.to_csv(inbox / "traderepublic" / "account_transactions.csv", sep=";", index=False)
    last = pd.Timestamp(today)
    pf = pd.DataFrame([{"Name": nm, "ISIN": isin, "quantity": round(qty[isin], 6),
                        "price": round(eur(t, c, last), 4), "avgCost": "", "netValue": round(qty[isin] * eur(t, c, last), 2)}
                       for isin, nm, t, c, *_ in INSTRUMENTS if isin in qty])
    pf.to_csv(inbox / "traderepublic" / "portfolio.csv", sep=";", index=False)

    # ------------------------------------------------------------------
    # PEA Boursorama : mouvements + photo des positions
    # ------------------------------------------------------------------
    mv = []
    pea_q = {}
    for dd, isin, tick, nm, q in ((date(2024, 11, 20), "LU1681043599", "DEMO-CW8", "AMUNDI MSCI WORLD UCITS ETF", 6),
                                  (date(2025, 1, 15), "FR0000120271", "DEMO-TTE", "TOTALENERGIES", 40),
                                  (date(2025, 3, 3), "FR0000120073", "DEMO-AI", "AIR LIQUIDE", 12),
                                  (date(2025, 6, 10), "LU1681043599", "DEMO-CW8", "AMUNDI MSCI WORLD UCITS ETF", 5),
                                  (date(2026, 1, 12), "LU1681043599", "DEMO-CW8", "AMUNDI MSCI WORLD UCITS ETF", 4)):
        p = px[tick][pd.Timestamp(dd)]
        pea_q[isin] = pea_q.get(isin, 0) + q
        mv.append([dd, "Achat comptant", nm, isin, q, fmt(p), fmt(round(q * p + 1.99, 2)), "1,99"])
    mv.append([date(2025, 6, 2), "Dividende", "TOTALENERGIES", "FR0000120271", 40, "", fmt(40 * 0.85), ""])
    mvdf = pd.DataFrame(mv, columns=["Date opération", "Opération", "Libellé", "Code ISIN", "Quantité", "Cours", "Montant", "Frais"])
    mvdf["Date opération"] = pd.to_datetime(mvdf["Date opération"]).dt.strftime("%d/%m/%Y")
    mvdf.to_csv(inbox / "boursorama" / "pea-mouvements.csv", sep=";", index=False, encoding="utf-8-sig")
    pos = pd.DataFrame([{"Libellé": nm, "Code ISIN": isin, "Quantité": pea_q[isin], "Cours": fmt(px[t][last]),
                         "Valorisation": fmt(pea_q[isin] * px[t][last])}
                        for isin, nm, t, *_ in INSTRUMENTS if isin in pea_q])
    pos.to_csv(inbox / "boursorama" / "pea-positions.csv", sep=";", index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------------
    # Binance (relevé « Transaction History ») et IBKR (Activity Statement)
    # ------------------------------------------------------------------
    for coin, (p0, mu, vol) in CRYPTO.items():
        px[f"{coin}-USD"] = pd.Series(_path(rng, n, p0, mu, vol), index=days)

    def usd_eur(sym, d):
        return px[sym][pd.Timestamp(d)] / fx["USD"][pd.Timestamp(d)]

    bl = []

    def bn(ts, op, coin, change, account="Spot"):
        bl.append(["123456789", ts, account, op, coin, f"{change:.8f}", ""])

    bn("2024-12-05 09:12:03", "Deposit", "EUR", 2000)
    for ts, coin, eur_amt in (("2024-12-06 10:00:00", "BTC", 1000), ("2024-12-06 10:05:00", "ETH", 600),
                              ("2025-03-10 18:30:00", "BTC", 250)):
        q = eur_amt / usd_eur(f"{coin}-USD", ts[:10])
        bn(ts, "Buy", coin, q)
        bn(ts, "Buy", "EUR", -eur_amt)
        bn(ts, "Transaction Fee", coin, -q * 0.001)
    bn("2024-12-07 08:00:00", "Simple Earn Flexible Subscription", "BTC", -0.005)
    bn("2024-12-07 08:00:00", "Simple Earn Flexible Subscription", "BTC", 0.005, "Earn")
    for m in pd.period_range("2025-01", today, freq="M"):
        bn(f"{m.year}-{m.month:02d}-01 01:00:00", "Simple Earn Flexible Interest", "BTC", 0.00002)
    # Conversion d'une partie de l'ETH en BTC
    ts = "2025-09-02 12:00:00"
    eth_q = 0.05
    val = eth_q * usd_eur("ETH-USD", ts[:10])
    bn(ts, "Binance Convert", "ETH", -eth_q)
    bn(ts, "Binance Convert", "BTC", val / usd_eur("BTC-USD", ts[:10]))
    bn("2026-02-14 16:20:00", "Withdraw", "EUR", -300)
    bn("2026-02-14 16:19:00", "Sell", "ETH", -0.04)
    bn("2026-02-14 16:19:00", "Sell", "EUR", 0.04 * usd_eur("ETH-USD", "2026-02-14"))
    pd.DataFrame(bl, columns=["User_ID", "UTC_Time", "Account", "Operation", "Coin", "Change", "Remark"]).to_csv(
        inbox / "binance" / "binance-transaction-history.csv", index=False)

    msft = lambda d: px["DEMO-MSFT"][pd.Timestamp(d)]  # noqa: E731
    lines = [
        "Statement,Header,Field Name,Field Value",
        "Statement,Data,BrokerName,Interactive Brokers Ireland Limited",
        'Statement,Data,Period,"January 1, 2025 - December 31, 2025"',
        "Account Information,Header,Field Name,Field Value",
        "Account Information,Data,Base Currency,EUR",
        "Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code",
    ]
    held = 0
    for d, q in (("2025-02-05", 8), ("2025-08-11", 5)):
        p = msft(d)
        held += q
        lines.append(f'Trades,Data,Order,Stocks,USD,MSFT,"{d}, 15:31:02",{q},{p:.2f},{p:.2f},{-q * p:.2f},-1,{q * p + 1:.2f},0,0,O')
    lines.append('Trades,Data,Order,Forex,EUR,EUR.USD,"2025-02-05, 15:30:00",-3500,1.04,1.04,3640,-2,0,0,0,')
    lines.append("Trades,SubTotal,,Stocks,USD,MSFT,,13,,,,,,,,")
    lines += [
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount",
        "Deposits & Withdrawals,Data,EUR,2025-02-03,Electronic Fund Transfer,6000",
        "Deposits & Withdrawals,Data,Total,,,6000",
        "Dividends,Header,Currency,Date,Description,Amount",
    ]
    for d in ("2025-03-13", "2025-06-12", "2025-09-11", "2025-12-11"):
        q = 8 if d < "2025-08-11" else 13
        lines.append(f"Dividends,Data,USD,{d},MSFT(US5949181045) Cash Dividend USD 0.83 per Share (Ordinary Dividend),{q * 0.83:.2f}")
    lines += ["Withholding Tax,Header,Currency,Date,Description,Amount,Code"]
    for d in ("2025-03-13", "2025-06-12", "2025-09-11", "2025-12-11"):
        q = 8 if d < "2025-08-11" else 13
        lines.append(f"Withholding Tax,Data,USD,{d},MSFT(US5949181045) Cash Dividend USD 0.83 per Share - US Tax,{-q * 0.83 * 0.15:.2f},")
    lines += [
        "Interest,Header,Currency,Date,Description,Amount",
        "Interest,Data,EUR,2025-11-04,EUR Credit Interest for Oct-2025,3.12",
        "Open Positions,Header,DataDiscriminator,Asset Category,Currency,Symbol,Quantity,Mult,Cost Price,Cost Basis,Close Price,Value,Unrealized P/L,Code",
        f"Open Positions,Data,Summary,Stocks,USD,MSFT,{held},1,0,0,0,0,0,",
        "Financial Instrument Information,Header,Asset Category,Symbol,Description,Conid,Security ID,Underlying,Listing Exch,Multiplier,Type,Code",
        "Financial Instrument Information,Data,Stocks,MSFT,MICROSOFT CORP,272093,US5949181045,MSFT,NASDAQ,1,COMMON,",
    ]
    (inbox / "ibkr" / "ibkr-activity-2025.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # Données de marché synthétiques puis import (hors ligne)
    # ------------------------------------------------------------------
    db = DB(profile.db_path)
    inst = pd.DataFrame([{"isin": i, "name": nm, "ticker": t, "currency": c, "asset_class": ac,
                          "region": max(eval(rg), key=eval(rg).get), "sector": None,
                          "exposure": ex, "regions": rg, "sectors": sc, "resolved_by": "demo"}
                         for i, nm, t, c, _, _, _, ex, rg, ac, sc in INSTRUMENTS])
    db.upsert("instruments", inst, mode="replace")
    pr = [pd.DataFrame({"symbol": t, "date": s.index.strftime("%Y-%m-%d"), "close": s.values}) for t, s in px.items()]
    pr.append(pd.DataFrame({"symbol": "IWDA.AS", "date": bench.index.strftime("%Y-%m-%d"), "close": bench.values}))
    db.upsert("prices", pd.concat(pr), mode="replace")
    fxr = [pd.DataFrame({"currency": c, "date": s.index.strftime("%Y-%m-%d"), "rate": s.values}) for c, s in fx.items()]
    db.upsert("fx_rates", pd.concat(fxr), mode="replace")
    logs = import_inbox(profile, db, online=False)
    from .market import resolve_all

    resolve_all(db, online=False)
    # Une opération saisie à la main, comme depuis le formulaire
    from .manual import add_operation, ensure_account

    acc = ensure_account(db, "IBKR", "cto")
    d = date(2026, 4, 1)
    add_operation(db, account_id=acc, kind="sell", d=d, ticker="DEMO-MSFT", isin="US5949181045", name="Microsoft",
                  quantity=3, price=float(msft(d)), currency="USD", fees=1.0, note="saisie démo", online=False)
    db.upsert("vacations", pd.DataFrame([
        {"name": "Japon 2025", "start": "2025-04-18", "end": "2025-04-27", "note": "démo"},
        {"name": "Lisbonne 2025", "start": "2025-08-02", "end": "2025-08-16", "note": "démo"},
    ]), mode="replace")
    db.upsert("balance_snapshots", pd.DataFrame([{"account_id": "manuel:ldds", "date": "2025-01-01", "balance": 4000.0, "source": "manuel"},
                                                  {"account_id": "manuel:ldds", "date": "2026-01-01", "balance": 6500.0, "source": "manuel"}]))
    db.upsert("accounts", pd.DataFrame([{"id": "manuel:ldds", "institution": "Crédit Mutuel", "name": "LDDS", "type": "livret", "currency": "EUR"}]))
    return "\n".join(logs)
