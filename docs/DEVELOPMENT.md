# Meridian — development guide

## Layout

```
finmon/                 core package (no Streamlit import)
  db.py                 SQLite schema + light migrations, DB.upsert / read, set_override
  config.py             profiles (data/reel, data/demo), YAML config + per-profile rules
  parsing.py            tolerant CSV reading, number/date parsing, stable ids
  importers/            one module per source: detect…() + import_…()
  sync.py               import_any(): content-based dispatch to importers
  market.py             instrument resolution (ISIN → Yahoo ticker), prices, FX, live quotes
  manual.py             manual trades, holdings statements, CSV template
  data.py               load(db) → Bundle: the full computed state for the UI
  analytics/
    portfolio.py        positions, PMP cost basis, FX attribution, TWR / IRR, closed trades
    manual_accounts.py  manually valued accounts merged into the portfolio
    networth.py         daily balances and net worth by bucket
    allocation.py       look-through allocation, diversification score
    budget.py           categorisation, transfer matching, rent share, smoothing, cash-flow figures
    fees.py             TER scan, fee drag, cheaper equivalents
    projection.py       wealth projection, FI target, goals
    simulation.py       per-line projection from history
  charts.py             Plotly helpers (palette, donut, treemap, bars…)
dashboard/
  app.py                navigation, sidebar, logo
  theme.py              CSS and small HTML blocks
  common.py             cached bundle, dialogs, editors, English labels
  views/*.py            one file per page
config/                 generic, versioned configuration (categories, settings, instruments)
data/<profile>/         local only: finmon.db, inbox/, archive/, regles.yaml, regles_auto.yaml
tests/                  pytest; fixtures are anonymised exports
```

## Data model (SQLite)

| Table | Content |
|---|---|
| `accounts` | id, institution, name, type (`courant`, `livret`, `pea`, `cto`, `crypto`, `assurance_vie`, `epargne_salariale`, `autre`), rate, tracking (`holdings` / `manual`) |
| `trades` | broker events: buy, sell, dividend, interest, fee, tax, deposit, withdrawal, transfer_in/out, reward (amounts in EUR, negative = cash out) |
| `position_snapshots` | full holdings statements (reconciliation) |
| `instruments` | ISIN/pseudo-ISIN → ticker, currency, asset class, exposures (JSON) |
| `prices`, `fx_rates` | daily closes; FX as units of currency per 1 EUR |
| `cash_transactions` | bank lines (label, merchant, amount, bank categories) |
| `balance_snapshots` | bank balances and manual valuations |
| `manual_contributions` | invested amounts of manually valued accounts |
| `category_overrides` | per-transaction category / trip / share factor |
| `income_treatment` | per-transaction inflow/outflow choice: income, smooth (months, start), offset, ignore |
| `manual_adjustments` | ± corrections on a month (spending or income) |
| `fee_overrides`, `goals`, `vacations`, `import_log` | as named |

`data.load()` builds everything in this order: classify bank lines → match transfers to broker deposits →
fixed rent share → inflow treatments → rule-based spreading → health-refund matching → manual adjustments;
portfolio build → manual-value accounts merge → net worth → allocation.

## Adding an importer

1. Put an **anonymised** sample in `tests/fixtures/`.
2. Write `detect_x(df)` and `import_x(db, …)` in `finmon/importers/` (amounts in EUR via `market.fx_on`,
   ids via `parsing.stable_ids` so re-imports are idempotent).
3. Dispatch it in `sync.import_any`.
4. Add a test in `tests/test_core.py`; document the format in `docs/FORMATS.md`.

## Adding a page

Create `dashboard/views/<page>.py`, register it in `dashboard/app.py` (`P` and `pages`). Read data with
`bundle()`; write with `get_db()` then `invalidate()` + `st.rerun()`. Keep the visual language:
`theme.section()` titles, `st.metric` cards, `charts.*` helpers, English labels, no explanatory paragraphs.

## Tests

```bash
python -m pytest -q
```

Every page can also be smoke-tested headlessly with `streamlit.testing.v1.AppTest` (see git history for examples).

## Conventions

- Stored categories and labels are French (historic); `common.en()` translates for display.
- Never commit anything under `data/`, `.venv-finmon/`, exports or personal rules.
- Commit messages: imperative summary line, body explaining the why.
