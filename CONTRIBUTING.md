# Contributing

`main` is protected: nobody pushes to it directly. Every change arrives through a pull request
from a fork and needs one approval from the owner.

1. **Fork** the repository (GitHub › *Fork*), then clone your fork:
   ```bash
   git clone https://github.com/<you>/finmon.git meridian && cd meridian
   git remote add upstream https://github.com/gitpouledauph/finmon.git
   ```
2. **Branch** from an up-to-date `main`:
   ```bash
   git fetch upstream && git switch -c feature/<short-name> upstream/main
   ```
3. **Develop** following [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md); run `python -m pytest -q`.
4. **Never commit personal data** (`data/`, bank or broker exports, `regles.yaml`). Fixtures must be anonymised.
5. **Open a pull request** from your fork to `gitpouledauph/finmon:main` with a short description and
   screenshots for UI changes. The owner reviews and merges.

To keep your fork current: `git fetch upstream && git rebase upstream/main`.
