# Audit du 2026-09-01 — publiabilité `1.0`

Lecture seule sur `main` à `ff38bbb`. Constats seulement : le plan est
`docs/PLAN.md` et cet audit n'en porte pas, conformément à `CLAUDE.md`.

**Ce qui a été exécuté ici**, et non lu dans un rapport : la suite
(`1875 passés, 1 ignoré`, les 5 échecs restants tous dans le seul fichier
qui exige Pillow, extra `[vision]` non installé) ; `mypy --strict` sur les
78 fichiers (`Success`) ; `ruff check` et `ruff format --check` à la
version que la CI épingle (`0.15.14` — propre). Les ratios de prose sont
mesurés par `ast` + `tokenize`, pas par `grep`, et le même outil est
rejoué sur trois commits pour que la tendance ne dépende pas de la
méthode.

---

## 1 — Aucune grosse branche en attente

Huit branches distantes, **une seule PR ouverte** : `#162`
(`couverture-tranchee`), 1 fichier, +39 lignes de `docs/AUTOPILOT.md`.

| branche | commits | état réel |
|---|---|---|
| `claude/repo-technical-audit-1afr82` | 21 | **arbre identique à `main`** — vagues `RS`+`G`, squash-mergées en `#163` |
| `claude/a2b-a-refused-edit-is-visible` | 650 | histoire pré-réécriture, sans base commune ; `A2b` est dans `main` |
| `ligne-source-vide` | 2 | son `validator.py` est identique à `main` (`#161`) ; ne reste qu'un diff de doc |
| `phase4-complete`, `phase4-brique1-integration`, `promesses-etat-perime` | 1 ch. | **en retard** sur `main` : leur diff *retire* du contenu que `main` porte |
| `couverture-tranchee` | 1 | la PR `#162`, 39 lignes de doc |

La branche qui inquiète — 91 fichiers, +5493/−753 — est **déjà dans
`main`**. Rien n'est en attente d'être mergé, et les six branches
tree-différentes sont des restes à supprimer, pas du travail perdu.

## 2 — La porte `0.10.0` est tenue ; `1.0` tient à deux critères

`V1`, `V2`, `V3`, `V8`, `V9` sont tenus et vérifiés par le dépôt lui-même.
`V4` est tenu depuis le 2026-08-27, `V5` et `V7` le sont. Restent :

- **`V6`** — la campagne de variance post-correctif, le chemin inter-pages
  qu'aucun run ne mesure, deux ventilations. **Tout s'exécute sur `cinoc`**,
  pas ici : ce dépôt ne porte plus de banc.
- **`V10`** — la revue humaine externe de l'API publique.

Rien de tout cela n'est de la dette de code. Ce qui bloque une publication
`0.10.0` **aujourd'hui** est mécanique et hors-code : déclarer le *trusted
publisher* sur pypi.org et test.pypi.org sur le **nom de fichier** du
workflow (il a changé au renommage), créer les environments GitHub
`testpypi`/`pypi`, puis `P2`. Ce sont des actions de mainteneur.

## 3 — Le seul défaut mécanique trouvé : `ValueError` absorbe les bugs

`core/attempt.py:86` met `ValueError` dans `_RECOVERABLE_ERROR_TYPES`, et
le `try` de `_attempt_chunk` (l. 517) enveloppe `_produce`,
`_script_to_raw`, la comptabilité d'usage **et** `_validate_and_capture`.
Tout `ValueError` levé dans ce périmètre — quelle qu'en soit l'origine —
est traité comme une sortie producteur malformée.

Reproduit en injectant un `ValueError` depuis du code **interne** (pas
depuis le producteur) :

```
référence : fallback=3   reasons={'too_different_from_source': 3}
injecté   : fallback=10  reasons={'all_attempts_exhausted': 10}
run() retourne normalement
```

Dix lignes retombent sur l'OCR, la cause est **imputée au producteur**, et
l'appelant reçoit un résultat réussi. C'est le scénario qu'`ADR-008` dit
vouloir empêcher : *« an unknown exception must never become a
silently-uncorrected "success" »*. L'intention de l'ADR est plus étroite
que son implémentation.

