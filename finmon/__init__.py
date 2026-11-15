"""finmon — moniteur local de patrimoine, investissements et dépenses.

Tout tourne sur la machine : les données sont importées depuis des fichiers
(exports Boursorama, pytr pour Trade Republic) dans une base SQLite locale.
Les seules requêtes réseau sont les cours et taux de change publics (Yahoo Finance).
"""

__version__ = "0.1.0"
