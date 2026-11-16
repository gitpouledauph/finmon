# Setting Meridian up for a new person (agent playbook)

This file is written for an AI coding agent (or a human helper) onboarding a new user. Follow the steps in
order; ask the user only for what you cannot read from their files.

## Ground rules

- Everything stays local. Never upload exports or the database anywhere, never commit `data/`.
- Never type the user's passwords, PINs or 2FA codes. For Trade Republic, the user runs
  `python -m finmon export-tr` and confirms on their phone.
- Exports contain names and account numbers: if a new format needs a test fixture, anonymise it first.
- Personal rules (names of landlord, employer, flatmates) go in `data/reel/regles.yaml`, not in `config/`.

## 1. Install

Python **3.11+** is required (`python3 --version`). On macOS install one if needed (`brew install python@3.13`)
and use `python3.13` below.

```bash
git clone https://github.com/gitpouledauph/finmon.git meridian && cd meridian
python3 -m venv .venv-finmon && source .venv-finmon/bin/activate
pip install -r requirements.txt && python -m pytest -q    # all tests must pass
```

## 2. Interview (ask once)

1. Which **investment accounts**? (broker, PEA, crypto exchange, life insurance, employee savings…)
   For each: *tracked holdings* (we follow securities) or *manual value* (only invested + current value)?
2. Which **bank accounts** (current, deferred-debit card, savings accounts) and which bank?
3. **Income**: employer name as it appears on the salary transfer; other regular income.
4. **Housing**: rent paid to whom; shared flat? flatmates' names; the user's fixed share.
5. Regular **transfers between own accounts** (their name as it appears in labels).
6. Anything to **spread** (tax refund, annual bonus) or to **exclude**.

## 3. Collect and import exports

Give the user the download instructions from [GUIDE_CSV.md](GUIDE_CSV.md). Then:

```bash
python -m finmon import                      # or drop files in Settings › Data & imports
python -m finmon prices
```

Check `python -m finmon status` and the *Status* tab. If a file is not recognised, extend the parser
(see [DEVELOPMENT.md](DEVELOPMENT.md) › *Adding an importer*), add an anonymised fixture and a test,
document the format in [FORMATS.md](FORMATS.md).

## 4. Create the other accounts

In *Investments › Transactions*: *New account…* → name, type, **tracking mode**. For manual-value accounts
enter *total invested* and *current value*. Savings accounts: *Net worth › Update manually valued accounts*.

## 5. Write the personal rules

Create `data/reel/regles.yaml` from the interview (template in [USER_GUIDE.md](USER_GUIDE.md) §2.3). Reload
the dashboard (*Recompute*) and check *Cash flow*: salary recognised, rent and transfers out of spending,
broker transfers under *Invested*. Then let the user classify the remaining merchants in
*Spending › To classify* (one dropdown per merchant).

## 6. Verify with the user

- Net worth per account matches their apps (± prices of the day).
- No negative quantities / no "sale exceeds holdings" alerts left unexplained.
- Monthly spending looks plausible; open a month's detail and check a few lines.

## 7. Hand over

Show the monthly routine (USER_GUIDE §3). Optionally schedule `scripts/install_daily_sync.sh` (daily prices).
