#### Le principe

1. **Une seule fois** : on importe l'historique complet de chaque compte (fichiers ci-dessous).
2. **Ensuite** : chaque nouvel achat, vente, dividende ou versement se saisit dans la page **Saisir une opération**.
   Aucune connexion aux banques ni aux courtiers ; seuls les cours publics viennent de Yahoo Finance.
3. **Si un compte ne colle pas** (crypto reçue par dépôt, conversion ou Earn, historique incomplet) :
   **Saisir une opération › Un relevé de positions** — on indique tout ce que contient le compte aujourd'hui,
   et finmon recale le portefeuille dessus.

Déposez les fichiers dans **Données & imports › Import historique** : le format est reconnu automatiquement.
Ré-importer un fichier qui recoupe un précédent ne crée pas de doublons.

---

#### Binance

Deux exports possibles, les deux sont acceptés (français ou anglais) :

**Historique des transactions — recommandé** (le plus complet : dépôts, retraits, intérêts Earn, conversions) :
1. Sur **binance.com** : **Portefeuille › Vue d'ensemble › Historique des transactions**.
2. **Exporter › Générer tous les relevés** : compte **Tous**, crypto **Toutes**, depuis l'ouverture
   (un export par année si la période est limitée).
3. Le CSV commence par `User_ID,UTC_Time,Account,Operation,Coin,Change,Remark`.

**Historique des trades Spot** (achats/ventes uniquement) :
**Ordres › Ordres Spot › Historique des trades › Exporter**. Le CSV commence par
`N° de commande,Durée,Paire,Côté,Prix,Exécuté,Montant,Frais`. Choisissez la période **la plus longue** :
si une vente dépasse les achats du fichier, finmon signale qu'il manque de l'historique.

Les achats payés en USDC/USDT sont convertis en euros au taux du dollar du jour.

#### Interactive Brokers — relevé d'activité annuel

1. **Portail client › Performance et relevés › Relevés › Activité** (« Activity Statement »).
2. Période : **Annuelle**, et choisissez une année (ou « Plage de dates personnalisée »).
3. Format : **CSV** › **Exécuter / Télécharger**.
4. Recommencez pour **chaque année** depuis l'ouverture du compte, plus l'année en cours
   (période « Depuis le début de l'année »).

Le fichier commence par `Statement,Header,Field Name,Field Value`. Achats/ventes, dividendes, retenues à la source,
intérêts, frais et versements sont repris et convertis en EUR au taux du jour. Les opérations de change
(EUR.USD) sont ignorées : seule compte la valeur en euros.

#### Trade Republic — export unique avec pytr

Trade Republic ne propose pas d'export CSV complet ; on utilise **une fois** l'outil open source pytr, en local :

```bash
cd ~/Desktop/Draft/Monitoring_Investments
source .venv-finmon/bin/activate
python -m finmon export-tr
```

pytr demande votre numéro (+33…), votre PIN, puis un code à valider dans l'app Trade Republic.
L'historique est téléchargé et importé directement. Ensuite, coupez le lien : `rm -rf ~/.pytr`.

#### Boursorama

**Compte courant et livrets** (pour les dépenses, revenus, vacances et soldes) :
**Mes comptes** › le compte › icône **Exporter** au-dessus des opérations › **CSV**, période la plus longue possible.
Un fichier par compte (courant, Livret A, LDDS…). Le fichier commence par `dateOp;dateVal;label;…`.
Pour suivre les dépenses ensuite, refaites cet export une fois par mois (le dernier mois suffit).

**PEA / compte-titres** : depuis **Bourse › Mon portefeuille › Exporter** (« positions comptables », fichier `export-positions-comptables-….csv`), et si possible
- les **positions** (titre, ISIN, quantité, cours, prix de revient) ;
- l'**historique des opérations** (achats, ventes, dividendes).

Choisissez « PEA » ou « Compte-titres » au moment de l'import. Si Boursorama ne propose pas d'export exploitable,
remplissez le **modèle CSV finmon** (bouton ci-dessous) avec vos achats passés, ou envoyez-moi le fichier obtenu.

#### Autre courtier, ou saisie en masse

Téléchargez le **modèle CSV finmon** : une ligne par opération
(`date;compte;type;ticker;isin;nom;quantite;prix;devise;frais;note`). Types : Achat, Vente, Dividende, Versement,
Retrait, Frais, Intérêts. Pour Dividende/Versement/Retrait, mettez le montant dans la colonne `prix`.

#### Soldes ailleurs

Un livret dans une autre banque ? **Revenus & épargne › Saisir un solde à la main**.
