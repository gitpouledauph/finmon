# Formats de fichiers acceptés

Référence des exports que finmon sait lire. Ils sont reconnus **automatiquement d'après leur contenu**
(pas d'après leur nom), quelle que soit la langue du site d'origine quand c'est indiqué.
Des exemples anonymisés sont dans [`tests/fixtures/`](../tests/fixtures).

Règles communes :
- tous les montants sont convertis en **EUR au taux du jour** de l'opération (taux Yahoo Finance) ;
- ré-importer un fichier, ou deux fichiers qui se recoupent, **ne crée pas de doublons** ;
- les avertissements d'import s'affichent dans *Données & imports* (« Points d'attention ») et dans le journal.

---

## Binance

### A. Historique des trades Spot — `Binance-Historique-des-trades-Spot-…csv`

Où : **Ordres › Ordres Spot › Historique des trades › Exporter**.

| Français | Anglais | Exemple |
|---|---|---|
| N° de commande | Order No. | `1000000001` |
| Durée | Date(UTC) / Time | `2026-02-06 17:32:27` |
| Paire | Pair | `BTCEUR`, `ETHUSDC` |
| Côté | Side | `BUY` / `SELL` |
| Prix | Price | `60000.00` |
| Exécuté | Executed | `0.00100BTC` (quantité + crypto) |
| Montant | Amount | `60.00EUR` (montant + devise de cotation) |
| Frais | Fee | `0.00000102BTC` ou `1.35USDC` |

Traitement :
- plusieurs exécutions d'un même ordre à la même seconde sont regroupées en une opération ;
- achat payé en **EUR** : montant exact ; payé en **USDC/USDT** (stablecoins) : montant USD converti en EUR —
  les stablecoins sont traités comme des liquidités, pas comme une position ;
- frais prélevés en crypto : la quantité est réduite (petite perte réalisée) ; frais en EUR/USDC : frais en euros.

Limite : ce fichier ne contient **ni dépôts, ni retraits, ni intérêts Earn/staking, ni conversions « Convert »**.
Si une vente dépasse les achats connus, un avertissement signale qu'il manque de l'historique.

### B. Historique des transactions (relevé complet) — recommandé

Où : **Portefeuille › Vue d'ensemble › Historique des transactions › Exporter** (« Générer tous les relevés »).
Colonnes : `User_ID,UTC_Time,Account,Operation,Coin,Change,Remark`.

| Opérations Binance | Traitées comme |
|---|---|
| Deposit / Withdraw (EUR ou stablecoin) | versement / retrait |
| Deposit / Withdraw (crypto) | transfert entrant / sortant au cours du jour |
| Buy, Sell, Transaction Buy/Spend/Revenue/Sold, Binance Convert, Small Assets Exchange, Auto-Invest… | achats / ventes (regroupés par seconde) |
| Transaction Fee, Fee | frais |
| Simple Earn Interest, Staking Rewards, Distribution, Airdrop, Cashback… | gain (« récompense ») |
| Subscription / Redemption Earn, Transfer Between Wallets… | ignoré (mouvement interne) |

---

## Interactive Brokers — Relevé d'activité (Activity Statement), CSV

Où : **Performance et relevés › Relevés › Activité**, période *Annuelle* (une par année), format **CSV**.
Accepté **en français et en anglais**. Le fichier empile des sections (`Section,Header,…` puis `Section,Data,…`).

| Contenu | Section (EN) | Section (FR) | Colonnes utilisées |
|---|---|---|---|
| Période du relevé | Statement › Period | Statement › Period (`Janvier 1, 2025 - Décembre 31, 2025`) | Field Name/Value · Nom champ/Valeur champ |
| Achats / ventes | Trades | Transactions | Asset Category, Currency, Symbol, Date/Time, Quantity, Proceeds, Comm/Fee (et équivalents FR : Catégorie d'actifs, Devise, Symbole, Date/Heure, Quantité, Produit, Comm/Tarif) |
| Versements / retraits | Deposits & Withdrawals | Dépôts et retraits | Currency/Devise, Settle Date/Date de règlement, Description, Amount/Montant |
| Dividendes | Dividends, Payment In Lieu Of Dividends | Dividendes | Devise, Date, Description (`AAPL(US0378331005) …`), Montant |
| Retenue à la source | Withholding Tax | Retenue à la source | idem |
| Intérêts, frais | Interest, Fees | Intérêts, Frais | idem |
| ISIN des titres | Financial Instrument Information | Informations sur l'instrument financier | Symbol, Security ID |
| Positions de fin de période | Open Positions | Positions ouvertes | Symbol, Quantity (sert au rapprochement) |
| Bourse de cotation | Financial Instrument Information › Listing Exch | Informations instrument financier › Liste des Bourses | choisit le ticker Yahoo |

Les lignes `Total`, `SubTotal`, les sections d'information (Actif net, Codes, Mentions légales…) et les
opérations de change (Forex, EUR.USD, conversions automatiques « AFx ») sont ignorées. Une section peut avoir
**plusieurs en-têtes** (ex. `Transactions` : actions puis Forex) : chaque ligne utilise l'en-tête qui la précède.

La bourse indiquée par IBKR fixe la cotation suivie, dans la devise réellement payée :
`BVME.ETF` → `.MI` (Milan, EUR), `LSEETF`/`LSE` → `.L` (Londres), `SBF` → `.PA`, `AEB` → `.AS`,
`IBIS`/`XETRA` → `.DE`, `NASDAQ`/`NYSE`/`ARCA` → sans suffixe (USD)… Un relevé par année ;
le nom du fichier (`U1234567_20260101_20261113.csv`) n'a pas d'importance.

---

## Trade Republic — via pytr (une fois)

`python -m finmon export-tr` : connexion v2 (validation dans l'app), puis import de
`account_transactions.csv` (`Date;Type;Value;Note;ISIN;Shares;Fees;Taxes;…`, types en anglais, français ou allemand)
et `portfolio.csv` (`Name;ISIN;quantity;price;avgCost;netValue`). Ces deux fichiers peuvent aussi être déposés à la main.

## Boursorama / BoursoBank

- **Opérations de compte** (courant, livrets) : `dateOp;dateVal;label;category;categoryParent;supplierFound;amount;comment;accountNum;accountLabel;accountbalance`.
- **Positions PEA/CTO — « positions comptables »** (*Bourse › Mon portefeuille › Exporter*,
  fichier `export-positions-comptables-JJ-MM-AAAA_HH-MM-SS.csv`) :

  | Colonne | Sens | Exemple |
  |---|---|---|
  | name | titre | `AMUNDI PEA S&P 500 UCITS ETF ACC` |
  | isin | ISIN | `FR0011871128` |
  | quantity | quantité (2 décimales : arrondie pour les fonds) | `16,00` |
  | buyingPrice | prix de revient unitaire | `47,95` |
  | lastPrice | dernier cours | `60,05` |
  | amount | valorisation | `960,80` |
  | amountVariation / variation | plus-value latente € / % | `193,60` / `25,23` |
  | lastMovementDate | dernier mouvement | `2025-11-05` |

  La date de l'export est lue dans le nom du fichier. Le fichier ne dit pas s'il s'agit d'un PEA ou d'un
  compte-titres : on le précise à l'import. Sans historique d'opérations, le **prix de revient** sert de
  montant investi ; le montant investi exact (versements) n'est pas connu.
  Les fonds en **gestion profilée** (ex. *PEA Profile Équilibre*) apparaissent dans ce même export, avec une
  quantité arrondie à 2 décimales (écart de quelques centimes sur la valeur).
- **Positions PEA/CTO, autres exports** : colonnes du type libellé / ISIN / quantité / cours / prix de revient / valorisation.
- **Mouvements PEA/CTO** : date / opération / libellé / ISIN / quantité / cours / montant / frais.

## Épargne réglementée (Livret A, LDDS, LEP…)

Pas de fichier : *Revenus & épargne › Saisir un solde à la main*, avec le taux. Les taux réglementés en vigueur
sont dans `config/settings.yaml › taux_reglementes` (à mettre à jour au 1er février et au 1er août).

## Modèle CSV finmon (tout autre courtier)

`date;compte;type;ticker;isin;nom;quantite;prix;devise;frais;note` — téléchargeable dans le dashboard.
Types : Achat, Vente, Dividende, Versement, Retrait, Frais, Intérêts. Pour Dividende/Versement/Retrait, le montant va
dans `prix`.

---

## Ajouter un nouveau format

1. Déposer un exemple **anonymisé** dans `tests/fixtures/`.
2. Écrire ou étendre un lecteur dans `finmon/importers/` (fonctions `detect…` + `import_…`).
3. Le brancher dans `finmon/sync.py::import_any` et ajouter un test dans `tests/test_core.py`.
4. Compléter ce document.
