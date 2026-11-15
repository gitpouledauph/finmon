# finmon — Personal Book Monitoring

Moniteur **100 % local** de patrimoine, investissements et dépenses : un « Finary maison » qui tourne sur votre Mac.
Les données viennent de fichiers (exports Boursorama, pytr pour Trade Republic) et vivent dans une base SQLite
locale (`data/`, exclue de git). Seuls des identifiants publics (ISIN, tickers, paires de devises) partent vers
Yahoo Finance pour récupérer cours et taux de change.

## Démarrage

```bash
cd ~/Desktop/Draft/Monitoring_Investments
/opt/homebrew/bin/python3.13 -m venv .venv-finmon      # déjà fait
.venv-finmon/bin/pip install -r requirements.txt
.venv-finmon/bin/python -m finmon demo                  # profil démo, sans réseau
.venv-finmon/bin/python -m finmon dashboard             # ouvre http://localhost:8501
```

Dans le dashboard, la barre latérale bascule entre **Mes données** et **Démo**.

## Alimenter avec vos données

**1. Une seule fois : l'historique.** Dans **Données & imports › Import historique**, déposez :

| Compte | Fichier |
|---|---|
| Binance | Historique des transactions (recommandé) ou Historique des trades Spot, en français ou anglais |
| Interactive Brokers | Un *relevé d'activité* annuel CSV par année (français ou anglais) |
| Trade Republic | `python -m finmon export-tr` (pytr, une seule fois), puis `rm -rf ~/.pytr` |
| Boursorama | Export CSV des opérations (courant, livrets) ; positions et mouvements du PEA/CTO |
| Autre | Modèle CSV finmon (téléchargeable dans le dashboard) |

Détail pas à pas : [docs/GUIDE_CSV.md](docs/GUIDE_CSV.md) · formats reconnus colonne par colonne : [docs/FORMATS.md](docs/FORMATS.md).

**2. Ensuite : plus aucune connexion.** Chaque nouvelle opération (achat, vente, dividende, versement…)
se saisit dans la page **➕ Saisir une opération** : compte, ticker Yahoo, date, quantité, prix, devise, frais.
Le montant est converti en EUR au taux du jour et la ligne rejoint le portefeuille.

**3. Cours en direct.** Le dashboard récupère le dernier cours de vos lignes (crypto en temps réel, actions
avec ~15 min de différé selon la place) toutes les 1, 5 ou 15 minutes, et recalcule valeurs et PnL.

Commandes utiles :

```bash
.venv-finmon/bin/python -m finmon import      # importe data/reel/inbox/**
.venv-finmon/bin/python -m finmon export-tr   # historique Trade Republic (une fois)
.venv-finmon/bin/python -m finmon prices      # historique + dernier cours + change
.venv-finmon/bin/python -m finmon export      # classeur Excel dans data/reel/exports/
.venv-finmon/bin/python -m finmon status
./scripts/install_daily_sync.sh               # mise à jour quotidienne des cours (launchd)
```

## Ce que montre le dashboard

- **Vue d'ensemble** — patrimoine net et son évolution (investissements / épargne réglementée / liquidités),
  variation par compte, dépenses du mois vs moyenne, taux d'épargne, performance.
- **Investissements** — valeur vs capital investi, performance TWR et TRI, comparaison à un indice,
  positions (PRU, poids, plus-values), réalisé, dividendes, frais.
  **Décomposition sous-jacent / change** : pour chaque titre, la plus-value latente est séparée entre la
  performance du sous-jacent dans sa devise et l'effet EUR/devise, selon l'exposition devise *du sous-jacent*
  (un ETF MSCI World coté en euros reste ≈ 72 % exposé au dollar).
- **Allocation & exposition** — par classe d'actif, enveloppe, établissement, zone, devise et secteur
  (ETF éclatés par transparence), concentration, carte des lignes.
- **Dépenses** — par catégorie et par mois/année, carte de chaleur, principaux marchands, correction
  manuelle des catégories (mémorisée).
- **Vacances** — périodes (saisies ou détectées via les paiements en devise étrangère), coût par voyage,
  par jour, par an, part des dépenses annuelles.
- **Revenus & épargne** — revenus vs dépenses, épargne mensuelle, taux d'épargne, livrets.
- **➕ Saisir une opération** — formulaire (compte, ticker, date, quantité, prix, devise, frais) et liste des saisies, avec suppression.
- **Données & imports** — import historique unique, modèle CSV, édition des titres (ticker, expositions), journal, export.

## Méthodes de calcul

- Prix de revient au **PMP** (méthode fiscale française). Plus-value réalisée = produit de cession − PMP × quantité.
- **Effet change** : F(t) = valeur EUR du panier de devises du sous-jacent. Avec `units = Σ coût / F(date d'achat)` :
  `r_change = F(t)·units/coût − 1`, `r_sous-jacent = valeur / (F(t)·units) − 1` ; le terme croisé est le reste.
- **TWR** : chaînage des rendements quotidiens hors flux ; **TRI** : taux actuariel des versements.
- Dépenses : correction manuelle > règles (`config/categories.yaml`) > catégorie Boursorama > « À classer ».
  Les virements internes, vers les livrets et vers les courtiers ne sont pas des dépenses.

## Configuration

- `config/settings.yaml` — noms/types des comptes, indice de référence, catégories exclues des vacances.
- `config/categories.yaml` — taxonomie et règles de classement (expressions régulières).
- `config/instruments.yaml` — corrections par ISIN (ticker, exposition devise, régions, secteurs) et alias de noms.

## Structure

```
finmon/            moteur (imports, saisie, base, marché, calculs, graphes)
  importers/       boursorama.py, traderepublic.py, binance.py, ibkr.py
  manual.py        saisie manuelle et modèle CSV
  analytics/       portfolio.py, budget.py, networth.py, allocation.py
dashboard/         app Streamlit (app.py + views/)
config/            réglages YAML
docs/              guide des exports
tests/             tests des calculs (pytest)
data/              VOS DONNÉES — local uniquement, ignoré par git
```

Les anciens fichiers (`trade.py`, `pnl.py`, `app.py`…) sont conservés tels quels ; le nouveau code ne les utilise pas.

> finmon est un outil de suivi : il ne donne pas de conseil en investissement.
