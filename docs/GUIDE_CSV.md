#### Le principe

1. **Une seule fois** : on importe l'historique complet de chaque compte (fichiers ci-dessous).
2. **Ensuite** : chaque nouvel achat, vente, dividende ou versement se saisit dans la page **➕ Saisir une opération**.
   Aucune connexion aux banques ni aux courtiers ; seuls les cours publics viennent de Yahoo Finance.

Déposez les fichiers dans **Données & imports › Import historique** : le format est reconnu automatiquement.
Ré-importer un fichier qui recoupe un précédent ne crée pas de doublons.

---

#### 🟡 Binance — relevé de toutes les transactions

1. Sur **binance.com** (navigateur d'ordinateur) : **Portefeuille › Vue d'ensemble › Historique des transactions**.
2. En haut à droite : **Exporter › Exporter l'historique des transactions** (ou « Générer tous les relevés »).
3. Compte : **Tous** · Crypto : **Toutes** · Période : depuis l'ouverture du compte. Si la période est limitée
   (souvent 12 mois par export), faites un export par année.
4. Téléchargez le fichier quand Binance l'a préparé (quelques minutes, lien dans « Historique des exports ») :
   un CSV qui commence par `User_ID,UTC_Time,Account,Operation,Coin,Change,Remark`.

Achats, ventes, conversions, frais, intérêts Earn/staking, dépôts et retraits sont tous pris en compte.
Les montants en EUR sont calculés au cours du jour de chaque opération.

#### 🔴 Interactive Brokers — relevé d'activité annuel

1. **Portail client › Performance et relevés › Relevés › Activité** (« Activity Statement »).
2. Période : **Annuelle**, et choisissez une année (ou « Plage de dates personnalisée »).
3. Format : **CSV** › **Exécuter / Télécharger**.
4. Recommencez pour **chaque année** depuis l'ouverture du compte, plus l'année en cours
   (période « Depuis le début de l'année »).

Le fichier commence par `Statement,Header,Field Name,Field Value`. Achats/ventes, dividendes, retenues à la source,
intérêts, frais et versements sont repris et convertis en EUR au taux du jour. Les opérations de change
(EUR.USD) sont ignorées : seule compte la valeur en euros.

#### 🟢 Trade Republic — export unique avec pytr

Trade Republic ne propose pas d'export CSV complet ; on utilise **une fois** l'outil open source pytr, en local :

```bash
cd ~/Desktop/Draft/Monitoring_Investments
source .venv-finmon/bin/activate
python -m finmon export-tr
```

pytr demande votre numéro (+33…), votre PIN, puis un code à valider dans l'app Trade Republic.
L'historique est téléchargé et importé directement. Ensuite, coupez le lien : `rm -rf ~/.pytr`.

#### 🔵 Boursorama

**Compte courant et livrets** (pour les dépenses, revenus, vacances et soldes) :
**Mes comptes** › le compte › icône **Exporter** au-dessus des opérations › **CSV**, période la plus longue possible.
Un fichier par compte (courant, Livret A, LDDS…). Le fichier commence par `dateOp;dateVal;label;…`.
Pour suivre les dépenses ensuite, refaites cet export une fois par mois (le dernier mois suffit).

**PEA / compte-titres** : depuis **Bourse › Mon portefeuille**, exportez si possible
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