Deux amplificateurs, tous deux vérifiés :

1. `pydantic.ValidationError` **hérite de `ValueError`** (2.13.5). Toute
   construction de modèle qui casse dans ce périmètre prend la même sortie.
2. `traces._set_trace(**fields: object)` fait un `setattr` sur un modèle
   pydantic, donc `mypy --strict` ne peut pas voir une faute de frappe, et
   pydantic la refuse **en `ValueError`** :
   `"LineTrace" object has no field "projetced_text"`. Une coquille dans un
   nom de champ de trace devient donc un repli OCR attribué au modèle.

`docs/PLAN.md:2598` déclare l'allowlist `ADR-008` « intacte » comme
non-cible de vague : ce point n'est pas un arbitrage rendu, c'est un angle
mort.

## 4 — La provenance ne couvre pas ce qui peut changer les octets

`config_fingerprint()` (`core/pipeline.py:281`) agrège exactement cinq
politiques : `chunk_planner`, `guard`, `loss`, `pairing`, `retry`.
N'y sont pas : `routing_policy`, `review_policy`, `qe_scorer`,
`confidence_policy`.

Or `routing.py:204` fait du texte OCR le texte final d'une ligne `SKIP`.
Deux runs aux seuils de routage différents livrent donc des octets
différents **sous la même empreinte**. La docstring de `RoutingPolicy`
connaît le sujet et écrit que la politique n'y entre « pas tant qu'un run
n'a pas effectivement sauté ou escaladé une ligne » — mais le code ne
l'ajoute conditionnellement nulle part.

**Portée réelle, à ne pas surestimer** : les deux bornes valent `None` par
défaut et le routage exige un scorer. C'est un défaut d'un chemin
expérimental, pas du chemin nominal.

## 5 — La prose : le stock est défendable, le flux ne l'est pas

Mesure au 2026-09-01 sur `src/` : **9 537 lignes de code, 8 189 de prose**
— soit **46 % de chaque fichier**, ratio 0,86.

Le plan a déjà tranché que la cible « ≤ 0,45 » était fausse, et il a
raison : la composition le montre.

| catégorie | lignes | statut |
|---|---|---|
| docstrings de fonction | 3 259 | référence d'API |
| docstrings de classe | 1 102 | référence d'API |
| commentaires `#:` de champs publics | 1 024 | référence d'API |
| docstrings de module | 1 334 | contexte |
| commentaires simples | 1 470 | contexte |

**66 % de la prose est la référence d'API** : ce que signifie un champ de
`CorrectionReport`, ce que refuse une garde. La couper reviendrait à
publier une bibliothèque sans documentation de surface.

Le constat neuf est ailleurs — dans la **tendance**, mesurée avec un outil
unique sur trois commits :

| commit | date | code | prose | ratio |
|---|---|---|---|---|
| `4b59394` (avant `RS`) | 21 août | 9 207 | 7 702 | 0,837 |
| `2be945e` (`RS` close) | 27 août | 9 257 | 7 785 | **0,841** |
| `ff38bbb` (`main`) | 1ᵉʳ sept. | 9 537 | 8 189 | **0,859** |

Deux choses en découlent :

1. **La vague `RS` n'a pas fait baisser la prose.** Elle visait le récit de
   migration, l'a retiré, et le ratio a *monté* de 0,004. Le plan le dit
   lui-même en le mesurant autrement (0,844 → 0,838) ; les deux méthodes
   s'accordent sur le fait qu'il n'a pas bougé.
2. **Le taux marginal est le double du taux moyen.** Depuis la clôture de
   `RS` : +280 lignes de code, +404 lignes de prose, soit **1,44 ligne de
   prose par ligne de code neuve**, contre 0,86 en stock.

C'est la réponse mesurée à l'impression « ça croule sous les
commentaires » : le stock accumulé est justifié, mais chaque vague écrit à
un régime qui fait dériver le ratio vers le haut. Ce n'est pas un problème
de nettoyage, c'est un problème de débit.

