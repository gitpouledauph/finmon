### 1. Compte courant et livrets Boursorama — l'essentiel

C'est ce fichier qui alimente **dépenses, revenus, vacances et soldes**.

1. Sur **boursobank.com** (le site web, pas l'app mobile), ouvrez **Mes comptes** puis cliquez sur le compte courant.
2. Dans la liste des opérations, cliquez sur l'icône **Télécharger / Exporter** (flèche vers le bas, au-dessus de la liste).
3. Choisissez le format **CSV** et la **période la plus longue possible** (idéalement depuis l'ouverture du compte ; sinon faites plusieurs exports, les doublons sont ignorés).
4. Recommencez pour **chaque livret** (Livret A, LDDS…) : cela donne l'historique des versements et intérêts.

Le fichier attendu commence par une ligne d'en-tête du type :
`dateOp;dateVal;label;category;categoryParent;supplierFound;amount;comment;accountNum;accountLabel;accountbalance`

Ensuite, refaites un export **une fois par mois** (le dernier mois suffit) pour garder le dashboard à jour.

### 2. PEA / compte-titres Boursorama — si vous en avez un

Deux exports complémentaires, depuis l'espace **Bourse › Mon portefeuille** :

- **Positions** (photo actuelle : titre, ISIN, quantité, cours, prix de revient, valorisation). Si un bouton
  d'export CSV/Excel est proposé sur la page portefeuille, prenez-le. Si l'export est en Excel (.xlsx),
  ouvrez-le et faites « Enregistrer sous… › CSV ».
- **Mouvements / historique des opérations** du PEA (achats, ventes, dividendes) sur la période la plus longue.
  Sans cet historique, la performance part du jour du premier import et l'effet de change n'est pas calculable.

Au moment de l'import, indiquez s'il s'agit du **PEA** ou du **compte-titres**.
L'interface Boursorama change régulièrement : si vous ne trouvez pas ces exports, envoyez-moi une capture
de la page ou le fichier obtenu, j'adapterai le lecteur.

### 3. Soldes ailleurs

Un livret dans une autre banque ? Saisissez son solde dans **Revenus & épargne › Saisir un solde à la main**.

### Où mettre les fichiers

- soit via la page **Données & imports › Importer des CSV** (glisser-déposer) ;
- soit en les copiant dans `data/reel/inbox/boursorama/` puis `python -m finmon import`.

Les fichiers importés sont archivés dans `data/reel/archive/`. Rien n'est envoyé sur Internet.
