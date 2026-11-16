# Contributing

`main` is protected: nobody pushes to it directly. Every change arrives through a pull request.

1. **Get access**: ask the owner to add your GitHub username as a collaborator (read access).
2. **Fork** the repository (GitHub › *Fork*), then clone your fork:
   ```bash
   git clone https://github.com/<you>/finmon.git meridian && cd meridian
   git remote add upstream https://github.com/gitpouledauph/finmon.git
   ```
3. **Branch** from an up-to-date `main`:
   ```bash
   git fetch upstream && git switch -c feature/<short-name> upstream/main
   ```
4. **Develop** following [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md); run `python -m pytest -q`.
5. **Never commit personal data** (`data/`, bank or broker exports, `regles.yaml`). Fixtures must be anonymised.
6. **Open a pull request** from your fork to `gitpouledauph/finmon:main` with a short description and
   screenshots for UI changes. The owner reviews and merges.

To keep your fork current: `git fetch upstream && git rebase upstream/main`.