## 6 — La fragmentation modulaire, elle, est réelle

`core/` : 43 modules pour 5 709 lignes de code, **médiane 127 lignes**.
**16 modules portent moins de 80 lignes de code** :

```
  10 l.  workspace.py      22 l.  context.py     29 l.  traces.py
  15 l.  _parse.py         22 l.  losses.py      29 l.  redaction.py
  38 l.  _norm.py          45 l.  projection.py  47 l.  indexing.py
  51 l.  page_alignment.py 54 l.  fidelity.py    61 l.  retry.py
  65 l.  finalize.py       65 l.  quality.py     72 l.  batching.py
  74 l.  provenance.py
```

`workspace.py` porte **10 lignes de code et 56 lignes de prose**. C'est la
forme concrète de la surarchitecture dans ce dépôt : pas des classes
obèses, mais un émiettement — et il alimente directement le constat 5,
puisque chaque module coûte sa docstring de module (1 334 lignes au total).

## 7 — Dérives documentaires mineures

`saknussemm.__all__` compte **68 symboles**. `docs/PLAN.md` écrivait « 67 »
en trois endroits (l. 44, 2130, 2293). Le 68ᵉ est `ReviewPolicy`, rendu
atteignable par la vague `G` depuis un paramètre public : croissance par
clôture, comme `RefusedEdit` en `A2b`, et non accrétion.

`_smoke_imports.py` n'épingle aucun nombre, donc rien n'échouait — mais
`V8` (« aucun document normatif ne décrit un périmètre faux ») porte
précisément sur ce genre d'écart. **Corrigé le 2026-09-02.** La fiche `P1`
cite elle aussi « 67 symboles publics » et reste inchangée à dessein :
c'est le relevé daté de la répétition du 2026-08-01, vrai ce jour-là.

## 8 — Ce qui est sain, et qu'il ne faut pas ouvrir

- **`mypy --strict` propre sur 78 fichiers**, `ruff` propre à la version
  épinglée. La CI épingle `ruff==0.15.14` ; avec `0.16.5` on voit 358
  écarts qui sont de la dérive de version, pas des défauts.
- **Les réécriveurs ALTO/PAGE.** La complexité vient du format. Le corpus
  de parité octet est la condition écrite avant d'y toucher, et elle n'est
  pas levée.
- **Le planner et la césure.** Atomicité des unités, inter-pages, chaînes
  de 3+ : complexité essentielle.
- **`decide.py` écrivain unique.** Le test d'exclusivité protège une
  propriété sémantique, pas une métrique de taille. À garder.
- **Le compteur d'arité/longueur, dans sa forme actuelle.** Depuis
  `RS-4.2` une inscription exige une raison écrite d'au moins 40
  caractères. C'est la correction de l'incitation qui avait produit
  `PageWorkspace` — le dépôt a diagnostiqué « la métrique devenue
  architecture » et a changé le compteur plutôt que l'objet.

## 9 — Verdict

Le dépôt **n'est pas en train de se dégrader**. Les portes `0.10.0` sont
tenues, la suite et le typage sont propres, aucune grosse branche ne
traîne, et la seule PR ouverte fait 39 lignes de documentation.

Il est **surarchitecturé sur un axe précis et un seul** : l'émiettement de
`core/` (16 modules sous 80 lignes de code), qui achète de la testabilité
unitaire au prix d'un chemin nominal qu'on ne peut plus lire dans un
fichier. Ce n'est pas une accumulation d'abstractions inutiles — c'est une
seule décision, prise plusieurs fois.

Sur la prose, la critique courante est **fausse sur le stock et juste sur
le flux**. 66 % est de la référence d'API qu'une bibliothèque publiable
doit porter. Mais le régime d'écriture des dernières vagues (1,44) fait
monter le ratio à chaque livraison, et personne ne le mesure en continu.

Le seul défaut qui puisse produire un mauvais fichier chez un utilisateur
est le `ValueError` du constat 3. C'est le seul point de cet audit qui
mérite une correction avant publication ; tout le reste est de la lisibilité
et de la vérité documentaire.
