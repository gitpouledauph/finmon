# Meridian — local wealth & spending intelligence

Meridian is a private, **100 % local** alternative to wealth trackers such as Finary. It consolidates
brokers, crypto exchanges, employee savings and bank accounts into one dashboard:
net worth, investment performance (TWR / IRR, FX vs local attribution, benchmarks), allocation and
diversification, fees, projections and goals, and a full cash-flow analysis of your bank statements.

Nothing is synchronised with your banks: you import exports **once**, then keep the data current with
manual entries and monthly bank exports. Only public identifiers (tickers, ISINs, currency pairs) are sent
to Yahoo Finance to fetch prices. Your data lives in a local SQLite file under `data/`, which is never committed.

> Python package name: `finmon` · dashboard: Streamlit · data: SQLite

![pages](https://img.shields.io/badge/pages-14-7d9bd6) ![tests](https://img.shields.io/badge/tests-pytest-4fb286)

## Features

| Area | What you get |
|---|---|
| **Net worth** | total and history by category, clickable breakdown category → account → lines |
| **Performance** | value vs invested, total / unrealized / realized P&L, TWR & IRR, up to 4 benchmarks (MSCI World, S&P 500, Nasdaq-100, CAC 40…), return attribution local market vs currency, every closed trade |
| **Allocation** | look-through by asset class, region, currency, sector, account type; diversification score /100; holdings map coloured by return |
| **Market watch** | price chart of every underlying, 1D → 5Y, per chart |
| **Fee scanner** | fund TER (Yahoo, editable), annual cost, 10/20-year fee drag, cheaper equivalent ETFs (PEA-aware), broker costs |
| **Projections & goals** | net-worth projection by asset class, inflation, financial-independence year (4 % rule), savings goals |
| **Cash flow** | salary, rent, spending, savings rate by month/year; inflow & outflow ledgers; smoothing over N months; manual adjustments |
| **Monthly review** | any month vs 12-month average, last year or another month, by category |
| **Spending / Travel** | categorisation rules, per-merchant rules from one dropdown, trip costs |

## Quick start

```bash
git clone https://github.com/gitpouledauph/finmon.git meridian && cd meridian
python3 -m venv .venv-finmon && source .venv-finmon/bin/activate
pip install -r requirements.txt
python -m finmon demo          # optional: synthetic data to explore every page
python -m finmon dashboard     # opens http://localhost:8501
```

Requires Python 3.11+ (tested on 3.13). In the sidebar, switch between **Personal** and **Demo** profiles.

## Documentation

| Document | For |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Using Meridian day to day: first import, accounts, monthly routine, every page |
| [docs/AGENT_SETUP.md](docs/AGENT_SETUP.md) | An AI agent (or a helper) setting Meridian up for a new person |
| [docs/FORMATS.md](docs/FORMATS.md) | Every supported export, column by column |
| [docs/GUIDE_CSV.md](docs/GUIDE_CSV.md) | Where to download each export (French brokers/banks) |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Architecture, data model, adding an importer or a page, tests |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Fork & pull-request workflow |

## Forks and contributions

The repository is public: anyone can clone it or **fork** it and run Meridian on their own data.
`main` is protected — nobody pushes to it directly; changes arrive as pull requests from forks and need
the owner's approval. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Privacy

- `data/` (database, imports, personal rules) is git-ignored. Never commit exports: they contain names and
  account numbers. Test fixtures in `tests/fixtures/` are anonymised.
- Personal categorisation rules (names of landlords, employers…) live in `data/<profile>/regles.yaml`,
  outside version control.

## Legacy files

`app.py`, `pnl.py`, `brokers.py`, `news.py`, `trade.py`, `plots.py`, `pipeline.py` and similar files at the
repository root belong to an earlier prototype and are not used by Meridian.

## License

MIT — see [LICENSE](LICENSE).
