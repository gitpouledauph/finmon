# Meridian — user guide

## 1. Install and launch

```bash
git clone https://github.com/gitpouledauph/finmon.git meridian && cd meridian
python3 -m venv .venv-finmon && source .venv-finmon/bin/activate
pip install -r requirements.txt
python -m finmon dashboard            # http://localhost:8501 — Ctrl+C to stop
```

Next times: `cd meridian && source .venv-finmon/bin/activate && python -m finmon dashboard`.

| Command | Does |
|---|---|
| `python -m finmon dashboard` | start the dashboard |
| `python -m finmon demo` | build the demo profile (synthetic data) |
| `python -m finmon import` | import every file dropped in `data/reel/inbox/<source>/` |
| `python -m finmon export-tr` | one-off Trade Republic history download (pytr, phone confirmation) |
| `python -m finmon prices` | refresh prices and FX history |
| `python -m finmon export` | Excel export of everything |
| `python -m finmon status` | accounts, row counts, last prices |

Two profiles exist: **Personal** (`data/reel/`) and **Demo** (`data/demo/`). Switch in the sidebar.

## 2. First setup (once)

1. **Import history** — *Settings › Data & imports › Import*: drop each export. The format is detected from
   the content; re-importing overlapping files never creates duplicates. Supported exports and where to
   download them: [GUIDE_CSV.md](GUIDE_CSV.md) · column reference: [FORMATS.md](FORMATS.md).

   | Account | File |
   |---|---|
   | Interactive Brokers | Activity Statement CSV, one per year (EN or FR) |
   | Binance | *Transaction history* (complete) — or *Spot trade history* |
   | Trade Republic | `python -m finmon export-tr` |
   | Boursorama / BoursoBank | `export-operations-….csv` (all bank accounts) + `export-positions-comptables-….csv` (PEA/CTO) |
   | Anything else | the Meridian CSV template (download it on the import tab) |

2. **Create accounts that cannot be imported** — *Investments › Transactions*:
   - **Tracked holdings**: securities, quantities and prices are followed line by line (PEA, brokerage, crypto).
     Add trades, or a *Holdings statement* (everything the account contains today).
   - **Manual value**: you only enter the **total invested** and the **current value** (employee savings
     plan, life-insurance euro fund…). Nothing is tracked; gain = value − invested. Update whenever you like —
     the last value is kept until you enter a new one.
   - Savings accounts (Livret A, LDDS…): *Overview › Net worth › Update manually valued accounts* or
     *Cash flow › Savings accounts*.

3. **Personal categorisation rules** — `data/reel/regles.yaml` (never committed). Typical content:

   ```yaml
   owner_names: ["DOE JOHN", "JOHN DOE"]          # transfers between your own accounts
   loyer_fixe:                                     # rent share counted in the budget (shared flat)
     - {depuis: "2025-07", montant: 900}
   etalement:                                      # spread an inflow (tax refund over Jul–Dec of N-1)
     - {pattern: "DGFIP", mois: 6, debut_mois: 7, annee: -1}
   rules:                                          # regex on the bank label; first match wins
     - {pattern: "ACME CORP", category: Salaire, sign: credit}
     - {pattern: "LANDLORD NAME", category: "Loyer & colocation (hors budget)"}
   ```

## 3. Monthly routine (5 minutes)

1. Export the last month from your bank, drop it in *Data & imports*.
2. *Investments › Transactions*: enter new trades; update manual-value accounts.
3. *Cash flow › Spending › To classify*: pick a category per unknown merchant (creates a rule for next time).
4. *Monthly review*: compare the month with the 12-month average or any other month.

## 4. Pages

| Page | Notes |
|---|---|
| **Net worth** | click a category, then an account, to see what it holds |
| **Performance** | pick accounts at the top; *Closed trades* lists every realized gain/loss |
| **Allocation** | *Investments* or *Total wealth* scope; diversification score breakdown in the expander |
| **Market watch** | one timeframe for all charts at the top, or per chart |
| **Fee scanner** | edit a TER if Yahoo has none; *Save TER overrides* |
| **Projections & goals** | assumptions per asset class in the expander; goals tab |
| **Line simulator** | per-line projection from up to 10 years of history |
| **Transactions** | *Tracked holdings* vs *Manual value* accounts; new accounts declare their tracking mode |
| **Cash flow** | *Inflows* (count / smooth / deduct / ignore each inflow), *Outflows* (share %, category, exclude), *Smoothing* (spread an inflow or an expense over N months), *Manual adjustments* (± on a month) |
| **Monthly review** | *Compare with*: 12-month average, same month last year, or any month |
| **Spending** | category charts, *To classify* by merchant, all transactions editor |
| **Travel** | trips (dates), cost per trip and per day; foreign-currency payments suggest trips |

### How the cash-flow numbers are defined

- **Income** = salary + bonus/works council + smoothed inflows + inflows marked *Income* + manual adjustments.
- **Spending** = card payments, direct debits and cash withdrawals (never transfers), minus inflows marked
  *Deduct from spending*, health refunds matched to the related expense, and manual adjustments. Each
  transaction can count only for your share (Outflows › Share %).
- **Rent** = your fixed share (`loyer_fixe`); real rent and flatmates' transfers are kept out of the budget.
- **Saved** = income − rent − spending · **Savings rate** = saved / income.

## 5. Backup and reset

The whole state is `data/reel/finmon.db` plus `data/reel/regles.yaml` and `regles_auto.yaml`. Copy the
`data/` folder to back up. Deleting `data/reel/` resets the Personal profile.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| A price is missing | *Data & imports › Securities*: set the Yahoo ticker, then *Recompute* in the sidebar |
| Port 8501 busy | `streamlit run dashboard/app.py --server.port 8502` |
| A sale exceeds known holdings | import a longer history, or enter a holdings statement |
| An alert is irrelevant | *Hide* it; restore from *Data & imports › Status* |
