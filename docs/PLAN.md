# Saknussemm — plan de route unique

**C'est le seul document de planification vivant du dépôt.** Il remplace
`docs/history/PLAN-1.0-2026-07-15.md`, `docs/history/ROADMAP_LIB_V3.md` et la section §13
« plan de livraison » de `SPECS_LIB_V2.md`, tous trois déplacés ou marqués comme
historiques. Ne pas en écrire un second ; ne pas ressusciter les anciens.

Répartition des rôles, à tenir :

- **`SPECS_LIB_V2.md`** dit ce que la bibliothèque **doit être** (contrats,
  invariants, formats). Normatif. Ne contient plus de calendrier.
- **Ce document** dit ce qui **reste à faire** et dans quel ordre.
- **`docs/audit/`** dit ce qui a été **constaté**, avec les preuves. N'y ajouter
  aucun plan. Deux relevés courants : `AUDIT-2026-07-25.md` (première mesure
  réelle) et `AUDIT-2026-07-27.md` (contre-audit d'une analyse externe).
- **`docs/history/`** est gelé. Ne jamais s'y fier pour l'état courant, et ne
  jamais y renvoyer depuis un document normatif.

Dernière mise à jour : 2026-08-16 — dix arbitrages qui redécoupent le
périmètre (§ « Décisions déléguées — 2026-08-16 »). Ils ne rouvrent aucun item
et n'en ferment aucun : ils sortent de ce dépôt la démo, le banc et les corpus,
et déplacent l'exécution de la mesure vers `cinoc`. Révision précédente :
2026-08-06, après un audit structurel externe (§ `RM`).
Cette révision **ne change ni le diagnostic ni les priorités** : elle ajoute une
vague `RM` de dette *structurelle* — un défaut latent, un instrument de mesure
faussé, et de la réduction — qui ne ferme aucun item `L`, `R` ou `M` mais rend
`S1` praticable. Révision précédente : 2026-07-27, contre-audit d'une analyse
externe, qui relevait le niveau de trois réponses (`L`, `S1`, tests), ajoutait
quatre items de vérité documentaire, et écrivait la règle de gel.

---

## Objectif : `0.10.0`, puis `1.0.0` — jamais l'inverse

Publier une `0.x` honnête plutôt qu'une `1.0` prématurée. Les raisons ont
changé, contrairement à ce que ce paragraphe a longtemps annoncé : il
présentait « trois raisons inchangées » dont la première était close depuis
le 2026-08-01, et le disait quinze pages plus bas. Relevé par la revue
externe du 2026-08-16. Ce qui reste :

1. Les gardes ne sont pas calibrées ; le code le dit lui-même
   (`GuardConfig.vision()`, seuil « safe default, not a calibrated one »).
2. Un seul modèle, un seul profil de gardes, deux runs mesurés.
3. La surface publique **est** close, à 67 symboles (`S3b`, fait le
   2026-08-01, affiné par `RM-04` le 2026-08-06 — voir `V5`). Elle n'est
   donc plus un travail à faire, mais elle n'a jamais été relue par
   quelqu'un d'extérieur à sa construction, ce qu'exige `V10`. Publier
   `1.0` la gèlerait sous SemVer avant cette relecture.

`docs/versioning.md` autorise déjà explicitement la série `0.9.x` à casser.

### Ce que « v1 propre » veut dire

`1.0.0` n'est **pas** la fin de la liste ci-dessous ; c'est un ensemble de
propriétés tenables. Critères de sortie, à ne pas négocier à la baisse :

| # | critère | vérifié par |
|---|---|---|
| V1 | Aucune altération du texte livré qui ne soit **déclarée et comptée** | `L*` fermés, échelle de fidélité au rapport |
| V2 | La comptabilité des pertes ne produit **ni fantôme ni angle mort** | `R*` fermés, matrice versionnée |
| V3 | Une **seule** définition de l'unité de césure dans tout le code — **atteint** : une famille de primitives dirigées (`core/pairing.py`, seul lecteur des champs pointeurs) + une dérivation d'unité (`core/units.py`), et la cohérence des pointeurs est tenue par l'invariant de symétrie | fait |
| V4 | Ce que le système **ne peut pas** établir est signalé, pas décidé | **tenu (2026-08-27)** — `review_required` livré, `G1`-`G3` clos ; les trois règles que le moteur ne peut pas alimenter sont écrites plutôt que déclarées |
| V5 | La surface publique est la clôture de ce que la façade retourne | `S3b` fermé (`S3a`, son statut provisoire écrit, est fait) |
| V6 | Toute revendication chiffrée est un **intervalle**, sur ≥2 familles de modèles, dont le chemin inter-pages | `M*` fermés |
| V7 | Un corpus externe versionné **bloque** un merge | **tenu (2026-08-16)** — `tests/external_corpus/pinned/` porte trois pages Gallica réelles, dans la suite par défaut, sans marqueur ni saut |
| V8 | Aucun document normatif ne renvoie vers `docs/history/` ni ne décrit un périmètre faux | `D*` fermés |
| V9 | Licences des corpus tranchées | `Gate 0` |
| V10 | Revue humaine externe indépendante de l'API publique | `P3` |

`V1`-`V3`, `V8`, `V9` sont exigibles dès `0.10.0`. `V4`-`V7`, `V10` sont la
distance restante entre `0.10.0` et `1.0.0`.

---

## Décisions déléguées — 2026-08-11

Le mainteneur a délégué quatre arbitrages qui bloquaient la suite. Ils sont
tranchés ici, avec leur raison, et **chacun est réversible en modifiant ce
paragraphe** — c'est le seul endroit qui les porte.

Le fait qui les commande toutes : **rien ne sera publié avant une v1 aboutie.**
Cela retire l'urgence de taguer et rend gratuites les ruptures de la série
`0.x`, qui n'atteindront jamais un consommateur.

**1. Le gel est levé sur son critère, et remplacé par une contrainte plus
étroite.** Sa condition d'origine — « tant que `L*` et `R*` ne sont pas
fermés » — **est atteinte** : `R0`-`R8` clos le 2026-07-28, `L0`-`L10` clos
sauf deux résidus de `L5` que ce plan qualifie lui-même de non-correctifs. Le
lever tel quel rouvrirait pourtant la porte que la suite doit garder fermée,
alors une règle plus précise le remplace.

**Reformulée le 2026-08-13.** La première rédaction disait « aucune extension
de la surface publique **tant que `S3b` n'a pas coupé** » — et `S3b` avait
coupé le 2026-08-01, donc la contrainte censée remplacer le gel ne
contraignait rien. Corrigée en ce qu'elle voulait dire :

> **La surface publique EST à sa clôture calculée. L'étendre est une décision
> explicite, jamais un effet de bord** : elle passe par
> `test_public_api_snapshot` (qui refuse qu'elle grandisse),
> `test_public_surface_is_the_closure` (qui recalcule les deux promesses), le
> `CHANGELOG` et `docs/versioning.md` — dans le même commit.

Les deux corollaires permanents sont conservés : aucun 6ᵉ chemin de résolution
de partenaire, et aucune revendication chiffrée sans `M2` + `M3`.

**2. Pas de publication intermédiaire.** La question « publier `0.10.0` puis
couper, ou couper puis publier » est éteinte deux fois : par la décision de ne
publier qu'une v1 finie, et par le fait que **la coupe est déjà faite**
(2026-08-01). La seconde moitié de cette décision — « `S3b` passe avant tout
tag » — était donc satisfaite avant d'être écrite ; elle est retirée plutôt
que gardée comme une condition qui se lit encore comme un travail à venir.

Ce qui reste, et qui est la seule règle active : **aucun tag avant une v1
aboutie.**

**3. `RM-08` est découplé de `S1`.** Il attendait `S1` au motif qu'unifier les
projections avant que l'unité soit autoritaire produirait une 6ᵉ formulation
au lieu d'en retirer cinq. Le motif tient **si** la fusion touche au stockage.
Elle est donc autorisée sous condition explicite : **les champs pointeurs
restent la vérité, on retire des lectures redondantes, on n'en ajoute
aucune.** Si la fusion exige de rendre l'unité autoritaire, elle s'arrête —
c'est `S1`, et le point 4 le parke.

**4. `S1` reste parké, et ce n'est pas une nouvelle décision.** Ce plan l'a
déjà tranché le 2026-07-27 : `V3` est reformulé et **atteint**, l'écart
restant est surveillé par trois tests, et le refactor est « le plus gros
risque de régression du dépôt, sur la partie la plus chargée du moteur, pour
fermer un écart déjà surveillé ». À rouvrir seulement si `S2` l'exige. Le
rappel est ici parce que `CLAUDE.md` décrit l'écart sans dire qu'il est
délibérément laissé ouvert, ce qui se lit comme du travail en attente.

**5. ~~La porte avancée est publique~~ — ANNULÉE le 2026-08-12, sans avoir
été exécutée.** Elle reposait sur une mesure fausse (voir §`S3` « Mesure du
2026-08-11 — rétractée ») : les neuf « trous » sont un troisième seam laissé
ouvert **par écrit**, et `S3b` était déjà fait depuis le 2026-08-01.

Ce que l'épisode laisse, et qui est plus utile que la décision annulée :

- une garde qui **recalcule** les deux clôtures au lieu de faire confiance à
  la liste épinglée ;
- la règle de méthode : *on amorce une clôture de surface publique avec les
  promesses de la bibliothèque, jamais avec les boutons optionnels d'un
  constructeur* ;
- et un rappel sur la délégation elle-même. Une décision déléguée reste une
  décision : celle-ci a été prise vite, sur une mesure d'une heure, contre
  deux décisions documentées que je n'avais pas lues. La délégation autorise
  à trancher ; elle n'autorise pas à trancher sans avoir lu.

**Ce qui n'est pas délégué et ne le sera pas ici** : le budget des runs
(`M2`/`M3`), les licences de corpus (`M5`/`M6`), la conception de
`review_required` (`G*`), et le tag de publication. Ils passent par le CLI —
voir `docs/AUTOPILOT.md`.

---

## Décisions déléguées — 2026-08-16

Dix arbitrages, pris par le mainteneur après une revue d'état complète et une
cartographie de `cinoc`. Ils **ne rouvrent aucun item `L`, `R`, `S` ou `RM`**
et ne contestent aucun constat. Ils déplacent des frontières : ce que ce dépôt
contient, où la mesure s'exécute, et ce qui vaut publication. Comme le bloc du
2026-08-11, chacun est réversible en modifiant ce paragraphe.

**1. Trois dépôts, un seul livrable.** `saknussemm` est la **bibliothèque, et
rien d'autre**. Deux dépôts la servent sans en faire partie : `cinoc` (le banc,
qui existait déjà et que personne ici n'avait relié au projet) et
`saknussemm-demo` (la démo web, qui sort d'ici). La règle de dépendance de
`CLAUDE.md` est inchangée et s'étend : **les deux importent la bibliothèque,
jamais l'inverse.**

**2. La démo part maintenant, pas « à la forme finale ».** `backend/`,
`frontend/`, `tools/e2e/`, `Dockerfile`, `docker-compose.yml` (parti avec la démo le 2026-08-16), `docs/API.md` (jamais créé ; voir `CONTRIBUTING.md`),
`SECURITY.md` et le workflow HF Spaces s'en vont dans `saknussemm-demo`.
`SECURITY.md` disait déjà « la démo se retire quand la bibliothèque atteint sa
forme finale » — la date était la seule chose qui manquait. Effet de bord
gratuit : le workflow `Sync to HF Spaces`, **rouge à chaque push depuis au
moins le 2026-08-14** parce que Hugging Face refuse les PNG de corpus, part
avec ce qu'il déployait.

**3. Le banc local est RETIRÉ, pas déménagé.** `scripts/vision_benchmark.py`
(759 l.), `benchmark.py`, `run_vision.py`, `providers_multimodal.py`,
`audit_run_lines.py` ne sont pas portés ailleurs : `cinoc` fait la même chose
avec 24 métriques au lieu d'une, des tests de significativité, et une métrique
validée à 1e-9 contre le scorer HIPE officiel. **Porter un instrument dont on
vient de prouver qu'il fausse ses propres résultats serait porter le défaut
avec.** Les corpus (`corpus/`, 43 Mo) et les campagnes (`measurements/`) le
suivent : la GT ALTO+images de `37-GT-BNL` est exactement la couche
structurelle qui manque au corpus texte que `cinoc` possède déjà sur la même
source.

**4. `saknussemm` devient une brique du socle de `cinoc`**, derrière un extra
`cinoc[saknussemm]`, comme les 19 autres moteurs — et non un plugin tiers. Un
plugin tiers est **refusé en mode public par conception** là-bas, donc il
n'apparaîtrait jamais dans la vitrine ; or la comparaison « OCR→LLM nu » contre
« OCR→saknussemm(LLM) » est la démonstration la plus directe de ce que cette
bibliothèque apporte.

**5. Le module réutilise la couche fournisseur de `cinoc`.** Le module prend un
paramètre `llm=<adapter>` plutôt que d'embarquer ses propres clients : il
hérite ainsi des quatre fournisseurs, du cap de concurrence réseau, des retries
429 et des seize prompts curés par période.

**6. Le scorer QE part au banc — fait le 2026-08-16.** `integrations/qe.py` et ses quatre scripts
rejoignent `cinoc`. La question que le scorer pose — « est-ce que ça vaut le
coup d'appeler le modèle sur cette ligne ? » — est **économique**, et `cinoc`
porte déjà une section de rapport économie (coût, débit, Pareto, coût
marginal). Ce dépôt garde le **protocole** `QEScorer`, qui est le point
d'injection ; il perd une implémentation qu'aucune CI n'exécute, dont les tests
se sautent partout, dont la calibration presse-19e est provisoire, et dont le
bundle de 545 Mo n'a **aucun canal de distribution** — `pip install
saknussemm[qe]` livre aujourd'hui un extra inutilisable.

**7. `0.10.0rc1` avant `0.10.0`, et le tag n'est pas une exigence de PyPI.**
Vérifié : ni PyPI, ni TestPyPI, ni l'OIDC ne demandent de tag. C'est
`.github/workflows/publish-saknussemm.yml` qui l'exige, dans une étape écrite
exprès pour qu'un `workflow_dispatch` distrait ne publie pas ce que `main`
pointe. La contrainte est donc **la nôtre**, et négociable. Elle n'est pas
levée : on tague un `rc` de répétition. Ce qui ne se reprend pas n'est pas le
tag (`git tag -d` suffit) mais le **numéro consommé sur l'index** — d'où le
`rc`, qui répète sans dépenser `0.10.0`. La décision n°2 du 2026-08-11
(« aucun tag avant une v1 aboutie ») **tient** : un `rc` de répétition
TestPyPI n'est pas la publication d'une version.

**8. La borne de `T1`/`T3` cesse d'être un compteur.** *(La liste est
établie : `docs/promises.md`, relevé du 2026-08-16 — 9 promesses sans
aucune garde, 14 partielles, et deux trous d'IMPLÉMENTATION plutôt que de
test. Le motif dominant est que PAGE est le format sous-gardé : six
promesses passent de tenue à partielle pour cette seule raison.)* Le compteur mesurait
l'effort, pas la couverture, et il butait sur une question qu'il ne pouvait pas
trancher : deux des cinq propriétés n'avaient trouvé aucun défaut du produit
mais un **angle mort de la suite entière** — une mutation réaliste que les 1400
autres tests laissaient au vert. Remplacé par une **liste finie** : *chaque
promesse vérifiable énoncée dans `SPECS_LIB_V2.md` a au moins une propriété
métamorphique ou différentielle qui la garde, prouvée par mutation.* Quand la
liste est couverte, `T1`/`T3` est **clos**, pas épuisé. Premier geste de
l'item : établir la liste des promesses, qui est aussi un livrable citable
pour la revue externe `P3`.

**9. Périmètre sur `cinoc`.** On n'y touche que pour ce que l'intégration
exige, et on y réconcilie le journal **pour les parties touchées seulement**.
Ce dépôt-là a sa propre dette — 31 commits non journalisés, aucun tag git, sa
1.0 non coupée — qui reste au calendrier de son mainteneur. Réconcilier avant
de toucher n'est pas négociable : c'est la règle n°6 de `docs/AUTOPILOT.md`,
et `cinoc` en a besoin plus encore qu'ici.

**10. `M3` se fait en local, à coût nul.** Voir la section `M`. Cela retire la
dernière dépendance budgétaire de la route vers `1.0.0`.

**Ce qui n'est pas délégué et ne l'est toujours pas** : la surface publique,
toute dépense au-delà du plafond convenu, et tout tag ou publication. S'y
ajoute la **liste des corpus à télécharger**, qui est un choix de projet et non
un critère technique.

---

## Décisions déléguées — 2026-08-25

Un seul arbitrage, et il conditionne `RS-5`.

**Sortir le routage QE, l'escalade et la confiance du chemin chaud est
autorisé, sous trois conditions cumulatives.** Le motif : `driver` connaît
aujourd'hui le score de qualité, le producteur d'escalade et le plafond
d'images, et `_plan_page_chunks` fait lire ces trois étapes avant le cas
nominal — alors qu'aucune des trois ne s'exécute par défaut. C'est de la
réduction, et la règle de gel autorise la réduction.

Les trois conditions, ensemble :

1. **Comportement identique, prouvé par les octets.** Les digests du golden
   ne bougent pas, et un run routé de référence — compteurs `lines_skipped`,
   `escalated_lines`, `producer_calls` épinglés avant la phase — donne les
   mêmes nombres après.
2. **Aucune extension de surface publique.** La couture reste à son chemin de
   module ; `test_public_api_snapshot` reste vert **sans modification**.
   C'est la contrainte permanente de la décision n°1 du 2026-08-11, et elle
   n'est pas assouplie ici.
3. **Aucune nouvelle politique de routage.** Le travail déplace ce qui
   existe. Une variante de routage, même meilleure, sort du périmètre et du
   gel.

**Ce qui est refusé d'avance** : faire du routage un simple décorateur
d'`EditProducer`. La forme est séduisante et elle détruit ce que le mode
existe pour prouver — un `EditProducer` reçoit une requête, pas un plan de
chunks, donc un chunk entièrement `SKIP` serait quand même construit et
`producer_calls` cesserait de mesurer l'économie. La couture autorisée est au
niveau du **plan** (une méthode `route(chunks) -> [(chunk, producer)]`), ce
qui est un déplacement pur.

Réversible en modifiant ce paragraphe, comme les précédents.

---

## B — Le premier vrai run, 2026-08-18

**24 592 lignes de presse Gallica passées par `mistral-small`, un job à la
fois.** C'est la première fois que la bibliothèque est mesurée contre un
modèle réel à cette échelle, et ça a corrigé plus d'affirmations que tout
l'audit précédent — y compris plusieurs des miennes.

### Ce que le corpus est

28 pages, six fascicules de quatre titres, **24 592 lignes, 8 433 couples de
césure, 6 000 blocs**, domaine public. Fourni, pas cherché. Il porte deux
formes de dégradation qui ne se règlent pas pareil : uniforme (médiane de
confiance 0,55) et localisée (médiane 0,99 avec 94 mots à 0,00).

**Il n'a AUCUNE vérité terrain.** Son `text.txt` est la même couche OCR que
l'ALTO, et il est en plus mal encodé là où l'ALTO est correct. Il mesure donc
le *comportement* et le *coût* avec précision, jamais la *justesse*.

### Le résultat, `mistral-small`, texte

| | |
|---|---|
| corrigées | **13 928 / 21 125 = 66 %** |
| texte réellement changé | 4 978 lignes |
| tokens | 5,71 M in / 1,50 M out |
| coût | **1,02 $** |
| **pages perdues** | **4** — aucun fichier produit |

Les refus, par cause :

| cause | lignes |
|---|---|
| `all_attempts_exhausted` | 2 728 |
| `hyphen_pair_fallback` | **2 271** |
| `too_different_from_source` | 1 491 |
| voisinage + absorption | 634 |
| migration de frontière | 63 |

### Ce que la qualité déclarée prédit

| pages | médiane WC | corrigées | perdues par la césure |
|---|---|---|---|
| dégradées (n=5) | 0,50 – 0,94 | **46 %** | **12 – 28 %** |
| propres (n=19) | 0,99 – 1,00 | **68 %** | 7 – 11 % |

**Le coût de la césure triple sur les pages dégradées** — mécaniquement :
plus l'OCR est mauvais, plus la correction est ample, donc plus elle touche
le mot de la couture et contredit le `SUBS_CONTENT` déclaré. C'est là que le
réglage a de la valeur, pas sur le seuil de similarité.

### Quatre erreurs de méthode, consignées parce qu'elles se reproduiront

1. **Un producteur à règles ne peut pas exercer la garde qu'il déclare
   inerte.** Il ne fait que des substitutions locales, donc sa sortie reste
   par construction proche de la source. Il ne peut pas *halluciner* — et
   c'est ce que la garde arrête. Le document d'audit qui en tirait ses
   conclusions a été retiré (#124).
2. **Trois jobs en parallèle sur un compte à quota mesurent le quota.** Les
   429 devenaient des replis de chunk puis des `all_attempts_exhausted` : sur
   la même page, 37 % de corrections à trois jobs contre **67 % seul**. Les
   deux tiers de mes échecs venaient de là.
3. **Réimplémenter au lieu de lire les dépôts consommateurs.** Le mauvais
   prompt, la page entière au lieu des découpages, les gardes texte sur un
   run vision, le plafond de 8 images — les quatre étaient déjà documentés
   dans `cinoc/campaigns/tooling/providers_multimodal.py`, dont un commentaire
   cite mot pour mot l'erreur 3051 que je me suis prise.
4. **Comparer un bras texte à un bras vision.** Le reproche tient — les deux
   bras ne mesurent pas la même chose — mais la justification que j'en avais
   tirée était **fausse, et corrigée le 2026-08-20** : « la campagne BNL dit
   elle-même que son mode texte fait 0 improved, 0 degraded ». Sa ligne
   « text » n'est pas un LLM. C'est `default_french_ocr_rules`, un producteur
   **déterministe à trois substitutions** — le `ſ` long et les ligatures
   `ﬁ`/`ﬂ` — passé sur un corpus BNL majoritairement **allemand en Fraktur**
   (140 lignes) et français du XIXᵉ (313), où aucune des trois n'apparaît.
   Zéro correspondance, donc zéro changement : le résultat attendu, et il ne
   dit **rien** d'un LLM en mode texte.

   Ce que le dépôt mesure vraiment sur le bras texte le contredit d'ailleurs :
   sur le corpus Gallica, `mistral-small` en texte pur livre **28 à 38 %** des
   lignes corrigées. Lire « text » dans un tableau et conclure « le mode texte
   ne sert à rien » est une faute de lecture, et elle a servi à ne pas relancer
   ce bras.

### Ce que le run a trouvé et que rien d'autre n'aurait trouvé

- **Deux pages tuées par un invisible retiré exprès** (#125) : `clean_content`
  supprime U+00AD à l'écriture, comme prévu, et l'échelle de fidélité n'avait
  aucun niveau pour ça — donc `ProjectionError` et page perdue.
- **Une page tuée par un mot soudé à sa marque de coupure** (#126), reproduite
  et laissée ouverte : le correctif touche la mise en page géométrique, et s'y
  tromper est pire que le défaut.
- **`all_attempts_exhausted` ne distingue pas l'étranglement de l'incapacité.**
  Un 429 soutenu épuise les tentatives et sort le même code de raison qu'un
  modèle qui n'y arrive pas. Un exploitant conclut que son modèle est mauvais
  alors que son quota est saturé. Reste ouvert.
- **`mistral-small` est instable**, pas seulement moins bon : la même page,
  même config, a donné 72/72 puis 3/72. `mistral-medium` fait 72/72 sans un
  refus.

### Le mode « une page, un appel »

Mesuré, pas estimé. L'enveloppe JSON par ligne pèse **7,9 fois** le texte
qu'elle transporte, parce que chaque `LineContext` porte `prev_text`,
`ocr_text` **et** `next_text` — le texte de chaque ligne est donc transmis
trois fois.

| mode | appels | entrée | coût |
|---|---|---|---|
| par chunk (actuel) | ~2 000 | 5,49 M | 1,11 $ |
| par ligne + découpages | ~3 100 | ~7,1 M | 1,28 $ |
| **par page** | **28** | **0,39 M** | **0,14 $** |

Et le découpage par ligne coûte **15,8× plus** en tokens d'image que la page
entière (36 610 contre 2 310 sur une page de 555 lignes), parce que le
tokeniseur facture un plancher par image.

Le mode page supprimerait aussi `all_attempts_exhausted` par construction :
plus de contrat JSON par ligne, donc plus de réponse invalide qui fait
retomber un chunk. Ce qu'il déplace : le risque passe de « le modèle a
halluciné » — que les gardes voient — à « l'aligneur a posé le bon texte sur
la mauvaise ligne ». Guardable, et par une garde qui existe déjà : un
décalage d'une ligne effondre `min_source_similarity` sur toutes les
suivantes.

C'est un **producteur**, donc aucun changement du cœur. Le travail neuf est
l'aligneur et son test de désalignement.

## C — Finir le mode actuel, puis ouvrir le second — plan du 2026-08-19

Écrit après une **contre-analyse** de ma propre analyse, exigée parce que la
première version était affirmée sans preuve. Sept constats sur dix ont bougé.
Ce qui suit ne garde que ce qui a été prouvé par lecture du code ou par
exécution, et **nomme les réfutations** plutôt que de les effacer : la
première version de ce plan est elle-même une des choses que la mesure a
corrigées.

### Ce que la contre-analyse a réfuté

| affirmation de la 1ʳᵉ analyse | verdict |
|---|---|
| le défaut de la marque est **bidirectionnel** | **faux** — unidirectionnel ; la 1ʳᵉ analyse contredisait `AUTOPILOT.md:368`, qui disait juste |
| les deux sites `_append_trailing_hyp` doivent être réconciliés | **hors sujet** — le second n'est atteint que sur décision vide, qui ne peut pas porter d'espace |
| chantiers « marque soudée » et « rayon d'action » indépendants | **faux** — la marque soudée *est* la page perdue |
| « le correctif touche la géométrie, s'y tromper est pire » | **réfuté par prototype** — la géométrie pave sans effort |
| `align_tokens` est réutilisable à 80 % pour le mode page | **faux** — ~30 %, et le mode page saturerait la mémoire avant d'être lent |
| population du défaut négligeable | **non mesurée** — 29 % des fichiers d'un fonds réel |

### `C1` — La marque soudée (`#126`) — **priorité 1**

**Ce que c'est, prouvé.** Le chemin lent supprime l'espace qui précède la
marque de coupure. Balayage de six décisions sur la forme réelle (le fixture
de `tests/test_a_break_mark_must_not_weld_to_its_word.py`, tiré de la ligne
Gallica qui a tué une page) :

| décision | chemin | artefact | fidélité |
|---|---|---|---|
| `'et d -'` | untouched | `'et d -'` | exact |
| `'et d-'` | lent | `'et d-'` | exact |
| `'à la révision et d -'` | lent | `'à la révision et d-'` | **`None`** |
| `'à la révision et d-'` | lent | `'à la révision et d-'` | exact |
| `'et dd -'` | lent | `'et dd-'` | **`None`** |
| `'et dd-'` | lent | `'et dd-'` | exact |

**Une seule direction.** Le chemin rapide, lui, est fidèle à la structure
`<SP>` de la source et ne soude jamais. La direction « espace ajoutée » que
la 1ʳᵉ analyse annonçait n'est reproductible que sur une forme fabriquée —
`String SP HYP` sans String-marque, **37 lignes sur 24 694** — et **aucun run
ne l'a jamais rencontrée**. Elle sort du plan.

**Ce que `None` déclenche.** `classify_projection_fidelity` compare des
**mots** : `['et','d','-']` contre `['et','d-']`. Divergence de mots →
`None` → `ProjectionError` (`projection.py:88`) → aucun `try` dans
`rendering.py` ni dans `pipeline.py:441` → `run()` propage. Le moteur prend
une décision correcte qu'il ne sait pas écrire, puis refuse correctement de
mentir — en tuant le document.

**La population, mesurée sur les 54 fichiers Gallica réels (24 694 lignes) :**

| | |
|---|---|
| lignes terminées par `<HYP>` | 4 578 |
| forme `#126` (`SP` + String-marque + `HYP`) | **29** (0,63 % des lignes à césure) |
| **fichiers portant ≥ 1 ligne à risque** | **10 sur 35 — 29 %** |

Les 10 fichiers appartiennent à **deux fascicules** (`bpt6k4607951t`,
`bpt6k46079527`). C'est une **signature de producteur**, pas un aléa : pour
un fonds numérisé par cette chaîne, le taux d'échec n'est pas 0,12 % des
lignes, c'est près de 100 % des fichiers. Et le texte de ces 29 lignes est
uniformément illisible (`"g'.e :.:;r.. --"`, `"1K' --"`) — exactement les
lignes dont un correcteur change le nombre de mots, donc la probabilité de
déclenchement *sachant la forme* est haute, pas faible.

**Pourquoi le défaut est resté ouvert, et pourquoi cette raison est fausse.**
La docstring du test dit « le correctif touche la géométrie, et écrire de la
mauvaise géométrie est pire que l'espace perdue ». Prototypé hors dépôt :
prendre l'espace **dans la fente déjà réservée au `HYP`** au lieu de l'ajouter
laisse tout le reste immobile, et les enfants pavent la ligne exactement.

```
décidé 'à la révision et d -'  →  artefact 'à la révision et d -'   exact
… String@817 w53, SP@870 w10, HYP@880 w20   → fin 900 = HPOS+WIDTH
```

**Le vrai obstacle, que personne n'avait nommé.** Un premier prototype a cassé
`test_f6_no_whitespace_geometry_unchanged` — une propriété **déclarée** :
une espace de bord ne doit pas changer la géométrie. Les deux tests ne
parlent pas de la même espace :

| entrée | où est l'espace | après `_drop_structural_break_hyphen` |
|---|---|---|
| `'deux mots- '` (`F6`) | **après** la marque | `'deux mots'` — absente |
| `'et d -'` (`#126`) | **avant** la marque | `'et d '` — présente |

`_drop_structural_break_hyphen` sépare donc déjà parfaitement les deux sens.
Ce que `_rebuild_line` ne peut plus faire : il reçoit une chaîne nue et ne
sait plus si l'espace précédait une marque ou en suivait une. **L'obstacle
n'était pas géométrique, c'était une perte d'information en amont.** Deviner
depuis l'intérieur du rebuild est précisément ce qui casse `F6`.

**Le correctif.** Porter le drapeau depuis l'endroit qui sait — le site
d'appel (`rewriter.py:1103`), seul à voir le texte avant *et* après le drop —
plutôt que le reconstituer. Élargissement de signature sur deux fonctions.

**Validé avant écriture.** Prototype monkeypatché, suite complète :
**1 659 passés, 1 échec** — `test_the_slow_path_welds_the_mark_OPEN_DEFECT`,
c'est-à-dire exactement l'inversion que sa propre docstring annonce. `F6`
passe, les golden de parité octet passent.

**Condition d'entrée.** Le test existant s'inverse (`assert delivered ==
decided`) et sa docstring devient de l'histoire. Un second cas ajouté : la
forme `#126` **sur le chemin rapide**, pour que la fidélité du chemin rapide
cesse d'être un effet de bord non asserté.

### `C2` — Publier le coût de la césure — **priorité 2**

Le chiffre est **déjà dérivable** : `DecisionSet.fallback_reason_counts()`
agrège `hyphen_pair_fallback` sans parser de message. Rien à construire.

Deux nuances que la 1ʳᵉ analyse avait omises et qui doivent figurer dans le
texte publié : `_refresh_pair_traces` (`reconcile.py:464`) n'écrit sa raison
**que si aucune n'est déjà posée**, donc le compteur isole proprement le
**dommage collatéral** ; et il compte des **lignes**, les deux membres d'une
paire tombée en recevant une — le nombre vaut donc ~2× les paires.

Ce qui manque est une phrase, nulle part écrite : une correction touchant un
mot coupé **coûte la correction de ses deux lignes**. Sur le run du 18 août :
**2 271 lignes**, deuxième cause de refus. Et le taux monte **12–28 % sur les
pages dégradées** contre 7–11 % sur les propres — c'est-à-dire qu'il est le
plus fort là où on veut corriger.

**Les taux de la section `B` sont repris tels quels, pas recalculés** : ils
viennent d'un run réel enregistré. Ce que `C2` ajoute est leur *publication*
dans le contrat et le README, pas une nouvelle mesure.

Vérité-en-documentation : autorisée sous le gel.

### `C3` — Le rayon d'action — **priorité 3, arbitrage**

**Le fait.** Une divergence de projection sur une ligne fait perdre **tout le
run** — pas seulement les autres fichiers : le `CorrectionReport` entier
disparaît avec, traces par ligne, niveaux de fidélité, décisions. Il ne
survit que le message d'exception, qui nomme une ligne. Les sources ne
risquent rien (vérifié par empreinte).

**Pourquoi après `C1` et pas avant.** Ce n'est pas un correctif, c'est un
**changement de contrat** de `run()`. Aujourd'hui la garantie est binaire et
facile à raisonner ; la livraison partielle l'affaiblit, et mal faite elle
devient le défaut que le dépôt combat depuis un an — accepter en silence
quelque chose d'incomplet. On le décide mieux quand la cause connue est
éteinte, pour ne pas confondre « on isole les dégâts » avec « on tolère un
défaut ».

**La forme honnête, et ce qui la rend possible.** `corrected_files` est un
dictionnaire clé par nom de fichier : un fichier non livrable **n'y est pas**,
donc un appelant qui attend son résultat obtient un `KeyError`, jamais un
fichier douteux. L'absence est bruyante par construction. Trois choses
ensemble, ou rien : attraper **par fichier**, **nommer dans le rapport**
pourquoi celui-là n'est pas livrable, et un test qui prouve qu'un résultat
partiel ne peut pas passer pour un succès complet.

**Arbitrage tranché le 2026-08-19 : livrer les fichiers sains.** Et il a été
tranché par une mesure, pas par une préférence.

Trois des quatre arguments pour garder le refus total ne tenaient pas. « On
ne peut pas ignorer le problème » est faux : un fichier retenu est *absent*,
et une recherche par nom lève. « Un résultat rendu veut dire que tout est
bon » est un confort de raisonnement, pas une propriété de correction — la
garantie qui compte est **par fichier**, et elle est intacte. « C'est déjà
écrit » n'est pas un argument sur ce qui est juste.

Le quatrième était réel : un mot coupé peut enjamber deux **fichiers**, donc
livrer le fichier *N* sans le *N+1* laisserait un mot à moitié corrigé dont
l'autre moitié n'existe nulle part. Mesuré sur les deux fascicules Gallica
réels — 12 fichiers, 8 787 lignes, **1 583 unités de césure** — il y en a
**0** à cheval sur deux fichiers, sur un détecteur vérifié contre un positif
fabriqué. Le mécanisme existe ; sur des volumes réels il est trop rare pour
payer la perte de tout le reste.

**Ce que le travail de `C3` a créé et qui a renforcé la décision** : avec
tous les fichiers fautifs nommés d'un coup, la *forme* de l'échec devient
lisible — 1 fichier sur 300 est un accident local, 300 sur 300 est une
configuration cassée. Livrer les sains devient un choix informé, pas un pari.

**Où atterrit le bruit.** Retenir le fichier ne suffisait pas : un appelant
qui boucle sur `corrected_files` écrirait 299 pages sur 300 en rapportant un
succès. Donc `CorrectionResult.write` — la seule porte qui pose des octets
sur un disque — **refuse** l'ensemble incomplet, et `allow_partial=True` est
l'appelant qui dit, dans du code relu, qu'il a lu la liste et accepte le
sous-ensemble.

### `C4` — Le mode page — **fait le 2026-08-19**

Les quatre pièces sont posées : l'aligneur qui tient à l'échelle page
(`#135`), l'alignement ligne-à-ligne et son refus de fusion (`#136`), le
contrat et le producteur (`#137`), et les deux modes nommés dans le README.

**Le run réel est fait — 2026-08-19 — et il ne dit pas ce que ce plan
espérait.** Quatre pages Gallica, 3 135 lignes, `mistral-small-latest`.

**L'aligneur n'est pas le problème.** Zéro ligne non appariée sur les quatre
pages. Tout ce que `#135`, `#136` et `#137` ont construit tient contre un
vrai modèle : la position suffit à retrouver chaque ligne, et la garde de
fusion n'a eu à refuser personne.

**Le modèle l'est.** Le taux de lignes que le modèle propose de changer est
**erratique** en mode page, et systématiquement plus bas qu'en mode apparié :

| page | lignes | page | apparié |
|---|---|---|---|
| f0001 | 518 | 52,3 % | 71,8 % |
| f0002 | 986 | **2,3 %** | 53,5 % |
| f0003 | 1 118 | 32,3 % | 47,9 % |
| f0004 | 513 | 56,1 % | 70,2 % |

Sur `f0002`, **963 des 986 propositions sont identiques à la source** : le
modèle a rendu la page telle quelle. Ce n'est pas une loi de taille — 1 118
lignes ont donné 32 % — c'est de la **variance**, et elle prolonge une
instabilité déjà notée le 18 août (*« la même page, même config, a donné
72/72 puis 3/72 »*).

**L'économie, elle, est réelle et mesurée sur la même page** (`f0004`,
513 lignes) :

| | mode page | mode apparié |
|---|---|---|
| appels | **2** | **147** |
| coût | **0,0051 $** | **0,0189 $** |
| durée | 77 s | 234 s |

**Deuxième passe, le même jour : la césure était une cause réelle mais
secondaire.** Le contrat page n'envoyait que des chaînes nues, là où le
contrat apparié porte six champs de césure par ligne. La cause de retentative
capturée dans les événements est `hyphen_integrity_violation` : voyant la
page comme du texte qui coule, le modèle **complète** le mot coupé — il écrit
`plusieurs-` là où la ligne dit `plu-`. Ajout du signal le moins cher
possible, une liste d'indices `coupes` (~200 jetons sur 518 lignes contre des
milliers si les six champs revenaient).

Mesuré : sur `f0001`, replis **101 → 88**, retentative de césure **supprimée**,
livraisons **inchangées à 195** — soit le mode apparié à une ligne près (196).

**Et une leçon de prompt, payée.** La première rédaction de la règle était
longue, en majuscules, avec un exemple. Le modèle est devenu timide sur
**toute** la page : propositions **271 → 50**, livraisons 195 → 38. La règle
brève rétablit tout. L'insistance se paie ailleurs que là où on la met.

**Ce qui reste, et c'est la taille de la page.** À 518 lignes le mode page
égale le mode apparié (195 contre 196). À 986 lignes il livre **9 contre
278**, et `coupes` n'y change rien.

**Le levier « borner la requête » ne marche pas aujourd'hui, et deux points
de mesure disent pourquoi.** Sur une page de 986 lignes :

| plafond | chunks | appels | livré | coût |
|---|---|---|---|---|
| 400 lignes | **217** | 217 | 169 | 0,0133 $ |
| 250 lignes | **217** | 217 | 189 | 0,0132 $ |
| page entière | 1 | 1 | 9 | 0,0051 $ |
| *mode apparié* | *121* | *147* | *278* | *0,0189 $* |

**400 et 250 donnent le même nombre de chunks.** Le plafond n'est donc pas
ce qui découpe : dès qu'il est franchi, le planificateur **descend au BLOC**,
et la page a 217 blocs. En dessous de la taille d'un bloc, le plafond ne
change plus rien — les 169 contre 189 livrés sont de la variance du modèle,
pas un effet du réglage.

**Ce qui manque au planificateur est de savoir trancher une page en N
tranches égales** — il ne sait que descendre PAGE → BLOCK → WINDOW → LINE.
C'est un travail identifié, pas un mystère.

**Verdict inchangé : ne pas recommander le mode page.** Sa partie risquée est
prouvée, sa césure est réglée, et ce qui bloque est soit un découpage que le
planificateur ne sait pas exprimer, soit un modèle qui tienne mille lignes.



**Les deux modes, et comment les nommer.** Le critère est *qui détient
l'identité de ligne* :

| nom | qui détient l'identité | appels / 28 pages | coût mesuré |
|---|---|---|---|
| **`line_keyed`** — mode apparié | le contrat JSON, ligne par ligne | ~2 000 | 1,11 $ |
| **`page_aligned`** — mode réaligné | l'aligneur, après coup | **28** | **0,14 $** |

Ce sont deux **producteurs**. Aucun changement du cœur, et c'est la propriété
qui rend le double mode tenable : les gardes, la réconciliation, la
projection et la comptabilité sont partagées, donc `cinoc` peut *benchmarker*
les deux sur le même moteur.

**Ce qui est réutilisable, mesuré, et bien moins que ce que la 1ʳᵉ analyse
annonçait.** Trois murs dans `core/alignment.py`, aucun n'étant un paramètre
à régler :

1. **La matrice `sim` est matérialisée en entier** (`alignment.py:104`) avant
   que la DP démarre — 8 Mo à 500², 33 Mo à 1 000², **128 Mo à 2 000²**. Une
   page de 8 620 tokens : ≈ **2,4 Go** pour `sim`, autant pour `cost`. Le
   mode page **saturerait la mémoire** avant d'être lent.
2. **`source_for_target` est un balayage linéaire des paires**, appelé une
   fois par token cible dans la boucle de `_rebuild_line` — une seconde
   quadratique par-dessus la DP. Le scan `move_suspected` en est une
   troisième.
3. **`align_tokens` n'a aucune notion de ligne** — or c'est exactement ce que
   le mode page doit reconstituer : où finit la ligne *k*.

Les temps confirment la quadratique : 0,005 / 0,095 / 1,83 / 14,25 s pour
50 / 200 / 800 / 2 000 tokens, soit ≈ 265 s extrapolés pour une page.

Réutilisable : le modèle de coût et la forme du backtrack — **~30 %**. Les
70 % restants sont exactement ce que l'échelle page casse. Le premier travail
n'est donc **pas** le bandage, c'est une réécriture qui ne matérialise pas
ses matrices.

**Ce que le bandage apporte — fait le 2026-08-19, et une revendication de
cette section était fausse.** Le modèle rend la page dans l'ordre, donc
l'alignement est quasi diagonal ; une bande ramène le coût à O(n × bande).
Ça, c'est vérifié.

Ce qui ne l'était pas : « **la bande donne la garde gratuitement** ». Mesuré,
`band_exhausted` dit **où la recherche est allée, pas si la lecture est
bonne**. Une transposition de blocs ne partageant aucun caractère le
déclenche ; la *même* transposition de `w0`…`w59` ne le déclenche pas, parce
qu'une correspondance diagonale médiocre (2 × 0,33) coûte moins qu'un trou
apparié à une insertion (2,0), donc le chemin n'a jamais besoin de sortir. Et
une suppression massive ne le déclenche pas non plus : le couloir **s'élargit**
à la différence de longueur, faute de quoi il n'existe aucun chemin de coin à
coin.

Donc la garde du mode page n'est pas là. Un morceau sauté se voit comme une
série de suppressions dans les paires ; une ligne décalée effondre
`min_source_similarity` sur toutes les suivantes. Deux mesures pour deux
défaillances — les confondre donnerait au mode page une garde silencieuse
précisément quand elle compte.

**Aucune garde neuve n'est nécessaire par ailleurs** : un décalage d'une
ligne est attrapé **100 % du temps** par les gardes existantes (1 736 lignes,
trois corpora) — mesure du 18 août, **non rejouée** dans la contre-analyse et
signalée comme telle.

**Le premier cas à écrire, avant le producteur** : une page où le modèle rend
**moins de lignes qu'il n'en a reçu**, parce qu'il en a fusionné deux.
L'aligneur doit refuser, pas redistribuer. **Fait le 2026-08-19**
(`core/page_alignment.py`), et la mesure a corrigé le module deux fois.

**L'alignement se fait sur les LIGNES, pas sur les jetons de la page.** Trois
mesures de similarité comparées sur les lignes réelles avant d'écrire quoi que
ce soit : Levenshtein sépare une ligne de ses voisines de 0,739 en moyenne, le
Jaccard des jetons de **0,747** — pas moins bien — et coûte **13× moins**.
L'insensibilité à l'ordre n'est pas une faiblesse à ce niveau : la question est
*quelle ligne est-ce*, pas ce que ses mots font à l'intérieur. Résultat :
**0,05 s** pour une page de 1 000 lignes.

**Ce que la première version faisait, et qui a failli passer.** La ligne
avalée par une fusion se retrouvait sans cible — le test passait, la garde
semblait acquise. Sauf que l'AUTRE ligne, elle, était appariée à la ligne
fusionnée et recevait donc les mots de sa voisine. C'est exactement la
corruption que le mode ne doit jamais produire, et elle se cachait derrière un
test vert. Vue seulement en écrivant un cas jouet qui a cassé pour la
mauvaise raison.

**Le garde-fou, mesuré, pas choisi.** Sur 8 859 paires appariées de huit pages
réelles, une correction déplace le compte de jetons d'une ligne de **−1, 0 ou
+1 — 100 % du temps** (+0 seul à 94 %). Une fusion produit une ligne portant
**1,64× à 1,86×** les jetons de sa source, soit 6 à 14 de plus. Les deux
populations ne se touchent nulle part. Le seuil est donc à ±2 jetons, **à
l'intérieur de la similarité** et non en filtre après coup, pour que la DP ne
*préfère* jamais une fusion : les deux lignes reviennent non appariées et
gardent leur OCR. Après la garde : fusion appariée **0 fois sur 6** (contre
6 sur 6 avant), et les 8 859 appariements ordinaires **tous conservés**.

Limite énoncée : sur une ligne d'un seul jeton la marge est plus grande que la
ligne, donc fusionner deux lignes très courtes peut encore passer. Le dommage
est borné et l'alternative — une marge sous le ±1 mesuré des vraies
corrections — désapparierait des milliers de lignes légitimes.

### Ordre, et ce qui est correctif contre décision

**`C1` → `C2` → `C3` → `C4`.** `C1` d'abord parce que c'est prouvé, prototypé,
petit, et que l'enjeu est 29 % des fichiers d'un fonds réel. `C2` ensuite
parce qu'il coûte une heure. `C3` après, parce que c'est un arbitrage qu'on
décide mieux la cause éteinte. `C4` en dernier, et plus loin que dit.

| | nature |
|---|---|
| `C1` la marque soudée | **correctif** |
| `C2` le coût publié | **correctif** (documentation) |
| `C3` le rayon d'action | **décision** — change le contrat de `run()` |
| `C4` le mode page | **décision** puis correctif |

## D — Les petits modèles locaux, 2026-08-20

Mesuré parce que le mainteneur a posé la contrainte : **la cible est un petit
modèle qui tourne en local**, pas un fournisseur distant. Ça change ce qu'on
optimise, et ça a d'abord servi à corriger une affirmation fausse de ce plan
(voir `A`, point 4 : « son mode texte fait 0 improved » ne parlait pas d'un
LLM).

### Un modèle d'un milliard de paramètres corrige, en texte pur

Appel isolé, `gemma3:1b`, contrat apparié, **4 secondes** :

```
'Le rvi de Frauce est mort hier'      ->  'Le roi de France est mort hier'      juste
'et le peuple a plemé toute la nuit'  ->  'et le peuple a pleuré toute la nuit' juste
'dans les rnes de la capitale'        ->  'dans les noms de la capitale'        faux (rues)
```

Deux sur trois, JSON valide. La question n'est donc pas « un petit modèle
peut-il corriger » — il peut.

### Sur une page entière, c'est le contrat qui casse, pas la correction

Page réelle de 72 lignes, `gemma3:1b`, chunks de 12 :

| | `requires_full_coverage=True` | `False` |
|---|---|---|
| appels | 121 | **87** |
| retentatives | 61 | **35** |
| descentes de granularité | 14 | **6** |
| `all_attempts_exhausted` | 26 | **4** |
| **lignes livrées corrigées** | 3 | **6** |
| lignes en repli | 50 | **28** |
| durée | 959 s | 889 s |

Le modèle rate la structure attendue à peu près une fois sur douze — une
ligne absente, un identifiant altéré. Avec `requires_full_coverage=True`,
chaque manque est une **erreur de validation**, donc une retentative, puis
une descente de granularité : **121 appels pour 72 lignes**.

**Le drapeau seul double le rendement et divise les épuisements par six.**
`LLMEditProducer` le déclare `True` en dur, ce qui est le bon choix pour un
modèle qui tient son contrat et le mauvais pour un petit modèle local.
**Décision à prendre** : en faire un réglage que l'hôte pose selon la classe
de modèle. C'est de la surface publique, donc un arbitrage.

### Ce que les gardes font face à un modèle faible — et c'est le bon résultat

`too_different_from_source` reste à **22–23 lignes dans les deux
configurations**. Le drapeau change la couverture, jamais la qualité : c'est
le taux d'hallucination du 1B, et la bibliothèque le refuse au lieu de
corrompre le fichier. Elle n'avait jamais été mise en situation de le
prouver.

### Les autres modèles de la machine

`churro-3B` (qwen2-VL, 3 G, vision) **ne corrige rien en texte pur** : il rend
les trois lignes identiques. Ce n'est pas un défaut — c'est un modèle d'OCR,
fait pour lire une image. Il ne se juge qu'en vision.

`gemma3:1b` n'a **pas** la vision (`completion` seul) ; elle commence à 4B
dans cette famille.

### Deux pièges de mesure, tous deux chez moi

**Ollama tronque à 2 048 jetons de contexte par défaut**, silencieusement. La
première mesure du mode page a rendu un JSON coupé au milieu, ce que j'ai
failli lire comme « le modèle échoue ». Une page de 513 lignes demande ~6 000
jetons en entrée **et autant en sortie**.

**Et le plafond par défaut du planificateur est de 80 lignes**, donc une page
de 72 lignes part **entière** dans les deux modes. Ma comparaison « beaucoup
de petits appels contre un gros » était fausse : c'était un appel compact
contre un appel six fois plus lourd — l'enveloppe appariée pèse **12 561
caractères contre 2 420** pour 2 084 caractères de texte, soit **5,2×**.

### La sortie structurée est bien le frein — proposition du mainteneur

Il a demandé si on ne pouvait pas faire rendre au modèle **juste la phrase**
et reconstruire la structure nous-mêmes. Les causes réelles de retentative,
capturées, lui donnent raison : **toutes structurelles**, aucune n'est une
mauvaise correction — sauts de ligne parasites (10), `line_id` manquants ou
inventés (5), comptes de lignes faux (4), JSON tronqué (1). Les mauvaises
corrections sont ailleurs, refusées par les gardes.

Mais retirer le JSON ne suffit pas, et la mesure a corrigé l'idée deux fois :

- **sans aucune structure**, `gemma3:1b` rend **une ligne pour cinq** — il
  fusionne tout. Le schéma était ce qui tenait la séparation ;
- **avec un délimiteur `|`**, le modèle décale toute la page, parce que l'OCR
  dégradé en contient lui-même (`'| ai< i'` est une vraie ligne du corpus).
  Un délimiteur présent dans les données casse là où on en a le plus besoin ;
- **avec une TABULATION**, ça tient à partir de 4B : `gemma3:4b-it-qat` et
  `gemma4:e2b` rendent 5 lignes sur 5 et gardent verbatim la ligne au `|`.

Et le meilleur résultat de la série : face à douze lignes de bruit illisible,
`gemma4:e2b` **ne hallucine pas** — il les rend inchangées. C'est le
comportement voulu, prouvé sur le cas le plus dur.

### État — et les taux ci-dessus sont invalides

**Toutes les mesures de TAUX de cette section sont à jeter**, pour une erreur
de méthode : la page de test a été choisie pour sa **taille** (72 lignes,
elle finissait vite), et elle s'est révélée être du bruit — **41,7 % de
lignes lisibles, confiance OCR médiane 0,50**, contre 84 % / 0,91 et
93 % / 0,98 pour les pages du corpus de référence. Sur une telle page la
bonne réponse d'un correcteur est « ne corrige presque rien », donc « 10
livrées sur 72 » ne se compare à rien.

**Ce qui survit**, parce que ça ne dépend pas de la lisibilité du texte : les
causes de retentative sont structurelles ; un 1B ne tient pas la structure
sans schéma et un 4B oui ; le délimiteur doit être absent des données ;
`requires_full_coverage=False` supprime les épuisements ; et un petit modèle
ne hallucine pas sur du bruit.

**Corrigé aussi, et c'était faux pour la même raison** : « le planificateur ne
sait pas faire des paquets de N lignes ». Le grain `WINDOW` est exactement
ça, avec `line_window_size` réglable — sur une page représentative, un
plafond de 12 donne **47 fenêtres de 12 lignes**. Sur la page de bruit il n'y
allait pas parce que ses blocs font déjà une ligne : le planificateur
s'arrête au premier grain qui rentre. Le comportement dépend donc de la
structure de la page, ce qui le rend difficile à prévoir sans mesurer — mais
il n'est pas absent.

## A — Audit du 2026-08-17 : le tri

Huit axes mesurés en parallèle, en réponse à la revue externe du 2026-08-16. Les
constats et leurs preuves sont dans `docs/audit/AUDIT-2026-08-17-huit-axes.md` ;
ce qui suit est **le tri**, et rien d'autre.

Le principe du tri : **un artefact silencieusement faux passe devant tout le
reste.** Ce qui échoue bruyamment, perd des données de façon repérable, ou ne
coûte que du temps, attend. Et le tri distingue trois portes différentes que la
revue externe confondait en une seule liste de douze points : ce qui bloque la
**correction**, ce qui bloque la **publication**, et ce qui n'est qu'une limite
à **déclarer**.

### A0 — Le motif commun, à garder en tête pendant tout ce qui suit

Les invariants sont écrits pour un producteur qui rend des **lignes entières**,
et contrôlés par des prédicats **positionnels** — premier mot contre premier
mot, i-ème `String` contre i-ème mot. Le protocole d'édition par spans permet de
**déplacer une frontière** sans changer ni le compte ni la position : c'est
l'angle mort commun de presque tous les défauts ci-dessous. Corriger un par un
sans voir le motif reviendrait à jouer à la taupe.

Deuxième moitié du motif : quand ces gardes refusent, ils refusent **en
silence** — `EditRejection` n'a aucun consommateur hors des tests. Le trou est
donc invisible au rapport comme au banc.

### A1 — Bloquant pour la correction : l'artefact peut être faux sans le dire

Dans cet ordre, parce que chacun est indépendant et que les premiers sont les
moins chers.

| # | quoi | coût | mesuré |
|---|---|---|---|
| `A1a` | **Fait le 2026-08-17.** Chemin rapide ALTO : détecter le déplacement de frontière avant toute mutation, sinon router vers le chemin lent. **Aucune correction refusée, seulement re-routée** — et aucune ligne du corpus réel ne l'est | petit | avant : 8,6 contre 273 unités par caractère, `losses` vide, `fidelity = EXACT`. Après : 84,9 et 85,0 |
| `A1b` | **Côté PART1 fait le 2026-08-17** : la marque de coupure exige désormais un caractère non-blanc devant elle. Exact et non heuristique — si le parseur a dit PART1, un mot finissait là. **Côté PART2 non fermé**, voir `E5b` ci-dessous | petit | `'Le peuple att-'` devenait `'Le peuple -'`, accepté, et l'ALTO portait `<String CONTENT="-"/>` |
| `A1c` | **Fait le 2026-08-17.** Migration de mot entier : la règle exige **les deux moitiés du déplacement** — le mot apparaît où il n'était pas *et* a disparu d'où il était. La version courte proposée aurait annulé une répétition typographique légitime | petit | un mot changeait de ligne, deux lignes `corrected`, `fallback_lines: 0`. La similarité concaténée valait 0,69 sous un seuil de 0,80 |
| `A1d` | **Fait le 2026-08-17.** `write()` refuse les collisions de nom de base avant d'écrire quoi que ce soit ; les deux `read_source_tree` des réécriveurs passent par un helper classifié — extrait plutôt qu'enveloppé sur place, le cliquet de taille de `RM-10` interdisant aux deux entrées de grandir | petit | 3 chemins retournés, 2 fichiers sur disque ; `FileNotFoundError`, `XMLSyntaxError` et `PermissionError` nus qui s'échappent |
| `A1e` | **Fait le 2026-08-17.** Contrôle de couverture au préflight, dans les deux sens : une source manquante et une clé fantôme sont refusées. Le run à vide reste légal, et un test le garde | ~30 lignes | le run RÉUSSISSAIT avec la moitié des lignes décidées dans aucun artefact |
| `A1f` | **Fait le 2026-08-17.** Condensats estampillés au parsing sur `DocumentManifest.source_digests` ; refus **au préflight** si un chemin ne porte plus ses octets — donc avant toute dépense, et non au rendu comme prévu. Ferme la contamination croisée, le TOCTOU, et `C4` : la provenance atteste désormais les octets réellement lus | moyen | artefact chimère, run réussi ; `EditScript` qui échouait sur ses propres préconditions |
| `A1g` | **Fait le 2026-08-17.** La chaîne vision vérifie les octets contre `asset.sha256`, et la lecture passe d'une fois **par ligne** à une fois par chunk — c'est ce qui rend la vérification assez peu chère pour être inconditionnelle | petit | condensat gravé `e8b4…`, fichier ouvert `ec62…`, crops différents |

Note d'exécution sur `A1a`, qui vaut pour toute cette section : la garde que
l'audit proposait — *un mot corrigé partage au moins un caractère avec l'original
à la même position* — **passe sur le contre-exemple même qu'elle cite**.
`aujourd` partage `a` et `u` avec `au`, `hui` partage trois caractères avec
`jourdhui`. Vérifié avant d'écrire une ligne de code, et le constat est gardé
exécutable par un test. Le signal qui mord est autre : *les lettres sont les
mêmes et le découpage ne l'est pas* — exact, sans seuil, sans faux positif par
construction — doublé d'une tolérance de longueur pour les déplacements
accompagnés d'une correction. **Ne pas prendre une proposition d'audit pour un
correctif validé.**

`A1e` et `A1f` sont la **contre-proposition mesurée** à l'« objet source
immuable » que la revue réclamait : elle fermerait deux des quatre problèmes
annoncés pour ~527 lignes d'appel sur ~110 fichiers ; ces deux lignes-ci ferment
les quatre pour environ un dixième du coût. La refonte reste souhaitable un
jour ; elle n'est pas le chemin le plus court vers un artefact honnête.

### A2 — Bloquant pour la correction : des gardes qui ne gardent pas ce qu'ils annoncent

| # | quoi | note |
|---|---|---|
| `A2a` | `E4`/`E5` ne s'appliquent pas à `replace_line`, donc **pas au producteur par défaut**. Décider : soit étendre `E5` seul à cette voie, soit émettre un rejet consultatif et le dire. Ce qui n'est pas tenable, c'est la formulation actuelle du contrat | le code l'avoue en commentaire ; le contrat promet l'inverse |
| `A2b` | **Fait le 2026-08-17.** `CorrectionReport.edit_rejections` — page, ligne, op, raison — trié pour ne pas dépendre de l'ordre d'exécution. Additif, ne refuse rien, mais **étend la surface publique de 66 à 67** : `RefusedEdit` devient atteignable depuis un type retourné, donc membre de la clôture, exactement comme `HyphenSplit`. Croissance par clôture, pas par accrétion | sans lui le taux de refus n'était pas non mesuré mais **non mesurable**, et un consommateur qui desserre un seuil sur un corpus dégradé ne pouvait mesurer aucune différence |
| `A2c` | **Fait le 2026-08-17.** `_script_to_raw` rend un couple indissociable — le lot à valider et les lignes refusées — plutôt que de jeter les secondes. Le budget de paramètres a refusé un neuvième argument, et il avait raison : les deux valeurs viennent du même calcul et ne sont justes qu'ensemble | ferme la promesse de rejeu, **marquée fermée à tort le 2026-08-16** |
| `A2d` | **Fait le 2026-08-17, et plus large que prévu.** La règle ne porte ni sur le nom de l'attribut ni sur le rôle de la ligne, mais sur la **valeur source comparée à ce que la ligne veut écrire** — ce qui ferme aussi un second cas : une valeur de césure que le rôle ne reproduit pas était détruite et non comptée elle aussi. Deux tentatives antérieures produisaient un **fantôme** : compter « occurrences moins une » sous-soustrait sur une ligne `BOTH`, où la réécriture en écrit deux | `R*` violée dans les deux sens ; la mesure « 234 entrées, 234 sorties » était vraie et la conclusion ne suivait pas — le corpus ne porte que des valeurs de césure |
| `A2e` | **Partiellement fait le 2026-08-17.** L'invariant existe et il est **exact** : le mot recollé est le dernier mot de la tête, marque retirée, suivi du premier mot de la queue — vérifié sur **413 paires de tous les corpus réels, zéro divergence**, et sur les fichiers livrés après un run. **Ne couvre pas encore l'écriture du réconciliateur** : inverser le mot qu'il écrit laisse les deux moitiés vertes, parce que les paires qui survivent à un run correcteur sur ces fixtures sont celles qu'il n'a pas réécrites. Il faut une fixture qui force une paire à se réconcilier vers un texte neuf en gardant son `SUBS`. La promotion en refus à l'exécution est une étape distincte | 4ᵉ décision par ligne, livrée, hors du périmètre vérifié |

Dette laissée ouverte par `A2b`, nommée pour ne pas être oubliée : une ligne
dont la seule op a été refusée rapporte toujours `corrected` alors qu'elle
porte son texte source. C'est la forme `L3`/`L9`, et l'invariant que le dépôt
énonce lui-même dans `test_status_truthfulness.py` dit qu'elle devrait dire
`fallback`. La corriger passe par l'écrivain unique de décision (`RM-01`) et
par les cliquets de statut, donc ce n'est pas un correctif d'une ligne — mais
c'est maintenant **visible**, ce qui était le préalable.

### A2bis — La garde de dérive doit juger un document contre lui-même

Ouvert le 2026-08-17 en réponse à une objection juste : **il n'y aura pas de
relecture humaine.** Le pipeline traite des milliers de documents, donc
« signaler pour relecture » n'est pas une issue, c'est un renvoi. Cette piste
est retirée.

Ce qui la remplace part d'une mesure. Tout ALTO réel du corpus porte une
confiance par mot, et la bibliothèque la parse déjà en
`LineManifest.ocr_confidence` — 100 % des lignes sur chaque fixture ALTO.
**Mais l'échelle n'est pas comparable d'un exportateur à l'autre :**

| document | médiane | minimum | 5ᵉ centile |
|---|---|---|---|
| Gallica, `bpt6k2324031`, 1144 lignes | 0,990 | 0,010 | 0,850 |
| BnL, `X0000002`, 566 lignes | 0,582 | 0,127 | 0,379 |
| BnF prod, `bpt6k5406037v` | 0,985 | 0,500 | 0,542 |

Une constante absolue — « méfie-toi sous 0,6 » — signalerait **tout** le
document BnL et **rien** de Gallica, alors que le BnL n'est pas un mauvais OCR
mais une autre échelle. Gallica sature (957 lignes sur 1144 exactement à 0,99)
avec une queue réelle jusqu'à 0,01 : le signal existe, il est **relatif à son
propre document**.

D'où la direction : la garde cesse de demander « cette ligne a-t-elle changé de
plus de K ? » et demande « **cette ligne a-t-elle changé plus que les lignes de
ce document ne changent ?** ». Là où l'OCR publie une confiance, elle sert à
*attendre* plus de changement sur les lignes que le moteur situe bas dans sa
propre distribution. Aucun seuil absolu ne survit, et le mécanisme s'auto-
calibre sur les deux distributions ci-dessus.

Deux réserves, à ne pas perdre :

- **PAGE ne porte aucune confiance** dans le corpus (0 ligne sur 78). Le repli
  est la distribution des changements elle-même, qui ne demande aucune
  métadonnée et vaut pour les deux formats.
- **Un document uniformément mauvais n'a pas de contraste interne**, donc pas de
  signal. La garde ne peut alors pas discriminer, et la conduite honnête est
  d'accepter — l'alternative étant de livrer sciemment de l'illisible — **et de
  l'écrire au rapport**, ce que `A2b` rend possible.

À mesurer sur `cinoc` contre vérité terrain avant d'être codé, et sous gel de
fonctionnalités d'ici là. `A2b` était le préalable : sans lui, aucun balayage de
seuil n'était observable.

### A3 — Bloquant pour la correction : la suite ne peut pas voir ce qu'elle affirme voir

Sans cette section, rien de ce qui précède n'est vérifiable — et c'est le
constat le plus important de l'audit.

| # | quoi | mesuré |
|---|---|---|
| `A3a` | **Fait le 2026-08-17.** Un second témoin indépendant : le test sait ce qu'il a demandé au producteur de proposer, donc il vérifie le rapport contre cela plutôt que contre lui-même. Il faut une proposition **refusée** — sur une ligne acceptée, proposition et décision coïncident et la mutation est invisible par construction | avant : mutation → **1485 tests verts**. Après : la même mutation fait rougir exactement 1 test, et les 1565 autres confirment qu'aucun autre ne l'attrape |
| `A3b` | **Fait le 2026-08-17.** Le compte vient désormais de lxml directement, hors du parseur testé, **marges exclues** — parce que le parseur les exclut délibérément. Ma première version comptait tous les `TextLine` et échouait sur les trois pages : elle assertait une propriété que la bibliothèque n'a pas et ne doit pas avoir (en-têtes courants, folios). Plus le sens inverse : aucune ligne inventée | avant : parseur qui perd une ligne par bloc → **les 18 tests passent**. Après : 9 rougissent |
| `A3c` | **Fait le 2026-08-17.** Le recensement scanne récursivement — vérifié : il trouve les **mêmes** deux sites, donc le trou était latent, et un troisième écrivain planté dans `core/schemas/` est désormais vu. Le garde anti-skip connaît les trois formes ; les deux évadés, sur fixtures committées, sont supprimés. Ma première version du garde s'attrapait **elle-même** — son commentaire citait la forme cherchée | fixture déplacée : avant → test skippé et garde vert ; après → le test **échoue bruyamment** |
| `A3d` | **Fait le 2026-08-17.** Le rejet est **asserté**, plus supposé : une paire devenue acceptable doit être remplacée, pas contournée. Un test qui s'écarte quand sa prémisse tombe rapporte un succès pour la seule raison qui justifie son existence | mutation : avant → 3 cas skippés, fichier vert ; après → 3 cas rouges |
| `A3e` | **Fait le 2026-08-17, et il a révélé plus que prévu.** La direction s'exécute désormais — mais **une seule fois**, sur un seul attribut, sur un des quatre cas. Presque toute disparition réelle est soit un attribut **invalidé** (`WC`/`CC`, comptés par ligne sous leur propre clé, dont la vérification matricielle a la charge) soit accompagnée d'un changement du nombre de `String`, que cette comparaison ne peut pas lire. La deuxième direction est donc **structurellement quasi vide telle qu'écrite**, et c'est la matrice qui porte le poids. Constat de forme, pas de site d'appel — et il fallait la faire s'exécuter pour le voir | sentinelle : avant → **20/20 verts** ; après → atteinte |
| `A3f` | **Répertoire de marques et alphabet faits le 2026-08-17.** Les deux générateurs tirent la marque depuis `HYPHEN_CHARS` (avant : 0 marque autre que `-` sur 200 tirages ; après : chacune des six apparaît). Et l'alphabet est **pondéré** comme le texte réellement corrigé au lieu d'être uniforme sur 442 codepoints : documents recevant au moins une correction, **56 % → 70 %**. Correction d'une de mes affirmations : élargir les RÈGLES ne vaut que 2 points (68 → 70), c'est l'ALPHABET le levier (56 → 70). Les règles étendues restent pour le réalisme — `n`/`u`, `i`/`l`, le `s` long — pas pour la couverture. ~~**Reste ouvert**~~ **Reste fermé le 2026-08-17**, avec deux de mes affirmations corrigées par la mesure — voir sous le tableau | mesuré, base d'exemples désactivée |

Seconde leçon d'exécution sur `A3f`, du même genre que la première et plus
gênante : j'ai mesuré la couverture **trois fois de trois manières** et obtenu
trois réponses. Deux venaient d'un contournement du générateur qui ne prenait
pas effet, et d'une base d'exemples Hypothesis qui rejouait des cas biaisés. Le
chiffre que j'avais annoncé — les règles font passer de 42 % à 22 % — était
faux ; elles valent deux points. **Une mesure vaut la méthode qui l'a produite,
et deux bras comparés doivent l'être avec la même.**

Troisième, sur la garde elle-même : sa première version cherchait les lettres
dans la chaîne XML brute, qui contient `CONTENT`, `HPOS`, `SUBS_TYPE` — donc la
condition était vraie de tout document. Elle n'attrapait aucune des deux
régressions. Reformulée sur les textes de lignes analysés, puis calibrée sur ce
qu'elle peut réellement discriminer, elle en attrape une et le dit.

**Fermeture du reste de `A3f`, le 2026-08-17, et deux de mes affirmations que la
mesure a corrigées.**

*Les tests `st.binary`.* Ils ne sont pas « sans assertion » : une exception non
classifiée les ferait échouer. Le vrai trou était ailleurs, et il en a révélé un
second. Mesuré sur douze graines, ce que chaque générateur atteint réellement
comme analyse réussie — c'est-à-dire le code derrière la porte d'entrée, la
politique de coordonnées, la cohérence `SUBS_*`, les polygones dégénérés :

| générateur | min | médiane | max |
|---|---|---|---|
| `st.binary` → ALTO | 0 % | 0 % | 0 % |
| `st.binary` → PAGE | 0 % | 0 % | 0 % |
| troncatures | 0,33 % | 0,33 % | 0,33 % |
| mutation d'un octet | 9,33 % | 14,17 % | 18,33 % |
| `hostile_alto` | **2,67 %** | **4,83 %** | **9,33 %** |
| `hostile_page` | 40,7 % | 51,8 % | 60,7 % |

Les deux `st.binary` n'atteignent **rien**, par nature : des octets au hasard ne
sont jamais du XML valide. Ils établissent une seule chose — des octets
arbitraires sont refusés — et ça vaut d'être affirmé, mais pas d'être pris pour
de la couverture sémantique. Épinglés à zéro **exprès**, plutôt que supprimés :
si un futur parseur les faisait passer, ce serait un vrai résultat, et c'est là
qu'il apparaîtrait.

*Correction à l'audit, et à ma propre correction.* L'audit annonçait
`hostile_alto` à 1 % utile. Une mesure unique m'a donné 9,5 % et j'allais
l'écrire — c'était près du **haut de son propre étalement**. La médiane est
4,8 %, le minimum 2,67 %. L'audit sous-estimait d'environ 5×, pas de 10×. Et le
plancher calibré sur cette mesure unique **a échoué dans la suite complète**, où
`pytest-randomly` réamorce l'entropie : c'est la même leçon que ci-dessus, une
troisième fois. Les planchers sont désormais la moitié du **minimum** sur douze
graines, vérifiés sur trente, et ils attrapent l'effondrement d'un générateur —
pas sa dégradation graduelle, ce qui est dit sur place.

*Second trou révélé par le même passage.* Les helpers attrapaient
`CorrectionError`, qui est un **alias de la classe de base** — donc un
`ConfigurationError` échappé du parseur comptait comme le contrat tenu, alors
que la promesse en tête du fichier nomme la famille `ParseError`. Mesuré sur
2 400 tirages : c'est toujours un `ParseError`, donc le nommer ne coûte rien et
rend la promesse vérifiable. Prouvé par mutation.

*Les impossibilités structurelles du générateur.* Sonde sur toute la suite,
1 604 tests, chaque appel à `derive_hyphen_groups` enregistré :

| structure | atteinte |
|---|---|
| chaîne ≥ 4 membres | **476 fois**, jusqu'à 12 membres |
| page vide | **jamais** |
| document ≥ 3 pages | **jamais** — `max pages = 2` |

**La chaîne de 4 n'était pas un trou de couverture.** C'en est un du
générateur, mais la suite atteint des chaînes de douze par des cas construits à
la main et par les corpora réels ; l'apprendre au générateur n'aurait rien
ajouté. *Un trou dans un générateur n'est pas un trou dans la couverture, et la
différence tient à une mesure.* Les deux autres étaient réels et sont désormais
couverts. Rien n'était cassé — une chaîne de césure traverse correctement trois
pages en un seul groupe, une page vide survit au run et ne décale pas ses
voisines — donc ce sont des gardes de régression, pas des correctifs, et le
fichier le dit pour ne pas enseigner l'inverse au prochain lecteur.

Ce que les deux pages n'atteignaient pas, et qui explique pourquoi ça valait le
coup : un document de deux pages a **une** couture, donc une chaîne ne peut pas
en traverser trois, et il n'a **pas de page du milieu**, donc « la correction est
tombée sur la bonne page » et « sur la dernière page » sont la même phrase.

Leçon d'exécution sur `A3f`, qui vaut pour tout ce bloc : ma première garde
anti-régression scannait le code source à la recherche du littéral codé en dur.
Elle **n'attrapait pas** la régression évidente — figer `break_mark = "-"` ne
retire ni le littéral ni l'import. Un contrôle de *forme* pour une propriété de
*comportement*, c'est-à-dire exactement l'erreur que ce bloc existe pour
trouver. Réécrite en tirant des documents et en regardant ce qui sort, elle
attrape les deux générateurs. **Se méfier d'une garde qui lit du code plutôt
que des résultats.**

Signal à retenir : sous une mutation comportementale du parseur ALTO, le **seul**
test devenu rouge fut le cliquet de nombre de lignes. *La suite détecte plus
fiablement la taille du code que son sens.*

Trou nommé par `A3e`, à ne pas perdre : **la fusion de `String` n'a aucun
compteur.** Mesuré sur `X0000002.xml` — 5 lignes sur 566 portent des `String`
consécutifs sans `SP`, artefact d'OCR ayant scindé un mot en fragments. Le
chemin lent reconstruit depuis les tokens, donc il les fusionne : le texte est
identique (`L` + `r` + `s` → `Lrs`) et deux éléments `String` disparaissent avec
leur géométrie, leur identité et leurs confiances. Antérieur à tous les
correctifs du 2026-08-17 — la ligne prend le chemin lent parce que 9 `String`
source rencontrent 7 mots corrigés, quelle que soit la décision d'une garde.

Ce que `R*` exige est que toute altération soit déclarée et comptée. La perte
laisse une trace (`style_dropped`, `confidence_invalidated`, le chemin
rapporté) et un test garde ce minimum, mais elle n'a pas de compteur propre.
Lui en donner un étend le rapport, donc c'est un arbitrage de surface publique
au même titre que `A2b`.

### A4 — Bloquant pour la publication seulement

Tous petits, tous mesurés, aucun ne touche la correction.

| # | quoi |
|---|---|
| `A4a` | **Fait le 2026-08-17, autrement que prévu.** Plutôt que rétrécir la borne, corriger la cause : `protected_namespaces=()` sur `LineTrace`, dont deux champs disent « le modèle » au sens OCR et non au sens pydantic. La promesse de `docs/versioning.md` reste vraie au lieu d'être réduite, et `A4f` la vérifie |
| `A4b` | **Fait le 2026-08-17.** `build` dans `[test]`. Mesuré après : la suite passe de « 2 ignorés » à **zéro ignoré** — les deux gardes tournent et passent |
| `A4c` | **Fait le 2026-08-17.** Le bloc mypy sans hooks est retiré (mypy tourne en CI, où il n'est pas optionnel), et le hook prettier qui visait `frontend/` — parti avec la démo — avec lui |
| `A4d` | **Fait le 2026-08-17, à merger par toi.** Deux jobs : `prepare-release` décide s'il faut publier et **ne peut rien signer** ; `publish` peut signer et n'exécute que des actions épinglées par SHA plus `gh`, préinstallé. Il ne fait même pas de `checkout`, donc aucun jeton git sur disque. **Et il retélécharge les distributions depuis l'exécution de CI vérifiée**, pas depuis le job de préparation — ce que la scission seule laisserait ouvert : un outil compromis là-bas pourrait réécrire la roue avant de la passer, et ses condensats avec, étant le même job. Seul un identifiant d'exécution traverse. Trusted Publishing s'attache au **nom de fichier** du workflow, donc la configuration du *pending publisher* est inchangée | trois exécutions de code non verrouillé partageaient le processus du seul jeton capable de publier |
| `A4e` | **Fait le 2026-08-17.** Le chemin est corrigé, et un test vérifie désormais qu'il **résout** — l'ancien vérifiait ses expressions régulières, pas qu'il puisse démarrer |
| `A4f` | **Fait le 2026-08-17.** Job `saknussemm-min-deps` : minima des dépendances **d'exécution** seulement — l'extra `[test]` n'a aucune borne basse, la résoudre bas testerait autre chose. Un import séparé de pytest, parce qu'un échec d'import est précisément le défaut visé |
| `A4g` | **Fait le 2026-08-17.** `SECURITY.md` écrit — où signaler, ce qui est dans le périmètre et ce qui n'y est pas. La liste des documents normatifs ne nomme plus de document d'API séparé, qui n'a jamais existé. Les trois `cd` vers un répertoire disparu à l'aplatissement sont corrigés, et le README dit enfin comment installer. Garde ajoutée sur les citations **en prose** : l'existante ne lisait que les liens markdown, et il y avait zéro lien cassé sur 61 fichiers pour cinq fichiers citant un document absent | mesuré |

### A5 — Structurel, hors porte `0.10` : la vérité unique du texte décidé

Le manifeste mutable **écrit** l'artefact ; le registre de décisions ne fait que
l'**auditer**. C'est la cause structurelle de deux des défauts d'`A1`, et le
prix en est déjà payé : **18 % des lignes de la suite de tests** existent pour
prouver en permanence que ces représentations racontent la même histoire — un
scanner de code, un test du scanner, et un test attestant que le test qui
atteste tient encore.

Coût compté de la fin de migration : **26 sites dans `src/`** sur 10 modules, un
seul changement de signature (`FormatAdapter.rewrite_file` prend les décisions),
et **le véhicule existe déjà** — un `LineTrace` par ligne est construit
inconditionnellement et porte déjà les deux champs. Prérequis unique : rendre
`traces` non-optionnel, ce qui est une fiction (20 annotations, aucun réglage
public de traçage n'existe). Le vrai coût est dans les tests : 69 écritures de
`corrected_text` sur 43 fichiers.

Bénéfice en **soustraction**, pas en addition. Et ce changement rend
`_verify_projection` tautologique sur le texte, ce qui est le signe qu'il
n'aurait jamais dû être une preuve.

À faire d'ici là, parce que la migration ne peut pas être un préalable à la
correction : un refus au préflight d'un manifeste dont `corrected_text` ou
`status` est déjà rempli. Une ligne de garde contre un contournement de tous les
gardes.

### A6 — Limites à déclarer, pas à corriger — **fait le 2026-08-17**

La revue notait le passage à l'échelle 4,5/10. **Mesuré : exposant temps
1,00 ± 0,02 et mémoire 1,00 de 100 à 20 000 lignes.** Rien n'est quadratique
dans la taille du document. Il n'y avait pas de refonte à faire, il y avait une
enveloppe à publier — et rien, ni le README, ni le contrat, ni le registre des
promesses, n'en disait un mot.

Remesuré par moi plutôt que recopié, sur les trois pages Gallica épinglées
(1215 lignes, 1,99 Mo, sans réseau) :

| | passage identité | avec corrections |
|---|---|---|
| CPU par ligne | 0,21 ms | **0,38 ms** |
| pic mémoire | ×7,3 la source | **×11,9** |
| par ligne | 11,6 ko | **19,1 ko** |

Les chiffres mémoire concordent avec ceux de l'audit (×8,3 ; 11 ko) ; le temps
diffère parce que sa mesure portait sur des documents synthétiques avec un
producteur correcteur. C'est le cas corrigé qui est publié, comme borne haute.

Déclaré au README : l'unité de travail est **un document** et le corpus
appartient à l'appelant (rien ne ruisselle, rien n'est borné pour lui) ; le
paramètre d'échelle est le nombre de lignes **par page**, pas par document ;
la dégradation quadratique du chemin de repli sur une très grande page est
nommée comme à corriger, pas comme à subir ; et le budget de reprise est du
temps mural sérialisé.

Déclaré au contrat : **l'ordre de lecture des pages fait partie du contrat de
sortie** — le code le suppose en prose sans le demander, et un autre ordre
change le sha256 ; **la réentrance est une propriété du moteur, pas de la
composition** — un producteur à état perd 41 courses sur 42 et les deux runs
se terminent « avec succès » ; et **un événement ne nomme pas son run**, donc
un observateur partagé ne peut rien attribuer.

Une garde vérifie que ces énoncés restent présents. En prose et non en
chiffres : une assertion de temps par ligne en CI vacillerait sur une machine
chargée et finirait supprimée.

### A7 — Après la correction : ce qui ne coûte que du temps

Aucun de ces points ne touche la justesse. Ils sont ici pour ne pas être
oubliés, pas pour être faits maintenant — et `A7c` reste sous la règle de gel.

| # | quoi | mesuré |
|---|---|---|
| ~~`A7a`~~ | Le comparateur de similarité est reconstruit à neuf à chaque appel : ~6 fois par couture, jusqu'à 5 par ligne. Le réutiliser ne change aucun comportement | **43 % du temps** d'un run profilé — **prémisse fausse, mais le site cachait un défaut de justesse. Fait le 2026-08-17, voir ci-dessous** |
| `A7b` | `units_containing` redérive les groupes de **toute la page** à chaque chunk qui tombe. La seule vraie quadratique. ~~Dériver une fois par page~~ — **le correctif proposé est faux, voir ci-dessous** | **exposant 2,05 mesuré isolément le 2026-08-17** (l'audit disait 1,77) ; 4,8 s à 3 200 lignes dégradées, ~190 s extrapolé à 20 000 |
| `A7c` | `max_in_flight` intra-page, chunks de premier niveau seulement, la descente restant séquentielle car ses sous-chunks partagent une bourse | prototype **octet pour octet identique** dans 20 configurations, **×12 à ×15**. Prérequis : trier `report.hyphen_splits`, aujourd'hui ordonné par l'exécution |
| `A7d` | `align_tokens` payé jusqu'à 3× par ligne ; `source_for_target` en balayage linéaire par token | correctif de cinq lignes |

**`A7a` : la mesure a réfuté le correctif et trouvé autre chose.** Réutiliser
le comparateur ne rend que **6 %** d'une étape qui pèse 37 % — soit ~2 % du
run, pas assez pour justifier le risque : le coût de `difflib` est dans la
recherche de blocs, pas dans la construction de l'index. En mesurant, l'ordre
d'arguments incohérent que l'audit signalait a mené ailleurs : `ratio()` n'est
asymétrique qu'à cause de l'heuristique **`autojunk`**, active par défaut, qui
au-delà de **200 éléments** traite comme du bruit tout élément présent dans
plus de 1 % du second opérande. C'est une heuristique pour comparer des
*fichiers*, où un élément est une ligne entière ; ici un élément est un
caractère, donc dans 200 caractères de prose l'espace et les lettres courantes
sont tous « populaires ».

Mesuré sur une ligne en forme de colonne de cours — du contenu ALTO ordinaire :

| longueur | caractères corrigés | borne arithmétique du ratio | renvoyé | verdict |
|---|---|---|---|---|
| 107 | 4 | 0,9626 | 0,9626 | accepté |
| **215** | **8** | **0,9628** | **0,0837** | **`too_different_from_source`** |
| 323 | 12 | 0,9628 | 0,0557 | `too_different_from_source` |

La même correction, sur le même texte répété, acceptée sous 200 caractères et
refusée au-dessus. La borne est de l'arithmétique, pas un seuil réglé :
`ratio() == 2M/T`, donc substituer `k` caractères sur `n` sans changer la
longueur laisse au moins `1 - k/n`. `autojunk` la viole de 0,88.

Deux coûts, et le second dure plus longtemps : le refus jette une bonne
correction, mais `source_similarity` est **publié sur chaque ligne** et c'est
le signal naturel pour calibrer la sévérité d'un run — donc un appelant qui
calibre dessus calibre sur un nombre qui s'effondre à un seuil de longueur dont
personne ne l'a averti. Corrigé par `autojunk=False`, et **prouvé neutre** :
sur **27 108 paires** formées de chaque ligne de chaque corpus réel ici, sous
trois producteurs de violences différentes, zéro ratio change et le coût est de
+0,7 %. Il ne pouvait pas en être autrement — la plus longue ligne des corpora
fait 85 caractères, donc l'heuristique ne s'était jamais déclenchée sur quoi
que ce soit de mesuré. **C'est exactement pourquoi rien ne l'attrapait.**
L'incohérence d'ordre d'arguments cesse du même coup d'être latente, plutôt que
d'être rangée : sans `autojunk`, `ratio()` est symétrique.

**`A7b` : la quadratique est confirmée, le correctif proposé ne l'est pas.**
Mesuré isolément le 2026-08-17 sur des pages synthétiques au taux de couples du
corpus, un `units_containing` par chunk qui tombe :

| P | `derive_hyphen_groups` seul | P appels | par appel | exposant |
|---|---|---|---|---|
| 100 | 0,34 ms | 4,5 ms | 0,35 ms | |
| 400 | 1,17 ms | 70,7 ms | 1,41 ms | 2,04 |
| 1 600 | 4,87 ms | 1 166,7 ms | 5,83 ms | 1,99 |
| 3 200 | 9,57 ms | 4 821,4 ms | 12,05 ms | **2,05** |

La dérivation seule est **linéaire** (32× la taille pour 28× le temps) : toute
la quadratique vient du nombre d'appels, pas de leur coût unitaire. Exposant
**2,05**, soit exactement quadratique — l'audit disait 1,77, ce qui sous-estime.

**Mais « dériver une fois par page » est faux.** La dérivation du pool n'est pas
invariante sur la durée de vie d'une page : `split_forward_link` mute les champs
de pointeurs, il est appelé depuis `plan_page` (`planner.py:469`) dans la
branche de grain LINE, et `_descend_granularity` (`driver.py:423`) rappelle
justement `plan_page` en forçant ce grain. Donc l'ordre réel est atteignable :
un chunk tombe et construit le cache, un autre descend et sévère un lien, un
troisième tombe et lit un cache périmé — **il ferait tomber une ligne qui n'est
plus dans l'unité**, silencieusement, et l'invariant de projection ne le verrait
pas puisqu'il compare l'artefact aux décisions dont l'artefact est issu.

Le remède qui tient utilise un canal que la conception a déjà construit pour
ça : `split_forward_link` renvoie un `HyphenSplit` que le `ChunkPlan` porte
précisément pour qu'« un consommateur apprenne que la coupe a eu lieu ». La clé
de cache est donc l'ensemble des splits vus par le workspace, pas la page. Ce
n'est plus cinq lignes, et c'est à faire quand `S1` aura rendu les groupes
autoritaires — d'ici là les champs de pointeurs restent le stockage de
référence, et mettre un cache devant un stockage mutable est le défaut qu'on
vient d'éviter.

Nuance mesurée qui borne `A7c` : les pages du corpus épinglé font 29, 42 et
1 144 lignes, et au grain par défaut une page de 29 lignes est **un seul
chunk** — gain nul. Tout le ×12 vient de la grande page. Sur un corpus de pages
ordinaires, le parallélisme utile est au niveau document, donc chez l'appelant.
**La conclusion de la revue était juste, pour une raison qu'elle n'avait pas
identifiée.**

### A8 — Ce que l'audit a corrigé de la revue externe

Noté parce qu'une revue crue sur parole aurait fait travailler dans la mauvaise
direction, et parce que c'est le meilleur argument pour continuer à mesurer.

- « `LineManifest` largement mutable, des centaines de sites » : **trois**
  écritures dans `src/`, toutes dans le même fichier. Le chiffre de 246 venait
  d'un commentaire du dépôt, et ce commentaire était faux. La conclusion tenait,
  la raison non.
- « L'objet source immuable ferme quatre problèmes » : il en ferme deux.
- « Les relectures disque sont un problème de performance » : 4 % du temps sur
  un fichier réel. Le problème est la fenêtre de corruption, pas la vitesse.
- « `corrected_files` garde tout le document » : 9 % du pic mémoire.
- Et un point où la revue avait raison contre mon premier réflexe : le passage
  périmé de `formats/loader.py` l'était bien.

---

## Règle de gel — applicable immédiatement

> **Levée le 2026-08-11** — condition atteinte, remplacée par une contrainte
> plus étroite : *aucune extension de la surface publique tant que `S3b` n'a
> pas coupé*. Voir « Décisions déléguées » ci-dessus. Le paragraphe d'origine
> est conservé tel quel parce qu'il dit ce que la règle protégeait.

**Aucune fonctionnalité nouvelle tant que `L*` et `R*` ne sont pas fermés.**

Suspendu : nouveau producteur, nouveau format, nouvelle politique de routage,
optimisation de coût, écriture des confiances (`write_wc`), extension de l'API
publique.

Autorisé : correctifs, refactorisation **réductrice**, corpus, mesure,
documentation de vérité, tests.

Corollaire déjà en vigueur, conservé : **aucun correctif ne doit créer un 6ᵉ
chemin de résolution de partenaire.** Un correctif qui en a besoin est le signal
qu'il faut d'abord finir `S1`.

---

## Gate 0 — Licences des corpus — **clos (2026-07-27)**

Tranché, et plus petit qu'annoncé.

- **`corpus/37-GT-BNL/`** — ground truth de la Bibliothèque nationale du
  Luxembourg, **CC0 / domaine public** par déclaration de la BnL elle-même
  (« As part of BnL's AI strategy, we provide the ground truth data that falls
  into the public domain (CC0, see copyright notice) »). Rediffusion libre.
- **`corpus/BnF-bpt6k3265015q/`** — document de presse du 19e siècle, **domaine
  public**, librement téléchargeable depuis Gallica. Nuance consignée plutôt
  qu'ignorée : les conditions de la BnF portent sur la *reproduction numérique*
  et distinguent réutilisation non commerciale (libre) de commerciale (sous
  licence). Un usage comme fixture relève de la première.

**Et la troisième option du plan était déjà vraie** : les corpus vivent à la
racine du dépôt, hors de `packages/saknussemm/`, et `sdist.include` est un
allowlist explicite de quatre entrées. **Aucun corpus ne part dans la wheel ni
dans la sdist** — vérifié, et désormais épinglé par
`tests/test_packaging_excludes_corpora.py`, qui refuse aussi qu'un README de
corpus reparte en « À VÉRIFIER ».

La purge d'historique (`git filter-repo`) n'est donc **pas** requise pour
publier. Elle reste une option de poids (34 Mo + 9,2 Mo dans les objets git),
sur un critère de taille et non de droit.

---

## L — Intégrité de ligne (bloquant)

La promesse unique de cette bibliothèque est la sûreté structurelle. Un défaut
qui altère le texte livré sans trace contredit l'argument de vente lui-même.

**Changement d'approche depuis le 25 juillet.** `L1`, `L2`, `L4` et `L6` étaient
listés comme quatre correctifs indépendants. Ce sont quatre symptômes de deux
absences de modèle. Les traiter séparément recrée le mécanisme d'enlisement
décrit en `S` : quatre correctifs, quatre chemins de plus.

**État : `L*` fermés — `L0`-`L3`, `L5`-`L10` faits, `L4` retiré.** Les deux
défauts qui altéraient le texte livré sans laisser **aucune** trace — ni
compteur, ni erreur — sont fermés. `L4` s'est révélé faux à la vérification
(§4.5 de l'audit du 27) et a laissé `L8` à sa place, qui est fait à son tour :
`exact` ne se revendique plus sur 115 lignes dont le fichier dit autre chose.
`L3` est fermé ; il a fait tomber `L9`, et l'invariant écrit pour couvrir cette
famille a trouvé `L10`. `L5` a élargi `L7` en le corrigeant — la ligne blanche
enjambée a rendu atteignable une paire non adjacente que trois endroits du
découpage supposaient impossible — et `L7` a fermé les deux, plus le reste de
`S1` au passage.

### L0 — Échelle de fidélité de projection — **fait** *(prérequis de L1, L4)*

`_projection_normal_form` (`pipeline.py:280`) fait `" ".join(text.split())` :
l'invariant censé détecter une divergence entre décision et XML est aveugle à
une classe de divergences que le moteur **produit effectivement**. C'est le
défaut le plus grave du dépôt : il touche le mécanisme de crédibilité lui-même.

Le remède n'était pas de durcir l'invariant — `exact` est **inatteignable en
ALTO** pour une partie des cas (`<SP>` ne porte pas de contenu ; un blanc de
bord n'a aucune représentation). Il était de rendre le niveau atteint
**explicite, déclaré et journalisé au rapport**.

Livré (`core/fidelity.py`, 100 % couvert ; 31 tests) :

- échelle ordonnée `exact` → `source_spelling` (ajouté par `L8`) →
  `token_equivalent` → `normalized`, chaque niveau distinguant ce que le
  **format coûte** (`<SP>` ne porte pas de contenu : une suite d'espaces et un
  blanc de bord ne peuvent pas survivre) de ce qui a été **substitué** (U+00A0,
  U+202F, tabulation aplatis en espace ordinaire) ;
- le niveau atteint est une donnée du rapport : `ProjectionStage.fidelity` par
  ligne, `CorrectionReport.projection_fidelity` par run (comptage par niveau).
  Champs additifs et optionnels — pas de bump de `CORRECTION_REPORT_VERSION` ;
- `" ".join(split())` a cessé d'être l'invariant universel : la divergence de
  **mots** lève toujours `ProjectionError`, tout le reste est classé et compté ;
- U+202F est couvert nommément.

Reste ouvert, volontairement :

- **le niveau *visé* comme politique.** Le plan le prévoyait ; l'ajouter
  maintenant étendrait la surface publique en pleine réduction (`S3`) et
  pendant le gel. Le plancher reste « les mots doivent correspondre »,
  inchangé. À rouvrir quand `S3` a arrêté la clôture d'API.
- **le branchement sur les compteurs de perte** — c'est `R8`, Lot 2.

### L1 — Blancs significatifs écrasés — **fait**

U+00A0 et **U+202F** (espace fine insécable — l'espace typographique française
avant `%`, `;`, `!`, `?`, `:`, le cas le plus fréquent sur le corpus visé)
étaient avalés par `\s` dans `_tokenize` (`alto/rewriter.py`) et ré-émis en
`<SP>` ordinaire, qui ne porte aucun contenu.

Correctif : **le tokeniseur ne scinde plus que sur les blancs sécables.** Un
blanc insécable est par définition un endroit où l'on ne coupe pas — sa place
est *à l'intérieur* du `String`, où il traverse l'aller-retour verbatim. Le
répertoire (`_NO_BREAK_SPACES`) : U+00A0, U+202F, U+2007. La classification
d'un token « espace » ne passe plus par `str.strip()`, qui considère un
insécable comme un blanc et le renvoyait donc en `<SP>` — c'était la
substitution elle-même.

Mesuré par `L0`, avant/après, sur le même chemin : U+00A0 et U+202F passent de
`normalized` à `exact`. La tabulation reste `normalized` — c'est une véritable
occasion de coupure, elle n'a pas de représentation ALTO, et le rapport le dit
maintenant au lieu de se taire.

Le `.strip()` du chemin lent est **clos** par `L0` : sa raison technique (le
pavage `HPOS` des enfants de ligne) est valide et documentée, et un blanc de
bord n'a aucune représentation en ALTO. Il sort désormais en
`token_equivalent`, déclaré. Ce qui manquait était la déclaration, pas le
comportement.

Reste ouvert : **le même travail côté PAGE.** `formats/page/rewriter.py` n'a
pas été audité pour cette classe ; PAGE porte son texte dans un nœud
`Unicode`, donc le mode de perte n'est pas le même et peut très bien ne pas
exister. À vérifier, pas à supposer.

### L2 — Signe de coupure doublé — **fait**

La déduplication qui empêche `String "Ober-"` + `HYP "-"` de rendre `Ober--` ne
testait que le tiret ASCII. Tous les autres signes du répertoire doublaient :
`Ober⸗` + `HYP "⸗"` se relisait `Ober⸗⸗`, `Ober¬` en `Ober¬¬`.

Silencieux parce que `reconstruct_textline` alimente **les deux côtés** de
l'invariant de projection — le `ocr_text` du parseur et la comparaison
UNTOUCHED du réécrivain : une erreur ici est commise identiquement des deux
côtés et se compare égale à elle-même. Ni `L0` ni aucun compteur ne pouvaient
la voir.

Correctif : la déduplication porte sur le répertoire (`_DEDUP_MARKS`), pas sur
`"-"`.

**Portée honnête** : aucun document des corpus du dépôt ne déclenche ce défaut
— vérifié, `corpus/37-GT-BNL` et `examples/X0000002.xml` n'ont aucune
combinaison `String`-avec-signe + `HYP`. C'est un chemin de corruption
silencieuse **latent**, reproduit synthétiquement par l'audit du 25. Réel, à
fermer, mais il ne faut pas lui prêter un effet mesuré qu'il n'a pas.

### L4 — U+00AD → `-` : **retiré, le constat était faux**

Le plan disait « décision ≠ octets du fichier ». Vérification faite, les octets
ne divergent pas : la collapse porte sur le texte *logique*, elle est
délibérée et documentée (`core/_norm.clean_content`, même raison), et les
chemins de réécriture réémettent le `<HYP>` d'origine avec son propre
`CONTENT` — le caractère source survit sur le disque.

Et elle est **portante** : 115 lignes de `examples/X0000002.xml` portent leur
signe dans le `<HYP>` seul, en U+00AD. Sans la collapse elles ne finissent pas
sur un caractère de coupure et ne s'apparient pas. Tenter de « corriger » ceci
casse dix tests dont la parité d'octets du seul corpus BnF du dépôt.

Ce qui reste, et qui n'est **pas** ce que disait `L4` : la normalisation n'est
déclarée nulle part. C'est un événement de classe `normalized` au sens de `L0`,
sur un caractère qui n'est pas un blanc → nouvel item `L8`.

Preuve et détail : `AUDIT-2026-07-27.md` §4.5.

### L8 — Substitutions hors blancs — **fait, et un des deux cas était déjà bon**

`L0` classait les substitutions de **blancs**. Deux substitutions de caractère
non-blanc étaient soupçonnées de ne remonter nulle part. Vérification faite,
**une seule** l'était.

**`preserve_break_char` : déjà déclaré.** Le pipeline force le signe de coupure
de la source *avant* que les décisions se matérialisent, et
`ProposalStage.output_text` conserve le texte **brut** du producteur. Un
consommateur voit donc `tou-` proposé et `tou¬` décidé, côte à côte dans le
rapport. Le commentaire du site d'application le dit déjà. Rien à faire —
résultat négatif utile, du même genre que l'invariant de symétrie.

**La collapse U+00AD : `exact` était un mensonge sur 115 lignes.** Le niveau
`EXACT` promet « l'artefact dit la décision, **caractère pour caractère** ». Sur
115 des 566 lignes de `examples/X0000002.xml`, le fichier porte son signe de
coupure en U+00AD dans le `<HYP>`, la reconstruction le relit `-`, la réécriture
réémet l'élément source intact — et le run classait les 115 en `exact`.

Il ne pouvait rien classer d'autre : **la collapse s'applique aux deux côtés de
la comparaison et s'égale à elle-même.** Même mécanisme d'aveuglement que `L2`.
Le remède n'est donc pas un invariant plus strict, c'est de donner à l'invariant
une seconde lecture — `RewriteResult.texts_verbatim`, le même parcours d'arbre
avec la table de substitution **désactivée**.

Nouveau niveau, **`source_spelling`**, entre `exact` et `token_equivalent` :
l'artefact dit la décision mais orthographie un caractère comme la **source**,
là où la décision porte la lecture normalisée. **Rien n'est perdu** — le fichier
est *plus* précis que la décision — et c'est précisément pourquoi le niveau est
au-dessus de `token_equivalent`, qui lui perd une suite de blancs pour de bon.
Classer un désaccord sans perte sous une perte réelle inverserait le sens de
l'échelle.

Mesure après correctif, sur le fichier BnF : **451 `exact`, 115
`source_spelling`, 0 `normalized`** — et les 115 sont exactement les lignes à
`<HYP CONTENT="U+00AD">`, épinglé par égalité d'ensembles, pas par comptage.

**Conséquence pour `R8`, à ne pas manquer** : « une substitution déclarée est
une perte comptable » est **faux pour `source_spelling`**. Le fichier garde son
caractère ; le compter en perte fabriquerait un fantôme — la forme de `R1`.
`R8` ne doit brancher la comptabilité que sur `normalized`.

PAGE ne substitue rien à la lecture (NFC + `strip`) et livre donc un
`texts_verbatim` vide. Ce n'est pas supposé : un test vérifie que le texte
logique de chaque ligne se retrouve **caractère pour caractère** dans les octets
livrés (échappement XML mis à part). ALTO et PAGE en désaccord silencieux sur la
même classe d'événement est exactement ce que `R4` a dû revenir corriger.

### L6 — Répertoire de coupure — **fait, sur mesure**

`HYPHEN_CHARS` passe de 4 à 6 : ajout de **U+2010 HYPHEN** et **U+2011
NON-BREAKING HYPHEN**.

Élargir n'est pas neutre — un nouveau membre fait apparier des lignes qui ne
l'étaient pas — donc chaque membre est là sur **preuve**. Mesuré sur les 40
fichiers ALTO/PAGE de `examples/` et `corpus/`, contenu textuel seulement :

| signe | occurrences | en fin de ligne |
|---|---|---|
| `-` U+002D | 238 | 119 |
| `⸗` U+2E17 | 36 | 25 |
| `¬` U+00AC | 0 | 0 |
| U+2010, U+2011, U+2013, `=` | **0** | **0** |

Les deux ajoutés sont **prouvablement sans effet** sur les corpus existants :
couverture latente pour un producteur qui les emploie, et rien d'autre que ces
caractères puissent signifier.

**`=` et U+2013 restent exclus**, pour la même raison : ils portent d'autres
sens (signe égal d'un tableau ; tiret de dialogue ou intervalle) et les corpus
ne donnent **aucune preuve** qu'ils soient nécessaires. La contrainte de
caractère alphabétique de `trailing_hyphen_char` écarte `1789–` mais pas une
ligne finissant sur un tiret de dialogue. Les admettre demande une mesure sur
un corpus qui en contient (`M7`), pas une édition de tuple.

### L3 — Membre inter-pages gelé sur son OCR — **fait**

Le réconciliateur possédait un join depuis sa **queue** : il réconciliait si la
queue était une cible du chunk. Pour une paire intra-page, très bien — les deux
membres sont en portée ensemble. Pour une paire **inter-pages**, c'était
inatteignable : la queue est toujours sur la page antérieure et décidée avant
que la tête n'existe, donc la passe de la queue lisait le texte de la tête dans
une réponse qui ne la mentionnait pas, retombait sur l'OCR brut, et écrivait ça
comme décision de la tête avec `status = CORRECTED`. La page suivante sautait
alors la ligne (`corrected_text is not None`) et jetait la correction qu'elle
venait de payer.

Correctif : **un join qui quitte la page appartient à sa tête** — le seul point
où les deux côtés existent.

Ce qui a rendu ça possible : `pairing.backward_partner_ref`, le miroir de
`forward_partner_ref`. Que cette direction n'ait **jamais eu de nom** est la
cause, pas un détail : sans arête entrante nommée, un join ne pouvait
appartenir qu'à sa queue. Les deux `xfail(strict)` sont passés en XPASS et sont
devenus des tests ordinaires.

Effet de bord requis : `_reconcile_one_pair` préfère désormais
`corrected_text` du côté queue — une queue inter-pages porte sa décision sur le
manifeste, pas dans la réponse du chunk courant.

### L10 — Coupure avant perdue sur une ligne à rôle mixte — **fait**

**Trouvé par un test, pas par une lecture** — le premier de la session.

`PAG_00000002_TL000454` de `examples/X0000002.xml` est `BOTH` : elle ouvre sur
un `SUBS_TYPE="HypPart2"` explicite et finit sur un simple tiret heuristique,
sans `<HYP>`. Lien arrière explicite, coupure avant heuristique, sur une seule
ligne.

Le réécrivain décidait de retirer le tiret du `String` en lisant
`hyphen_source_explicit` — qui décrit le lien **arrière**. Réponse
« explicite », donc il retirait le tiret en supposant qu'un `<HYP>` le rendrait.
Il n'y en a pas : **le signe disparaissait du fichier livré.**

Correctif : `pairing.forward_break_is_explicit`, la carte rôle→slot appliquée
au bon drapeau. Diff classé par TextLine sur le corpus réel : **1 sur 566**,
`Wal` → `Wal-`, rien d'autre. Le hash d'or épinglait le défaut.

### L9 — Une paire révoquée était rapportée `corrected` — **fait**

Trouvé en écrivant le test de la paire inter-pages incohérente, et **pas
limité à l'inter-pages** : `_reconcile_one_pair` posait `status = CORRECTED`
inconditionnellement, y compris quand `reconcile_hyphen_pair` avait fait
retomber **les deux** côtés sur leur OCR faute de cohérence. Deux lignes
gardaient donc leur texte source en se déclarant corrigées : aucun compteur de
fallback, aucun motif. Exactement la forme silencieuse de `L3`, sur un autre
chemin.

Le statut suit maintenant l'issue. `classify_reconcile_outcome` ne dit
« fallback » que si quelque chose a été proposé **et** jeté, donc une
correction identité reste `CORRECTED`.

**Deux tests épinglaient ce défaut** et affirmaient qu'un « clean run »
rapportait zéro fallback. Vérifié : sur ces fixtures la substitution casse le
mot joint, la paire est légitimement révoquée, et les deux lignes gardaient
bien leur OCR. Ils disent maintenant la vérité, et un vrai baseline
« ne change rien » a été ajouté à côté.

Les traces des deux membres sont rafraîchies par le réconciliateur : une queue
révoquée dont la page est déjà close n'a plus rien en aval pour corriger sa
trace, et `derive_decision_set` **lit le motif sur la trace** — sans ça, le
rapport montrait un fallback au motif vide.

### L5 — Cas restants de détection

**Fait (2026-07-28) sauf deux, et les deux qui restent demandent de la
géométrie, pas un correctif.**

Faits antérieurement : ~~page vide sautée~~, ~~PART1 sans partenaire annonçant
`join_with_next=True`~~, ~~rejet de `PairingPolicy` silencieux~~.

#### Le répertoire, dans les gardes — 32 lignes sur 363, mesurées

`HYPHEN_CHARS` a six membres et les parseurs s'en servent tous, donc une ligne
peut légitimement être PART1 en finissant par `⸗` ou `¬`. **Cinq sites de garde
testaient pourtant le seul tiret ASCII** (`endswith("-")`, `rstrip("-")`).

| signe | lignes PART1/BOTH |
|---|---|
| `-` U+002D | 331 |
| `⸗` U+2E17 | **24** |
| `¬` U+00AC | **8** |

**32 sur 363 — 8,8 %** tombaient hors de *toutes* ces vérifications. Pas
latent : `corpus/37-GT-BNL` est du Fraktur et son signe de coupure est `⸗`.

Conséquences réelles, chacune avec le test qui échoue avant :

- **garde orphelin** (`pipeline`) : un `⸗` supprimé par la correction n'était
  pas rattrapé — la ligne livrée ne disait plus que le mot continue ;
- **garde de croissance PART1** (`hyphenation`) : le signe restait collé au
  texte nu, donc chaque comparaison de longueur portait sur une chaîne **un
  caractère plus longue** que sa contrepartie. Le seuil étant un compte de
  caractères (`part1_last_word_char_growth`, 3), une complétion de mot de 4
  caractères se lisait 3 et passait ;
- **détection de fusion** (`validator`) : un modèle qui complète le mot **et**
  garde le signe (`nécessaires⸗`) ne correspondait jamais au mot logique — la
  fusion passait la validation alors que le texte de PART2 avait déjà migré.

Deux primitives dérivées du répertoire (`ends_with_break_mark`,
`strip_trailing_break_marks`) dans `pairing.py`, seul domicile du répertoire.
`ends_with_break_mark` n'impose **pas** la contrainte de caractère alphabétique
de `trailing_hyphen_char` : ses appelants savent déjà que la ligne coupe un mot
(le rôle le dit, éventuellement depuis un `SUBS_TYPE` explicite), et la
réimposer désarmerait une ligne explicitement marquée finissant par un chiffre.

#### La ligne vide — la même phrase que la page vide

`link_hyphen_pairs` prenait `lines[i + 1]`. Une ligne blanche entre un PART1 et
sa vraie continuation devenait donc le PART2 : elle ne porte aucun texte, donc
rien ne se réconcilie, les gardes de dérive de paire ne tournent jamais, et la
continuation réelle reste non liée. Même conséquence que le défaut page vide,
une échelle en dessous — et **la même phrase la règle** : une ligne sans texte
ne peut rien dire d'un mot qui l'enjambe ; c'est un fait sur le scan, pas sur la
phrase.

Appliqué aux **deux** parcours, avec une seule définition (`_substantive`) pour
que « une ligne vide ne porte rien » ne finisse pas par signifier deux choses.
Ça ferme aussi la facette « `link_cross_page_hyphens` ne regarde que
`lines[-1]`/`lines[0]` » : une blanche au pied d'une page ou en tête de la
suivante cachait un mot qui enjambe la couture. **Latent** — 0 ligne vide sur
1711 — donc onze tests, aucune mesure.

#### Ce qui reste, et pourquoi ce n'est pas un correctif

- **chaîne mixte jetant l'autorité `SUBS_CONTENT`** ;
- **cross-bloc en ordre de lecture dégradé**, et l'autre facette de
  `lines[-1]`/`lines[0]` : un en-tête ou un numéro de page en tête de page
  suivante n'est pas une ligne vide, c'est une ligne **hors ordre de lecture**.
  Décider qu'elle n'est pas la continuation demande de la géométrie — ce qui est
  exactement le métier de `PairingPolicy`, qui vet déjà les paires heuristiques
  géométriquement. Le trancher demande un corpus qui en contient (`M7`), pas une
  édition de prédicat.

### L7 — Découpage — **fait (2026-07-28)**, une racine pour trois symptômes

Les trois items étaient **le même défaut à trois endroits** : demander
« mon partenaire est-il la ligne **suivante** ? » au lieu de « **où** est mon
partenaire ? ». Et le troisième item n'était pas indépendant — il tombait avec
les deux autres.

**L'invariant, écrit comme tel.** Une paire liée n'a que deux issues légitimes
au moment du plan : **ensemble dans un chunk**, ou **coupée avec un
`HyphenSplit` sur le plan**. Ni l'un ni l'autre est un trou silencieux — le
validateur écarte une paire qui n'est pas entièrement dans le chunk, et le
réconciliateur pourrait écrire par-dessus la frontière.

**Et mon propre correctif `L5` avait élargi le trou.** Le suivi de chaîne de
`_plan_line` exigeait l'adjacence stricte ; dès que l'appariement a su enjamber
une ligne blanche, une paire liée `L0 → L2` échouait au test, la chaîne
s'arrêtait, les deux membres tombaient dans des chunks différents et le lien
restait **vivant**. Mesuré avant correctif :

```
chunks: [['L0'], ['L1'], ['L2'], ['L3']]
splits: []
L0 still linked to: L2
```

- **`_plan_line`** suit désormais le **lien** (une *recherche* id→position, pas
  un résolveur — la distinction que `S1` a posée), emmène les lignes
  intercalées avec la paire plutôt que de les laisser hors de tout chunk, et la
  condition de coupure devient « mon partenaire n'est pas dans mon chunk » au
  lieu de « le plafond m'a coupé » : les deux coïncidaient seulement tant que
  l'adjacence était requise. Un partenaire **hors page** (paire inter-pages,
  propriété du join de `L3`) ou **en arrière** n'est ni suivi ni coupé.
- **`_try_window`** avait la même racine, via `should_stay_in_same_chunk` —
  précisément la « troisième formulation » que `S1` laissait à absorber.
  Remplacée par `_unit_reach`, qui répond à la vraie question : *jusqu'où cette
  fenêtre doit-elle aller pour contenir tout lien qui en sort ?* Le prédicat
  pairwise était faux dans **deux** directions — il ne voyait ni un lien
  partant d'une ligne **antérieure** de la fenêtre, ni un partenaire non
  adjacent. **Absorbé et supprimé** : un seul appelant en production.
  **`S1` n'a plus de reste.**
- **Le troisième item — « la descente ne rapatrie pas les partenaires
  non-cibles » — n'est pas un défaut indépendant.** Mesuré : le ciblage de
  fenêtre (`_assign_window_targets`, qui utilise déjà la dérivation partagée)
  force les deux membres d'une paire dans la même fenêtre. Balayage de **3708
  chunks** sur 7 formes de page × une grille de configurations : **45
  violations, toutes de la forme « paire par-dessus une blanche »**, c'est-à-dire
  la paire non adjacente. Zéro après le correctif de fenêtre. Fermé par la même
  racine, sans code propre.
- **`_split_for_image_cap`** posait une autre question à la mauvaise fonction.
  `_page_local_units` répond « est-ce l'unité **entière** ? » et rend *rien*
  quand non — ce qui est juste pour le **routeur** : escalader une demi-unité la
  couperait, donc une unité incomplète reste au producteur primaire et ses
  membres restent ensemble **en ne faisant rien**. Le batcher n'a pas cette
  option : il **découpe** un chunk en appels, donc « ne rien faire » n'existe
  pas. Sans unité, il traitait chaque membre en singleton et pouvait mettre une
  paire dans deux appels. Deux formes y arrivaient : un groupe dont le dernier
  pointeur **pend**, et un groupe qui **continue sur une autre page** (son
  membre distant n'est pas là, ceux qui le sont appartiennent au même appel).
  Nouveau `_units_visible_on_page` — même dérivation partagée, zéro lecture de
  pointeur, **projection différente** : les membres présents, entiers ou non.

Les tests sont l'invariant, pas la forme du correctif : 48 combinaisons
forme × plafond, plus les cas qui ont exposé le défaut avec leurs chiffres.
Vérifié en revertant : **18 rouges** sur le planificateur, **3** sur le batcher.

Détail et preuves : `AUDIT-2026-07-25.md` §3a, §3c, §3d ; `AUDIT-2026-07-27.md`
§2.6, §3.1, §3.2, §4.3, §4.4.

---

## R — Comptabilité honnête (bloquant)

« Toute perte comptée » est une revendication d'auditabilité faite dans les docs
du projet. Elle était fausse **dans les deux sens** — ce qui est pire qu'une
absence de comptabilité, parce que le chiffre a l'apparence d'une garantie.

**État : `R0` à `R8` fermés (2026-07-28).** Deux des neuf se sont fermés par
mesure plutôt que par code — `R3` était plus étroit que son énoncé, `R8` était
déjà compté et c'est la *revendication* qui était fausse — et un troisième
(`R7`) est documenté et testé plutôt qu'armé, parce que l'armer changerait la
sortie livrée sans seuil mesuré. Le fil conducteur des neuf est **une** règle :
un événement, un compteur. Deux sites de comptabilité pour un même événement
sont libres de diverger, et c'est exactement ce qu'était `R1`.

| id | item |
|---|---|
| ~~R0~~ | **fait** — `core/losses.py`, matrice **versionnée et exécutable** (`LOSS_MATRIX_VERSION`). Écrite depuis la mesure, pas depuis la croyance : chaque sort a été observé sur les deux fixtures réelles × les trois chemins d'écriture. La distinction qui manquait : `STRUCTURAL` (l'attribut suit le token — le chemin lent passe de 3395 à **3963** `HPOS` parce qu'il écrit *plus* de mots, pas parce qu'il en perd) vs `SEMANTIC` (une assertion sur une lecture ; sa disparition est une perte). Quatre sorts : `PRESERVED` / `REWRITTEN` / `INVALIDATED` / `DROPPED`, plus `ALIGNMENT_SCOPED` pour ceux dont la perte est conditionnelle et comptée par une seconde passe. **Le réécrivain consomme la matrice** — il ne détient plus de seconde liste, et deux listes pour un attribut est précisément la forme de `R1`. Vérifiée par `test_loss_accounting_is_real.py` |
| ~~R1~~ | **fait** — `SUBS_TYPE`/`SUBS_CONTENT` étaient comptés perdus alors que `_apply_subs` les réécrit sur les **trois** chemins d'écriture. Mesuré avant correctif : **229 de chaque** revendiqués sur une seule page réelle de 566 lignes dont le fichier de sortie en porte exactement autant que la source. Trouvé par l'invariant différentiel `R0-test` |
| ~~R2~~ | **fait (2026-07-28)** — la reconstruction a **deux sorties** : une correction qui vide la ligne revient *avant* tout alignement (il n'y a aucun token cible sur quoi aligner), et cette sortie ne comptait aucun `STYLE`/`STYLEREFS`. Rien d'aligné veut dire tout perdu. **56 lignes** des corpus ALTO du dépôt portent ces attributs. Corrigé par **une** fonction de comptabilité appelée aux deux sorties — une seconde copie en ligne est exactement comment `R1` est arrivé |
| ~~R3~~ | **fait (2026-07-28), et plus étroit que l'énoncé.** « `<HYP>` d'une PART2 » évoque une ligne de continuation portant aussi un signe final : ce n'est **pas** une PART2. Le parseur lit le signe terminal comme une coupure avant, classe la ligne `BOTH`, et le `<HYP>` est **réémis**. Le seul chemin réel est un `<HYP>` **non terminal** — qu'ALTO ne définit pas, que le parseur tolère, et où l'élément part en silence. Compté `hyp_elements_removed` : ce qui part est l'**élément** (sa géométrie, son statut de balisage), pas le signe, dont le caractère revient dans le `CONTENT` reconstruit. Les deux moitiés sont assertées pour que personne ne « corrige » ça en resynthétisant un HYP qui doublerait le signe. **0 des 1711 lignes ALTO** des corpus ont cette forme : chemin latent, épinglé comme `L2` l'a été |
| ~~R4~~ | **fait (2026-07-28) — comptés, par LIGNE.** `WC`/`CC` n'étaient comptés nulle part en ALTO pendant que PAGE comptait `conf_dropped` **par occurrence** : silence d'un côté, unité incomparable de l'autre. Les deux arguments avaient raison sur des unités différentes, et l'unité était toute la décision — voir ci-dessous |
| ~~R5~~ | **fait (2026-07-28)** — le drapeau voyageait dans le dictionnaire de pertes, donc `sum(format_losses)` comptait un non-événement : rien n'a quitté le balisage, l'alignement n'a simplement pas pu se porter garant de l'ordre qu'on lui a remis. Il a son propre canal (`RewriteResult.word_order_suspected` → `ProjectionStage.word_order_suspected`). Signalé, jamais appliqué — inchangé |
| ~~R6~~ | **fait (2026-07-28)** — `CorrectionReport.hyphen_splits`. Et une mesure au passage : un split **n'arrive qu'à la granularité `LINE`**, que l'auto-sélection du planificateur n'atteint jamais (PAGE → BLOCK → WINDOW) ; le seul chemin réel est la **descente après échec de chunk**. L'événement est donc rare, et le test doit passer par cette porte-là. Ce qu'aucun autre champ ne dit : le split **remet le rôle de la queue à `NONE`**, donc `unpaired_breaks` — qui ne regarde que les lignes voulant encore un partenaire — y est aveugle par construction ; les deux côtés gardent leur texte, donc ce n'est pas un fallback ; rien ne quitte le balisage, donc ce n'est pas une perte de format. Ce que l'hôte reçoit est une ligne livrée dont le texte finit au milieu d'un mot et qui ne déclare aucune coupure |
| ~~R7~~ | **fait (2026-07-28) — documenté et épinglé, pas armé.** `word_count` n'est peuplé que par le parseur PAGE, donc `strict=True` sur un document ALTO rend **exactement** le comportement par défaut, en silence. La docstring le dit désormais franchement, et ajoute ce qui manquait vraiment : ce n'est **pas** « une réécriture ALTO ne perd rien ». Un changement de compte de mots reconstruit la ligne et lâche `TAGREFS`/`language`/attributs vendeur + le `STYLE` des `String` non alignés — **rapportés, gatés par aucun mode**. Armer la garde pour ALTO changerait la sortie livrée : ça demande un seuil mesuré, pas un drapeau retourné en passant. Trois tests tiennent les deux moitiés (`test_loss_policy_scope.py`) |
| ~~R8~~ | **fait (2026-07-28) — clos par la mesure, sans ajouter de compteur.** La perte **est déjà comptée** : une ligne `normalized` est agrégée par `projection_fidelity` et attribuée par ligne sur `ProjectionStage.fidelity`. Ce qui était faux, c'est la revendication autour : sur un run où une tabulation est aplatie, `format_losses` vaut **`None`** — et qui lit ce champ seul conclut « sans perte ». Corrigé dans le contrat aux trois endroits qui le disaient. **Et refuser d'ajouter une clé à `format_losses` est la même décision que `R4`** : elle coïnciderait avec `projection_fidelity["normalized"]` sur *tous* les runs par construction, et deux sites de comptabilité pour un événement sont libres de diverger par la suite — c'est ce qu'était `R1`. Les deux moitiés sont assertées : la perte est trouvable, et trouvable **à un seul endroit**. `source_spelling` reste hors comptabilité (`L8`) : le fichier garde son caractère |

### `R6` — une ride observée en l'épinglant, laissée telle quelle

`LineOutcome.hyphen_role` vient de la **trace** de la ligne, écrite quand son
chunk a été enrichi la première fois. Un split arrive **plus tard** — pendant la
descente de granularité qui suit un chunk en échec — donc une queue coupée peut
être rapportée avec le rôle qu'elle avait **avant** la coupure (`HypBoth` là où
le manifeste dit désormais `HypPart2`).

C'est un second problème de vérité, plus étroit que `R6`, et que le nouveau
champ ne corrige pas : c'est précisément pourquoi le split a besoin de son
**propre** enregistrement plutôt que d'être déduit des rôles du rapport. Épinglé
par un test (`test_the_reported_role_can_predate_the_split`) pour que ce soit
une quantité connue, et pour qu'un futur correctif ait un test à retourner.

---

### `R4` — l'unité était toute la décision (2026-07-28)

Le choix n'était pas « compter ou se taire », c'était **en quoi compter**.

| unité | ce que ça donne sur `X0000002.xml` (566 lignes) |
|---|---|
| par occurrence (ce que faisait PAGE) | **3339** |
| par ligne (retenu) | **566** en chemin lent, **492** en chemin rapide |
| silence (ce que faisait ALTO) | 0 |

Par occurrence, le compteur varie avec la **verbosité d'une ligne** et pas avec
ce sur quoi un archiviste agit ; à quatre chiffres il noierait les compteurs à
trois chiffres posés à côté. Par ligne, il énonce le fait : *ces lignes ne
portent plus la confiance du moteur.* C'est aussi la seule unité que le reste
du rapport parle — toute autre entrée de `format_losses` est attribuable à une
ligne (ADR-012), une valeur par occurrence ne l'aurait pas été.

**L'écart 492 / 566 est le contrôle qui compte.** Le chemin rapide ne retire
`WC` que des `String` dont le `CONTENT` a réellement bougé : 74 lignes gardent
leur confiance intacte, et le compteur le voit. Il est calculé par mesure
avant/après sur l'élément, pas déduit du chemin emprunté — « la ligne a été
réécrite » n'est pas « la ligne a perdu sa confiance », et c'est exactement le
genre de raccourci qui a produit les fantômes de `R1`.

Fait en un commit sur les deux formats, comme la matrice l'exigeait :
`COUNTS_INVALIDATION = True`, `INVALIDATION_UNIT = "line"`,
`INVALIDATION_COUNTER = "confidence_invalidated"` — une clé unique, émise par
ALTO **et** PAGE (`conf_dropped` disparaît). `LOSS_MATRIX_VERSION` passe à
`"2"`. La passe par `String` est tenue à l'écart des attributs `INVALIDATED`
(`is_unconditional_loss`), sans quoi le même attribut serait compté deux fois —
la forme de `R1`, encore.

---

## S — Dette structurelle

Le mécanisme d'enlisement est identifié : `derive_hyphen_groups` a été
introduite pour unifier quatre façons de demander « qui est le partenaire », est
bien utilisée, mais **les quatre anciennes n'ont jamais été retirées**.
L'unification a atterri en ajout — cinq chemins au lieu de quatre.

**Première tranche faite (2026-07-27) — par soustraction, pas par ajout.**

- `planner._hyphen_partner_id` supprimé : **zéro appelant**. Le mécanisme pris
  en flagrant délit — `derive_hyphen_groups` avait remplacé son usage, la
  fonction n'a jamais été retirée. 5 résolveurs → 4.
- `pipeline._page_local_hyphen_unit` remplacé par `_page_local_units`, qui **ne
  lit plus aucun champ pointeur** : il interroge la dérivation partagée. 4 → 3.
- Ce qui a rendu ça possible sans dupliquer la traversée : `HyphenGroup.complete`,
  calculé **dans la boucle qui lit déjà les pointeurs**. Un consommateur qui doit
  déplacer une unité entière (routeur, batcher de la limite d'images) doit
  distinguer « voici toute l'unité » de « voici la part que je vois » ; il pose
  désormais la question au groupe. La reposer aux pointeurs est exactement
  comment un résolveur parallèle apparaît.
- Effet de bord : la dérivation est faite une fois par page, plus une fois par
  ligne — l'ancienne marche était quadratique en densité de césures.

**Deuxième tranche faite (2026-07-27).** `pipeline._hyphen_closure` supprimé,
remplacé par `units.units_containing` : la seconde marche à point fixe sur les
pointeurs a disparu. **5 résolveurs → 2.** Personne n'a rien vu passer — la
suite entière est restée verte au moment de l'échange, ce qui montrait
justement qu'aucun test n'exerçait la différence entre les deux encodages.
Sept tests l'épinglent désormais.

### Correction de la cible de `S1`

Le plan visait « **1** résolveur ». C'est faux, et une mauvaise cible produit
un mauvais refactor. La cartographie montre **deux notions distinctes**, à
garder distinctes :

| notion | question | primitive |
|---|---|---|
| arête **dirigée** | « sur quelle ligne mon mot continue-t-il ? » | `forward_partner_id` |
| **unité** non dirigée | « quelles lignes voyagent ensemble ? » | `derive_hyphen_groups` |

Les confondre est ce qui a produit les encodages parallèles. La bonne cible est
**une primitive dirigée + une dérivation d'unité**, pas une seule fonction.

**Troisième tranche faite (2026-07-27) — la primitive dirigée existe.**
`pipeline._resolve_partner` supprimé. **5 résolveurs → 0 doublon.** Ce qui
reste est la forme cible :

| | rôle |
|---|---|
| `pairing.pair_ref` / `forward_ref` | lisent **un** créneau, qualifié par page |
| `pairing.forward_partner_ref` | la carte rôle→créneau, et la seule |
| `pairing.forward_partner_id` | l'id nu, délègue — pour les recherches déjà limitées à une page |
| `units.derive_hyphen_groups` / `units_containing` | la dérivation d'unité |
| `pipeline._lookup_ref` | une **recherche**, pas une résolution : ref → manifeste |

**Le piège que ça ferme, et il valait le détour.** Les deux créneaux de liens
s'appellent `hyphen_pair_*` et `hyphen_forward_*` — et « forward » nomme le
**créneau**, pas la direction de lecture. Le mot d'une ligne `PART1` continue
sur la ligne de son créneau **PAIR** ; seule une ligne `BOTH` utilise le
créneau FORWARD pour ça. Le réconciliateur du pipeline avait cette carte
épelée **inline**, à deux lignes d'un helper qui la connaissait déjà. Seize
tests l'épinglent désormais (`tests/test_directed_link.py`), avec des leurres
dans les deux créneaux.

Lectures de champs pointeurs, par module : `pairing.py` 22 (c'est sa
fonction), `units.py` 13, `pipeline.py` **8** (était 18), `planner.py` **0**,
`hyphenation.py` **0**.

Reste `should_stay_in_same_chunk` (hyphenation) — prédicat mince sur
`forward_partner_id`, troisième formulation. À absorber ou à assumer.

Et reste le **vrai** cœur de `S1` : rendre l'unité **autoritaire**, c'est-à-dire
que la décision appartienne à l'unité et se projette sur les lignes physiques,
les pointeurs devenant dérivés. Le blocage est nommé et il est favorable :
`split_forward_link` est le **seul** mutateur de pointeur après le parsing
(vérifié — tous les autres sites sont dans les parseurs et `link_hyphen_pairs`),
et il est appelé par le planificateur. Une fois une page planifiée, ses
pointeurs sont figés pour l'exécution. Dériver l'index **après chaque
(re)planification** — descentes de granularité comprises — suffit ; il n'y a pas
de mutations dispersées à traquer.

Attention conservée : le site « un partenaire est-il tombé en fallback ? »
n'interroge que les partenaires **directs**, pas la chaîne transitive. Passer au
groupe élargit le comportement sur les chaînes de 3+ — défendable au titre de
l'atomicité, mais c'est un changement à mesurer, pas à glisser. Le commentaire
le dit sur place.

### Décision (2026-07-27) — on s'arrête là, et `V3` est reformulé

**Le cœur de `S1` ne sera pas fait maintenant.** Le travail de cette session a
déjà capturé l'essentiel de sa valeur par des moyens beaucoup moins chers :

- la carte rôle→créneau ne vit qu'à un endroit ;
- une seule dérivation d'unité existe, et elle porte `complete` ;
- **l'invariant de symétrie** (`tests/test_link_symmetry.py`) teste que les
  pointeurs restent cohérents des deux bouts, sur corpus généré et fixtures
  réelles ;
- `split_forward_link` est **vérifié** comme seul mutateur post-parsing.

Le danger des pointeurs-comme-vérité était qu'ils se désynchronisent sans que
personne le voie. Trois tests le voient maintenant.

Ce que le refactor apporterait encore : rendre l'état illégitime
**inexprimable** plutôt que testé — une garantie de type, pas de suite.
Ce qu'il coûterait : le plus gros risque de régression du dépôt, sur la partie
la plus chargée du moteur, pour fermer un écart déjà surveillé.

`V3` est donc reformulé en « une famille de primitives dirigées + une
dérivation d'unité, cohérence tenue par invariant » — et il est **atteint**.

**À rouvrir seulement si `S2` le rend nécessaire.** Scinder les 3152 lignes de
`pipeline.py` pourrait l'exiger ; à ce moment-là les deux se font ensemble, et
pas avant.

### `S3` — la clôture, établie par calcul (2026-07-27)

Choisir la surface à la main, c'est comment on arrive à 95. Elle a donc été
**calculée** : partir de ce que `load` / `correct` / `correct_sync` retournent,
et suivre les annotations de type transitivement.

**Clôture des retours : 33 types.** 30 sont déjà exportés. **4 trous** — des
types qu'un appelant rencontre en typant la valeur de retour et qu'il ne peut
pas importer depuis le sommet :

| manquant | pourquoi il compte |
|---|---|
| `Coords` | la géométrie de chaque ligne du manifeste |
| `ProjectionFidelity` | le niveau que `L0` a mis sur `ProjectionStage` |
| `ReconcileMetrics` | porté par `CorrectionResult` |
| `CORRECTION_REPORT_VERSION` | `docs/versioning.md` dit aux consommateurs de **dispatcher dessus** (`D5`) — et `EDIT_PROTOCOL_VERSION`, lui, est exporté |

**Constat qui change la cible.** Le backend — le seul intégrateur réel —
**n'utilise ni `load`, ni `correct`, ni `correct_sync`**. Il passe par la porte
bas niveau : `CorrectionPipeline`, les policies, et les entrées de format par
leur chemin de module. Ce n'est pas un détail de style : ça dit que la façade
calculée n'est pas la porte empruntée, et qu'une réduction qui l'ignore
raterait sa cible.

**Correction (2026-07-28) d'une mesure fausse de ce plan.** La version
précédente de ce paragraphe affirmait « `build_document_manifest` 18×,
`parse_alto_file` 5×, `rewrite_alto_file` 2× » depuis le sommet. C'est faux :
le comptage confondait `from saknussemm import X` avec
`from saknussemm.formats.loader import X`. La mesure refaite, sur les
instructions d'import du dépôt entier :

| forme | dépôt | backend |
|---|---|---|
| `from saknussemm import …` (sommet) | **64** | 7 |
| `from saknussemm.<module> import …` | **695** | 60 |

Et les 7 du backend ne touchent que des symboles **gardés** par la répartition
ci-dessous, plus `sanitize_error` (3 sites). La conclusion tient toujours, mais
pour une raison plus forte que celle écrite : **le namespace de sommet est une
vitrine que le dépôt lui-même n'emprunte pas.** Le coût réel de la
rétrogradation est de 32 lignes d'import, dont 20 dans les tests de la lib, 6
dans des scripts et exemples, et **6 en production** — toutes pour
`sanitize_error`.

### Répartition proposée — **95 → 54**

**Gardés (50) + ajoutés (4)**

| groupe | n | contenu |
|---|---|---|
| façade | 4 | `load`, `correct`, `correct_sync`, `__version__` |
| ce que la façade retourne | 25 | `CorrectionResult`, `CorrectionReport`, `DecisionSet`, les manifestes, les étages du rapport, la provenance… |
| porte avancée | 7 | `CorrectionPipeline`, `EditProducer`, `PipelineObserver`, `BaseProvider`… |
| policies injectables | 7 | `RetryPolicy`, `GuardConfig`, `ChunkPlannerConfig`, `PairingPolicy`, `LossPolicy`, `ConfidencePolicy`, `RoutingPolicy` |
| erreurs | 7 | la hiérarchie `SaknussemmError` |
| **ajoutés** | 4 | les 4 trous ci-dessus |

**Rétrogradés (45)** — retirés de `saknussemm.*`, **toujours importables depuis
leur module** (vérifié : les 45 ont un module d'accueil réel).

| groupe | n |
|---|---|
| protocole d'édition | 12 |
| formats bas niveau | 8 |
| contrat LLM | 8 |
| producteurs concrets | 6 |
| QE / routage | 6 |
| enveloppe vision | 4 |
| divers (`ChunkGranularity`) | 1 |

**Le point à trancher avant de couper** : rétrograder oblige les appelants à
changer leurs imports — mécanique, pas une refonte — mais c'est un changement à
faire **dans le même commit** que la coupe, sinon le dépôt se casse lui-même.

### Mesure du 2026-08-11 — **rétractée le 2026-08-12**

La répartition ci-dessus (95 → 54, « couper 41 ») a été confrontée à la
surface réelle en recalculant les clôtures. Elle ne tient plus, et pas d'un
peu : **la surface n'est pas 41 symboles trop grande, elle est 4 trop grande
et 9 trop petite.**

`saknussemm.__all__` vaut **66** aujourd'hui — `RM-04` avait déjà fait
l'essentiel de la coupe. Et :

| clôture | taille | état |
|---|---|---|
| ce que la façade **retourne** | 34 types | **tous exportés.** La moitié vérifiable de `V5` est donc **atteinte**, et désormais gardée par un test qui échoue au moment où un champ de retour porte un type non exportable |
| ce que la porte avancée **accepte** | 58 types | **9 ne sont pas exportés** |

- **4 exportés hors de toute clôture**, donc rétrogradables sur le critère de
  `S3` lui-même : `EDIT_PROTOCOL_VERSION`, `EditOp`, `ImageRef`, `PageImage`.
- **9 types que les signatures de la porte exigent et qu'on ne peut pas
  importer depuis le sommet** : `FormatAdapter`, `RewriteResult`,
  `RewriteMetrics`, `ConfidenceScorer`, `ConfidencePolicy`, `QEScorer`,
  `RoutingPolicy`, `TokenAlignment`, `AlignedPair`. Qui implémente un
  `EditProducer` ou passe `format_adapter=` doit aller les chercher par
  chemin de module.

**Et ça explique une observation que `S3` avait faite sans la relier** : le
backend, seul intégrateur réel, n'emprunte pas la façade mais la porte basse.
Il n'avait pas le choix — la porte qu'il utilise n'a jamais été complètement
exportée. « Le namespace de sommet est une vitrine que le dépôt n'emprunte
pas » a une seconde moitié : *la porte qu'il emprunte n'est pas une vitrine
du tout.*

#### Ce que `S3b` devient, et la question qu'il faut trancher

La question n'est plus « couper quoi » mais **« la porte avancée est-elle
publique ? »**, et aucune clôture ne peut y répondre :

- **si oui**, il faut la *fermer* — ajouter les 9 — et la surface monte avant
  de descendre. Le seul consommateur connu l'emprunte, donc la démoter le
  casserait ;
- **si non**, alors `CorrectionPipeline` non plus n'est pas publique, et la
  surface tombe à la clôture de la façade plus les erreurs, soit ~45.

**Recommandation, sur la mesure** : la porte est publique et doit être fermée.
Le coût de l'autre branche est de casser le seul intégrateur réel pour tenir
une formulation de `V5` qui ne parlait que de la façade.

**RÉTRACTÉ le 2026-08-12, avant exécution.** Le constat ci-dessus est faux,
et l'erreur mérite d'être gardée parce qu'elle est reproductible.

`S3b` **est déjà fait** — exécuté le 2026-08-01, et `RM-04` l'a affiné le
2026-08-06. Les 67 symboles actuels ne sont pas une accumulation : c'est la
clôture calculée, et `tests/test_public_api_snapshot.py` porte le raisonnement
complet, que la mesure d'hier n'avait pas lu.

Surtout, **les « 9 trous » ne sont pas des trous** : ils sont exactement ce que
`CorrectionPipeline` ajoute par ses **injections optionnelles** —
`format_adapter`, `qe_scorer`, `routing_policy`, `confidence_policy`,
`confidence_scorers`. C'est un **troisième seam**, laissé ouvert par écrit et
pour deux raisons :

- `RewriteResult`, `RewriteMetrics`, `AlignedPair`, `TokenAlignment`,
  `FormatAdapter` sont le vocabulaire de comptabilité interne du rewriter, que
  `R5`/`R8`/`L8` ont déplacé toute l'année. Le bénir sous SemVer promettrait
  une stabilité que rien ne soutient ;
- `ConfidencePolicy`, `RoutingPolicy`, `QEScorer`, `ConfidenceScorer` sont des
  boutons de recherche dont les défauts ne font rien. Un export au sommet se
  lit « prêt » ; ils ne le sont pas.

**L'erreur de méthode, qui est la leçon** : j'ai amorcé le calcul de clôture
avec `CorrectionPipeline`. Amorcer une surface publique avec les boutons
**optionnels** d'un constructeur mesure ce avec quoi la bibliothèque peut être
*configurée*, pas ce qu'elle *promet*. Les semences sont les deux promesses —
ce que la façade retourne, et ce que le seam producteur accepte. Recalculé
ainsi : **34 types et 17 types, tous exportés**. Les deux moitiés de `V5` sont
tenues.

Ce qui reste de la mesure, et qui vaut : `tests/test_public_surface_is_the_closure.py`
recalcule les deux clôtures à chaque run, exporte la garde que la liste
épinglée ne donnait pas (un champ de retour au type non exportable échoue au
moment où on l'ajoute), et **épingle le prix du troisième seam** — neuf noms,
comme coût d'une décision et non comme défaut.

**La décision n°5 est donc annulée** : voir « Décisions déléguées ».

### Décision (2026-07-28) — la coupe est différée, la vérité ne l'est pas

`S3` se scinde en deux, parce que ses deux moitiés n'ont ni le même coût ni le
même bon moment.

**`S3a` — dire ce qui est provisoire. Fait.** Ce qui coûtait quelque chose
aujourd'hui n'était pas la longueur de `__all__` : c'était que trois documents
la décrivaient faussement.

- `tests/test_public_api_snapshot.py` nommait la liste `PUBLIC_API_1_0` et la
  décrivait comme « the frozen 1.0 surface ». Elle n'a jamais été ratifiée ;
  elle a été **accumulée**. Le test contredisait donc ce plan, et aurait fait
  passer la coupe pour une régression. Renommée `CURRENT_TOP_LEVEL_SURFACE`,
  docstring réécrite.
- `SPECS_LIB_V2.md §8.1` déclarait `reconcile_hyphen_pair`, `check_line`,
  `plan_page` « déjà publics, maintenus ». Ils ne sont pas dans `__all__` — la
  spec normative promettait trois symboles absents pendant que `__all__` en
  exposait 95 dont la spec ne parlait pas. **Les deux se contredisaient dans
  les deux sens.** La promesse est retirée (et non honorée : le gel suspend
  l'extension de l'API publique, et `S3` réduit).
- `versioning.md` et `README.md` énoncent désormais le statut provisoire et la
  règle des **deux portes** — `saknussemm.*` sous SemVer strict *à partir de*
  `1.0.0`, chemins de modules supportés et documentés. Un symbole rétrogradé
  n'est pas supprimé, il est déplacé.

**`S3b` — couper. Différé jusqu'après `S2`.** Trois raisons, dans l'ordre de
poids :

1. `S2` scinde `core/pipeline.py` (3152 lignes) en composants nommés. Ça peut
   déplacer ce qui mérite d'être exposé. Couper avant, c'est migrer les imports
   **deux fois**.
2. Rien n'est gelé avant `1.0.0` : `docs/versioning.md` autorise explicitement
   `0.9.x` à casser. Le coût de l'attente est donc nul, à une condition — la
   liste ne doit pas regrandir.
3. Cette condition est **déjà tenue**, et c'est ce qui rend l'attente sûre :
   le test de cliquet interdit toute croissance de `__all__`, et le gel de
   fonctionnalités suspend de toute façon l'extension de l'API publique. Un
   ajout ne peut pas passer en silence — il faudrait toucher le snapshot et le
   `CHANGELOG`.

Ce qui reste dû par `S3b`, inchangé : la répartition 95 → 54 ci-dessus, les 4
trous de clôture ajoutés, les 32 lignes d'import migrées, le tout **en un
commit**. Décision restée ouverte pour ce moment-là : garder `sanitize_error`
au sommet (surface 55) parce que c'est un utilitaire de sécurité avec une vraie
dépendance en production — un outil de sécurité se rend facile à trouver.

**Ce que cette décision ne fait pas** : elle ne repousse pas `V5`. `1.0.0` reste
conditionnée à `S3b` fermé. Elle ordonne, elle n'annule pas.


| id | item | mesure actuelle | cible |
|---|---|---|---|
| S1 | Queue de l'ADR-010 : **unité de césure de première classe** — membres ordonnés, pages, type explicite/heuristique, autorité `SUBS_CONTENT`, signe physique, état, décision atomique, projection par format. Pointeurs dérivés, jamais mutables séparément. Retrait des résolveurs obsolètes | **0** doublon de résolveur (était 5) ; 8 lectures de pointeur dans `pipeline.py` (était 18) ; unité pas encore autoritaire | 1 primitive dirigée + 1 dérivation d'unité, 0 pointeur mutable |
| S2 | Scinder `core/pipeline.py` en composants nommés — préflight, planification, routage, exécution de chunk, validation, acceptation, réconciliation d'unités, projection, assemblage du rapport. Le pipeline public **orchestre**, il ne réimplémente pas | **3244 → 568** (−82 %), 19 modules nommés, 14 tranches (2026-08-01). Fichier principal **568 < 800** ; assemblage du rapport sorti du contrôle d'exécution ; boucle interne isolée dans `core/driver.py` (`PageDriver`). **Aucune fonction des modules que `S2` a produits ou déplacés ne dépasse 100 lignes** — les 4 qui restaient sont faites (`_reconcile_chunk_hyphens` 158→54, `_render_outputs` 140→83, `_route_and_filter_chunks` 110→61, `driver::_run_chunk` 104→78), et `rendering` est passé de 81 % à 97 % de couverture au passage (`tests/test_rendering_channels.py`, écrit avant le découpage). **Dette distincte, non close, épinglée** : 7 fonctions de `core/` dépassent encore 100 lignes et **préexistent toutes à `S2`** — `validator` 149, `pairing` 119, `editing` 114 et 103, `hyphenation` 110 et 101, `acceptance` 107. Deux d'entre elles (`link_hyphen_pairs`, `reconcile_hyphen_pair`) sont de la résolution de partenaire de césure : **ne pas y toucher sans finir `S1`**, règle en vigueur. Non croissantes par `tests/test_orchestrator_budget.py` | **atteinte** — reformulée le 2026-08-01 : la cible portait sur le périmètre de `S2`, pas sur les fonctions que `S2` n'a jamais touchées ; celles-là sont une dette nommée, pas une file d'attente |
| S3a | **Dire** que la surface est provisoire, là où trois documents disaient le contraire — snapshot renommé, `§8.1` corrigé (3 symboles promis et absents), règle des deux portes écrite, cliquet anti-croissance | **fait (2026-07-28)** | — |
| S3b | **Couper** : réduire la surface à la clôture transitive de ce que la façade retourne | **fait (2026-08-01) — 95 → 68**. La répartition 95 → 54 écrite ici **ne se reproduisait pas** : elle comptait la porte avancée pour ses 7 points d'entrée sans leur clôture, ce qui aurait laissé exactement les trous que `S3b` doit fermer (un appelant nommant `CorrectionPipeline` sans pouvoir nommer `ProducerOptions` ni `CorrectionRequest`). Recalculé : **deux clôtures** — ce que `load`/`correct`/`correct_sync` retournent (34 types, dont les 4 trous que le plan avait correctement identifiés) et ce que la couture producteur oblige à nommer, parce que la première phrase du README promet « any custom `EditProducer` ». **33 rétrogradés** vers leur module d'accueil (vérifié importable pour les 33), **6 ajoutés**. Laissé hors surface délibérément : la couture `FormatAdapter` (`RewriteResult`, `RewriteMetrics`, `AlignedPair`, `TokenAlignment`) — injection optionnelle, et vocabulaire interne du réécrivain que `R5`/`R8`/`L8` ont déplacé cette année ; le geler sous SemVer à `1.0` promettrait une stabilité que rien ne soutient | **68**, calculée et non choisie, close sur ses deux promesses, non croissante |
| S4 | Queue de l'ADR-011 : geler les types `Source*` (l'immuabilité repose sur une copie défensive, pas sur le type) | **partiel (2026-08-01)**. Mesuré plutôt qu'estimé — et l'item est nettement plus gros que « une demi-tranche » : **`Coords` et `DocumentManifest` sont gelés** (0 site d'écriture dans `src/`, 1 dans un test, corrigé en `model_copy`). Reste : `PageManifest`/`BlockManifest`, écrits une fois chacun par la désambiguïsation de `page_id` dans `core/pairing.py` — la même boucle réécrit des pointeurs de césure, donc c'est du territoire `S1` ; et **`LineManifest`, 246 sites d'affectation**, qui EST l'état de travail du run (`corrected_text`, `status`, les pointeurs). Le geler demande un type de travail distinct, pas une annotation. Le renommage `Source*` reste à trancher : les 4 types de manifeste sont dans la surface publique que `S3b` vient de figer à 68 | 5 types gelés, 0 mutation de manifeste hors d'un type de travail nommé |
| S5 | Écrire `docs/adr/012-*.md` : cité par le code, inexistant ; `docs/adr/README.md` s'arrête à 008 alors que 009-011 existent | **fait (2026-08-01)**. `012-loss-policy-and-per-line-attribution.md` écrit à partir du code et non de mémoire ; index complété (009-012) et entrée 004 corrigée (`institutional` → `proxy_protected`, renommé le 2026-07-28). Tenu par `tests/test_adr_references_resolve.py` : tout `ADR-NNN` cité par une source a un fichier, tout fichier est indexé, tout lien de l'index résout | — |

**`S3b` doit précéder toute publication `1.0`** : publier d'abord gèlerait 95
symboles sous SemVer. Il ne bloque en revanche pas `0.10.0`, que
`docs/versioning.md` autorise à casser. **`S2` doit précéder `S3b`.**
**`S1` doit précéder `L3`**, et porte `L2`.

---

## État de la porte `0.10.0` — relevé du 2026-08-11, revu le 2026-08-16

L'information existait, éparpillée sur six sections. Rassemblée ici, elle dit
quelque chose que personne n'avait formulé : **les cinq critères exigibles pour
`0.10.0` sont tenus, et ce qui reste est de la mécanique de publication.**

**Revue du 2026-08-16 — un sixième critère est tombé, et deux points de
mécanique ont changé.** `V7` (« un corpus externe versionné bloque un
merge ») n'était pas exigible pour `0.10.0` mais pour `1.0.0` ; il est
tenu depuis que `tests/external_corpus/pinned/` porte trois pages Gallica
réelles. `V9` se lit désormais autrement : les corpus de campagne ne sont
plus dans ce dépôt du tout, et ce qui reste — 1,89 Mo de pages épinglées —
est tenu hors de l'artefact par l'allowlist seule, vérifiée sur les
distributions **construites**.

| critère | exigé pour | état, et par quoi il est établi |
|---|---|---|
| `V1` — aucune altération non déclarée | `0.10.0` | **tenu.** `L0`-`L10` fermés. Restent deux résidus de `L5` que ce plan qualifie lui-même de « pas un correctif » : ils demandent de la géométrie et un corpus qui les contienne (`M7`), pas une édition de prédicat |
| `V2` — ni fantôme ni angle mort | `0.10.0` | **tenu.** `R0`-`R8` fermés (2026-07-28), deux d'entre eux par mesure plutôt que par code |
| `V3` — une seule définition de l'unité | `0.10.0` | **tenu** (déjà acté dans le tableau des critères) |
| `V8` — aucun renvoi vers l'histoire gelée | `0.10.0` | **tenu.** `D*` clos (2026-07-28) ; `RM-06` a fermé le versant `src/` (215 tags → 23, tous dans des fichiers que la vague s'interdit d'ouvrir) |
| `V9` — licences des corpus | `0.10.0` | **tenu.** `Gate 0` clos ; aucun corpus dans la wheel ni la sdist, épinglé par un test qui lit les artefacts **construits** |

Ce qui reste, et ce n'est pas de la correction :

1. **`P1` fin** — l'upload TestPyPI. Toute la chaîne a été rejouée en local le
   2026-08-01. **Précision du 2026-08-16, parce que la formulation était
   trop courte** : ni PyPI, ni TestPyPI, ni l'OIDC n'exigent de tag. C'est
   `publish-saknussemm.yml` qui l'exige, dans une étape écrite exprès pour
   qu'un `workflow_dispatch` distrait ne publie pas ce que `main` pointe.
   La contrainte est donc la nôtre. Elle n'est pas levée : on tague un
   `rc`, qui répète sans consommer le numéro `0.10.0` — ce qui ne se
   reprend pas est le numéro sur l'index, pas le tag.

   **Deux préalables que seul le mainteneur peut faire** : déclarer le
   *trusted publisher* sur pypi.org **et** test.pypi.org — sur le nom du
   FICHIER de workflow, qui a changé avec le renommage — et créer les
   environments GitHub `testpypi` / `pypi`. Sans eux, le premier dispatch
   échoue à l'échange OIDC.
2. **`P2`** — `0.9.0` → `0.10.0` dans `__version__` (le `pyproject` le lit),
   entrée `CHANGELOG.md`, tag `saknussemm-v0.10.0`, SBOM, publier l'artefact
   **testé**.
3. **Un garde-fou déjà tenu, à ne pas perdre** : « aucune revendication de
   qualité ne sort du dépôt sans `M2` + `M3` ». Vérifié le 2026-08-11 — les
   deux `README` ne portent **aucun chiffre**. Publier `0.10.0` sans
   revendication chiffrée est donc cohérent, et le rester est une contrainte
   sur la note de version.

### La décision qui n'est pas technique

Le gel dit : « aucune fonctionnalité nouvelle tant que `L*` et `R*` ne sont pas
fermés ». **Cette condition est atteinte.** Le lever ou non est un arbitrage,
pas un constat, et il commande une séquence :

- Tant que le gel tient, **`S3b` ne peut pas se faire** — c'est une réduction
  de la surface publique, donc autorisée en tant que refactorisation
  réductrice, mais elle a été explicitement différée après `S2`.
- Or `S3b` est une **rupture**. Elle doit donc passer pendant la série `0.x`,
  que `docs/versioning.md` autorise à casser. La faire après `1.0` la
  gèlerait sous SemVer — c'est la raison n°1 pour laquelle ce plan refuse de
  publier `1.0` en premier.

**Périmé le 2026-08-25 : le dilemme n'existe plus.** `S3b` a coupé le
2026-08-01 et `RM-04` a affiné la surface le 2026-08-06 — elle est à **67
symboles**, close et recalculée à chaque run par
`test_public_surface_is_the_closure`. Il n'y a donc plus de « couper avant ou
après » à arbitrer : c'est coupé.

### Et `1.0.0` reste loin, pour des raisons de fond

**Corrigé le 2026-08-25.** Ce paragraphe listait cinq critères restants et se
contredisait avec le tableau vingt lignes plus haut : il donnait `V5` pour à
faire alors que `S3b` a coupé le 2026-08-01, et `V7` pour non tenu en
affirmant que `tests/external_corpus/pinned/` est **vide** — il porte trois
pages Gallica depuis le 2026-08-16, dans la suite par défaut, sans marqueur
ni saut. Deux affirmations fausses dans un paragraphe de synthèse, pendant
que la table normative disait juste : exactement le motif que la vague `RS`
traitait ailleurs.

Il en restait **trois** le 2026-08-25 ; `V4` est tenu depuis le 2026-08-27,
il en reste **deux**, et ni l'un ni l'autre n'est de la dette :

- ~~**`V4`**~~ — **tenu le 2026-08-27.** `G1`-`G3` sont clos : l'état
  `review_required`, cinq règles de renvoi rendues sur six codes clos, et
  trois règles écrites comme non implémentables en l'état avec leur raison.
- **`V6`** (`M1`, `M2`, `M7`) — `M3` est fait depuis le 2026-08-21 (trois
  familles de modèles, le système ne varie pas, le modèle varie d'un facteur
  trois). Restent la campagne de variance post-correctif, le chemin
  inter-pages qu'**aucun** run ne mesure encore, et deux ventilations de
  métriques. Tout cela s'exécute sur `cinoc`, pas ici.
- **`V10`** (`P3`) — la revue humaine externe de l'API publique.

---

## RS — Réparation structurelle (audit du 2026-08-25)

Origine : `docs/audit/AUDIT-2026-08-25-complexite-accidentelle.md`, dix
constats mesurés sur le dépôt lu à `4b59394`. Comme `RM`, cette vague **ne
rouvre aucun** item `L`, `R`, `M`, `G` ou `V` et ne conteste aucune priorité.
Un seul constat est un défaut latent au sens strict (`RS-3`, le rejeu de la
carte rôle→slot) ; le reste est du coût d'évolution.

Les sept items tiennent dans les catégories que la règle de gel autorise —
correctifs, refactorisation **réductrice**, mesure, documentation de vérité,
tests. **`RS-5` est le seul qui demande un arbitrage explicite** : déplacer le
routage QE hors du chemin chaud est réducteur et sans changement de
comportement, mais il déplace une couture d'injection ; l'arbitrage est écrit
au § « Décisions déléguées — 2026-08-25 » avant tout commit de la phase.

`RS-3` est le prérequis que `S1` attend : tant que trois modules lisent les
champs pointeurs hors des primitives, `S1` traverse une base dont la garde ne
voit que deux sites sur cinq.

### La règle de vérification, commune aux sept

Un différentiel d'octets sur tout le corpus, producteur déterministe
(`RulesProducer`), avant et après chaque étape. **Sur `RS-3` à `RS-6`, tout
digest qui bouge est un échec de l'étape, jamais une raison de mettre le
golden à jour.** Les seules étapes autorisées à en modifier un sont celles
qui retirent du code réellement mort (`RS-2`), et elles doivent dire pourquoi.

### Carte

| ID | Titre | Nature | Gravité | Fichiers | Dépend de | Statut |
|---|---|---|---|---|---|---|
| `RS-1` | Le filet manque là où l'on va couper : `_build_hyphen_pairs` et `_cross_page_partners` ne sont nommés par aucun test, `core/driver.py` non plus, le golden byte-parity est un échantillon | tests | **critique** | `tests/` (6 fichiers, dont 4 nouveaux), `docs/la-vie-d-une-ligne.md` (nouveau) | — | **fait (2026-08-25)** — 1780 → 1871 tests |
| `RS-2` | Quatre affirmations fausses ; un shim de compatibilité que seuls les tests gardent ; 400 Ko de XSD hors surface publique ; 4 classes qui ne sont pas des politiques dans `policies.py` | vérité | important | `README.md`, `core/protocols.py`, `core/schemas/policies.py`, `formats/validation.py` | — | **fait (2026-08-25)** |
| `RS-3` | Le rejeu de la carte rôle→slot sur les champs pointeurs, à 60 lignes d'une docstring qui l'interdisait ; garde sur 2 sites de 5 | **bugfix** (latent) | **critique** | `core/reconcile.py`, `core/indexing.py`, `core/hyphenation.py` | `RS-1` | **fait (2026-08-25)** — 3 modules lecteurs → 0 |
| `RS-4` | Cliquets goodhartisés une seconde fois : le plafond d'arité a produit `PageWorkspace`, le plafond de longueur a produit neuf modules sous 130 l. | outillage | important | `tests/test_orchestrator_budget.py`, `core/workspace.py` | — | **fait (2026-08-25)** — chaque entrée porte sa raison ; 3 conservations écrites |
| `RS-5` | 5 des 14 paramètres du pipeline pilotent 1 667 lignes qu'aucun run par défaut n'emprunte ; cycle `formats.loader` ↔ `formats.alto.parser` ; frontière `integrations/` ↔ `producers/` incohérente | réducteur | important | `core/driver.py`, `core/routing.py`, `core/pipeline.py`, `formats/loader.py`, `producers/`, `integrations/` | `RS-1`, `RS-4`, arbitrage | **fait (2026-08-25)** — cible d'arité révisée, voir ci-dessus |
| `RS-6` | Ratio prose/code à 0,84, dont 121 passages de récit de migration ; 14 raisons de repli sans énumération ; 21 seuils non calibrés à geler en `1.0` | vérité | important | tout `src/`, `docs/versioning.md` | `RS-3`, `RS-5` | **fait (2026-08-25)** — 138 marqueurs → 62 ; vocabulaire de repli clos |
| `RS-7` | Rien ne prouve, en fin de vague, que la trajectoire a tenu | mesure | important | `docs/PLAN.md`, `docs/promises.md`, `CHANGELOG.md` | tous | **fait (2026-08-25)** sauf `V10`, qui demande un relecteur extérieur |

### Les six mesures de sortie

Reproduire en fin de vague celles du relevé d'entrée :

| mesure | entrée (2026-08-25) | cible |
|---|---|---|
| lignes de code effectif `src/` | 9 207 | ~9 000, jamais plus |
| ratio prose/code | 0,84 | **0,838, cible retirée** — voir ci-dessous |
| modules dans `core/` | 42 | ≤ 42 — aucun nouveau module en `RS-6` |
| paramètres de `CorrectionPipeline.__init__` | 14 | **14, cible révisée** — voir ci-dessous |
| modules lisant les pointeurs hors `pairing`/`units` | 3 | **0** |
| affirmations fausses recensées | 4 | 0 |

### Trois décisions de conservation, tranchées le 2026-08-25

L'audit relève trois abstractions comme candidates au retrait. Les trois sont
**gardées**, et la raison est écrite ici pour que la question ne se rouvre pas
au prochain relevé.

**`PageWorkspace` et `RunContext` restent.** Le premier est né d'une métrique
— `_descend_granularity` à douze arguments — et c'est un vrai constat. Le
retirer rendrait ces douze arguments à une fonction qui n'en a pas besoin,
pour un gain de principe. Ce qui est corrigé est le compteur, pas l'objet :
depuis `RS-4.2`, inscrire une fonction longue ou large demande d'écrire
pourquoi, ce qui retire l'incitation à fabriquer un objet pour faire baisser
un nombre. `tests/test_page_workspace_is_not_a_bag.py` continue d'interdire
qu'il grossisse.

**Les quatre représentations par ligne restent.** `LineManifest` (l'état de
travail), `LineTrace` (l'audit), `LineDecision` (la décision terminale) et
`LineOutcome` (la projection publique) ne fusionnent pas : la séparation
muable/immuable est une propriété acquise par `ADR-011`, et `LineOutcome` est
une surface publique versionnée. Le défaut réel n'était pas leur nombre mais
le recopiage non vérifié entre elles, que `RS-1.5` a fermé par un test de
clôture — quinze champs, neuf projetés, six écartés avec leur raison.

**Le jeton d'ordre de `core/finalize.py` reste.** Il garde exactement l'ordre
des passes que `S1` va traverser. Sa condition de retrait est que `S1` soit
passé ; `S1` n'est pas dans cette vague, donc la condition n'est pas remplie
et ne le sera pas ici. Si `S1` est reporté sine die, la question est close et
le jeton reste — un garde-fou dont on n'a plus besoin ne coûte que sa lecture.

### La cible « ≤ 9 paramètres » était fausse, et voici pourquoi

Elle reposait sur une hypothèse que `RS-5.1` a pu vérifier : que les cinq
paramètres du programme de recherche pouvaient sortir du constructeur comme
ils sortent du chemin chaud. Ils ne le peuvent pas au même prix.

Sortir le routage de `core/driver.py` est un DÉPLACEMENT : le pilote demande
son plan à `ChunkRouter` au lieu de porter le scoreur, le producteur
d'escalade et le plafond d'images. Rien de public n'est touché, et les tests
de routage passent sans une modification — c'est le critère qui distingue un
déplacement d'une réécriture, et il est tenu.

Retirer ces cinq paramètres du CONSTRUCTEUR est autre chose : ce sont des
coutures d'injection publiques, épinglées par `test_public_api_snapshot`.
Les regrouper derrière un objet unique changerait la signature, donc la
surface, donc passerait par le snapshot, le `CHANGELOG` et
`docs/versioning.md` dans le même commit — la porte que la décision n°1 du
2026-08-11 décrit pour une extension délibérée. C'est une décision de
conception, pas une étape de réparation, et la condition n°2 de l'arbitrage
du 2026-08-25 l'interdit explicitement à cette vague.

La cible est donc **retirée plutôt que manquée**. Ce qui la remplace est ce
que `RS-4.2` a déjà écrit à côté de l'entrée : l'arité de ce constructeur est
une surface de configuration, pas du drilling de paramètres, et les deux ne
se soignent pas de la même façon. Le vrai gain de `RS-5.1` se mesure ailleurs
— `core/driver.py` n'importe plus `core.quality` ni `core.batching`, et une
assertion le tient.

### La cible « ratio prose/code ≤ 0,45 » était fausse aussi

Deuxième cible retirée par la mesure, et pour un motif plus instructif que
la première : **le relevé d'entrée avait surestimé la prose supprimable d'un
ordre de grandeur.**

Il comptait 121 lignes portant un marqueur narratif (« used to »,
« historically », un tag de vague) et en déduisait, par une règle de trois
sur la taille des paragraphes, quelque deux mille lignes de récit de
migration. La règle de tri a été appliquée intégralement — invariant et
justification mesurée restent, récit de migration part — sur les trente-six
modules concernés. Résultat : **138 marqueurs ramenés à 62**, et le ratio
passe de 0,844 à 0,838.

La raison est dans la composition de ce qui reste, mesurée après coup :

| catégorie | lignes |
|---|---|
| docstrings de fonction | 2 665 |
| commentaires `#:` sur les modèles publics | 919 |
| docstrings de classe | 921 |
| docstrings de module | 1 062 |
| commentaires simples | 1 445 |

Les trois premières lignes du tableau — 4 505 lignes — **sont la référence
d'API** : ce qu'un champ de `CorrectionReport` signifie, ce que chaque
niveau de l'échelle de fidélité vaut, ce qu'une garde refuse. Atteindre 0,45
demanderait d'en supprimer une bonne part, c'est-à-dire de faire exactement
ce que la clause « quand s'arrêter » du plan interdit.

Ce qui reste vrai du constat : les paragraphes qui racontaient COMMENT le
code en est arrivé là étaient du bruit, et ils sont partis. Ce qui était faux
est la quantité — et l'avoir chiffré au jugé plutôt que mesuré est
précisément le défaut que le reste de ce dépôt évite avec soin.

### Ce que cette vague ne fait pas

- **`S1` n'y est pas.** `RS-3` le déverrouille ; il ne l'exécute pas.
- **`formats/alto/rewriter.py` reste hors-limites.** `RS-1` élargit le corpus
  byte-parity, ce qui lève la condition écrite au § `RM` — mais la levée est
  une décision de ce plan, pas un effet de bord de `RS-1`.
- **Aucun collapse des jumeaux de `GuardConfig`.** Les deux étages se règlent
  indépendamment, et la docstring dit pourquoi.

---

## RM — Remédiation structurelle (audit du 2026-08-06)

Origine : un audit statique externe du dépôt, lu à `26d6f53`. Il **ne rouvre
aucun** item `L`, `R`, `M` ou `G` et ne conteste aucune priorité. Il constate
autre chose : le prix de la discipline elle-même. Un seul de ses onze constats
est un défaut au sens strict (`RM-01`) ; les autres sont de la dette dont
l'effet est un coût d'évolution, et qui tombe sur `S1`.

Les onze items tiennent tous dans les catégories que la règle de gel autorise —
correctifs, refactorisation **réductrice**, mesure, documentation de vérité,
tests. Aucun n'en sort. `RM-08` est explicitement **transmis à `S1`** et ne
s'exécute pas dans cette vague.

### Carte

| ID | Titre | Nature | Gravité | Fichiers | Dépend de | Statut |
|---|---|---|---|---|---|---|
| `RM-11` | Contradictions documentaires : `CLAUDE.md` vs ce plan sur `S1` ; 2 docstrings fausses ; 1 clause dupliquée | vérité | secondaire | `CLAUDE.md`, `core/outcome.py`, `core/quality.py`, `tests/test_import_contract.py` | — | **fait (2026-08-06)** |
| `RM-02` | Ratchet goodhartisé : mesure la longueur, pas le couplage ; périmètre limité à `core/` | outillage | important | `tests/test_orchestrator_budget.py` | — | **fait (2026-08-06)** |
| `RM-10` | `_rebuild_line` (203 l.) et `rewrite_alto_file` (161 l.) hors de toute mesure | mesure | important | `formats/alto/rewriter.py` (lecture seule) | `RM-02` | **fait (2026-08-06)** |
| `RM-05a` | Aucun test ne protège l'ordre des passes de `core/finalize.py` | tests | important | `tests/decision/` (nouveau) | — | **fait (2026-08-06)** |
| `RM-01` | L'écriture de la décision terminale d'une ligne est dispersée sur 5 modules ; l'ordre des passes est porté par une docstring | **bugfix** | **critique** | `core/decide.py` (nouveau), `core/outcome.py`, `core/acceptance.py`, `core/reconcile.py`, `core/routing.py`, `core/finalize.py` | `RM-02`, `RM-05a` | **fait (2026-08-06)** |
| `RM-04` | ~20 % du code du paquet n'est exécuté par aucun chemin par défaut et est gelé par ce plan | nettoyage | important | `__init__.py`, `pyproject.toml`, `CHANGELOG.md` | `RM-11` + ratification | **fait (2026-08-06), périmètre corrigé** |
| `RM-07` | `core` connaît les formats : `core/losses.py` porte la table des attributs ALTO ; le contrat d'import plafonne à `== 3` au lieu de nommer une règle | réducteur | important | `core/losses.py`, `core/provenance.py`, `tests/test_import_contract.py` | — | **fait (2026-08-06)** |
| `RM-03` | Drilling de paramètres : 10 à 20 arguments sur le chemin chaud | réducteur | important | `core/workspace.py` (nouveau), `core/driver.py`, `core/outcome.py`, `core/reconcile.py`, `core/routing.py`, `core/pipeline.py`, `core/retry.py` | `RM-01`, `RM-02` | **fait (2026-08-06)** |
| `RM-06` | ~480 tags de vocabulaire privé, dont certains pointent vers `docs/history/` | vérité | secondaire | tout `src/` | `RM-11` | **fait (2026-08-10)**, 215 mesurés → 23 gelés |
| `RM-05b` | 124 fichiers de test organisés par vague de remédiation ; ~~277 imports de symboles privés~~ **64, mesurés** | tests | important | `tests/` | `RM-05a` | **fait (2026-08-11)** — 0 fichier-vague, 3 répertoires par invariant, 38 symboles internes nommés avec leur catégorie |
| `RM-09` | `core/schemas.py` fourre-tout : 1 538 l., 44 importateurs, 4 familles de types | nettoyage | secondaire | `core/schemas.py` → `core/schemas/` | — | **fait (2026-08-10)**, zéro importateur touché |
| `RM-08` | ~~Cinq projections voisines de l'unité de césure~~ — **constat périmé** : les deux ne sont plus des résolveurs parallèles mais deux filtres d'**une** dérivation, et ils divergent pour une raison écrite | réducteur | important | `core/reconcile.py` | ~~`S1`~~ | **clos par la mesure (2026-08-12)** |

### Ordre, et pourquoi

Quatre dépendances seulement, toutes réelles :

1. **`RM-11` d'abord.** `CLAUDE.md` affirmait cinq résolveurs de partenaire
   quand ce plan en mesure zéro. C'est le document qui gouverne le travail
   quotidien ; tant qu'il est faux, chaque session part d'une carte erronée.
2. **`RM-02` avant `RM-03`.** Le ratchet actuel récompense le découpage qui
   augmente le nombre de paramètres — c'est lui qui a produit
   `_descend_granularity` à 13 arguments. Réparer les signatures sans réparer
   d'abord la métrique garantit que le prochain découpage les reproduira.
   `RM-10` est le même geste, étendu à `formats/`.
3. **`RM-05a` avant `RM-01`.** Le défaut n'est pas détectable par la suite
   actuelle : elle vérifie l'état *final* d'un run, pas sa dépendance à l'ordre
   des passes. Le test doit exister **et échouer** avant qu'on touche au code.
   Sous-dépendance : la **table de précédence des raisons de fallback** est un
   livrable de mesure, écrit avant la centralisation — le code encode
   aujourd'hui une priorité « premier arrivé » par des `if not
   trace.fallback_reason` répartis sur cinq fichiers.
4. **Ratification avant `RM-04`.** Il retire des symboles de `__all__`, que
   `S3b` vient de figer à 68 par calcul de clôture. `docs/versioning.md`
   autorise la série `0.9.x` à casser, mais dépenser cette cartouche est un
   arbitrage de produit. **Tranché le 2026-08-06 : option A** — extra
   `saknussemm[research]`, les modules restent dans l'arbre et sortent de
   `__all__` et de la couverture obligatoire. L'option B (paquet
   `saknussemm-lab` séparé) est réservée au cas où la levée du gel dépasse
   `0.10.0`.

`RM-09` arrive tard bien qu'il soit le moins risqué : avec 44 importateurs il
produit le plus gros diff de la vague. Fait en dernier, avec un
`schemas/__init__.py` qui réexporte tout, il ne touche aucun importateur.

### Lots

- **Lot RM-0 — vérité** : `RM-11`. Fait.
- **Lot RM-1 — instrument** : `RM-02`, `RM-10`. Aucun fichier de `src/`.
- **Lot RM-2 — le défaut** : `RM-05a` → table de précédence → `RM-01`.
  Le seul correctif de la vague, et le seul lot à risque élevé.
- **Lot RM-3 — dégonfler** : `RM-04`, option A.
- **Lot RM-4 — frontière** : `RM-07`.
- **Lot RM-5 — signatures** : `RM-03`. Interdit tant que RM-1 n'est pas mergé
  et RM-2 pas fermé.
- **Lot RM-6 — nettoyages progressifs** : `RM-06`, `RM-05b`, `RM-09`.

### `RM-08` — **clos par la mesure, le 2026-08-12** (et non par une fusion)

Le constat d'origine — « cinq projections voisines, `_page_local_units` /
`_units_visible_on_page` quasi identiques » — décrivait un état **antérieur**.
Vérifié dans le code avant d'y toucher, comme la règle n°6 de
`docs/AUTOPILOT.md` l'exige désormais :

- les deux lisent **zéro champ pointeur** ;
- les deux passent par **la** dérivation partagée (`derive_hyphen_groups`,
  `ADR-010`).

Elles ne sont donc plus des résolveurs parallèles — c'est précisément ce que
`S1` a retiré. Ce qui reste est **une dérivation vue par deux filtres**, et la
différence n'est pas cosmétique :

- le **routeur** peut décliner. Escalader la moitié d'une unité la couperait
  entre deux producteurs, donc une unité incomplète est laissée au producteur
  primaire et ses membres restent ensemble *en ne faisant rien*.
  `_page_local_units` ne retourne donc rien pour une unité qui n'est pas
  entière ;
- le **batcher image-cap** ne le peut pas. Il découpe *un* chunk en plusieurs
  appels : « ne rien faire » n'existe pas, chaque ligne atterrit dans un
  batch. Sans réponse, il traitait chaque membre comme un singleton et pouvait
  mettre une paire dans deux appels — la seule chose que l'atomicité de paire
  interdit. `_units_visible_on_page` retourne donc les membres *présents*.

**Fusionner obligerait à choisir un comportement et changerait l'autre en
silence.** Ce n'est pas une opinion : `tests/hyphenation/test_the_unit_projections_are_not_duplicates.py`
exhibe un document où les deux divergent (une chaîne A-B ici, C sur la page
suivante : le routeur voit `{}`, le batcher voit `{A, B}`), et la sensibilité
a été vérifiée en simulant la fusion demandée — le test échoue.

Le test est aussi la façon honnête pour l'item de **rouvrir** : si un
changement futur les rend d'accord partout, elles sont redondantes et le test
le dit en échouant.

`S1` n'est donc plus un prérequis de `RM-08`, et `RM-08` ne sort pas de la
vague : il en sort par le haut, sans code modifié.

### Ce que la vague ne touche pas

`core/pairing.py`, `core/units.py`, `core/hyphenation.py` et la résolution de
partenaire de `core/reconcile.py` — territoire `S1`. `formats/alto/rewriter.py`
est **mesuré** (`RM-10`), jamais découpé : 203 lignes sur le chemin qui produit
le fichier livré, et le corpus de parité octet n'est pas encore assez large.
Les seuils de `GuardConfig` (non calibrés) et l'allowlist d'erreurs `ADR-008`
restent intacts.

### Suivi

Dernière mise à jour : 2026-08-10 — session 10. Lots `RM-0` à `RM-5` clos ;
`RM-6` clos sauf `RM-05b`, qui est **partiel et le restera par construction**
(regroupement fichier par fichier). Restent : `RM-05b` (suite) et `RM-08`,
qui n'est pas de cette vague.
Branche : `claude/rm-session-10-nettoyages-qb74pu`.

- **Done** — `RM-11` (session 1) : règle « pas de 6ᵉ chemin » de `CLAUDE.md`
  reformulée en propriété (deux encodages, pas un compte historique) ;
  docstring de `_fall_back_to_source` qui se disait « the single place »
  corrigée ; clause dupliquée de `RoutingPolicy` réparée et alignée sur
  `core/pipeline.py` ; en-tête de `tests/test_import_contract.py` qui situait
  `_adapter_for_format` dans `core/pipeline.py` corrigé vers
  `core/provenance.py`.
- **Done** — `RM-02` + `RM-10` (session 2) : `_PARAMETER_TARGET = 8` rejoint
  `_FUNCTION_TARGET`, avec la même sémantique de cliquet et 13 fonctions
  épinglées à leur arité mesurée (`_OVERPARAMETERISED`) ; le scan passe de
  `core/*.py` à `src/saknussemm/**/*.py`, et 6 fonctions de `formats/`
  rejoignent `_OVERSIZED` à leur taille mesurée. **Épingler n'est pas
  s'engager à couper** : `formats/alto/rewriter.py` reste hors d'atteinte.
  Sensibilité vérifiée dans les deux sens puis annulée (un 10ᵉ argument sur
  `PageDriver._run_chunk` → rouge ; une fonction longue et large ajoutée à
  `formats/page/_text.py` → rouge sur les deux gardes, cas que l'ancien scan
  ne voyait pas). Aucun fichier de `src/` modifié.
- **Done** — `RM-05a` (session 3) : `tests/decision/`, trois tests, aucun
  fichier de `src/` touché. Le test d'ordre **passe** et il est pire que
  prévu : permuter deux des trois passes ne renumérote pas un rapport, il
  change le **texte livré**. Deux lignes adjacentes proposant la même
  correction depuis des sources différentes sont un doublon, et l'ordre
  canonique les révoque toutes les deux ; la porte `token_realign` passée en
  premier révoque celle dont le compte de mots change, ce qui **efface la
  preuve du doublon**, et la seconde livre alors une correction que l'ordre
  canonique rejetait — en `corrected`, sans raison, sans entrée sidecar. Un
  échange, une hallucination livrée. Le `xfail` (strict) porte la propriété
  due : un ordre faux doit être **refusé**, pas produire d'autres octets ; il
  épingle l'exigence, pas le mécanisme. La caractérisation des raisons pose
  la règle réelle — ni premier ni dernier écrivain, **les deux** : 4 écritures
  assignent, 3 défèrent derrière `if not trace.fallback_reason`. Le cliquet
  d'exclusivité épingle 22 écritures / 7 fonctions / 5 modules, ne peut que
  descendre, et exempte `core/decide.py` avant son existence.
- **Done** — `RM-01` phase 1/3 (session 4) : la règle de précédence est une
  décision motivée, `docs/adr/013-fallback-reason-precedence.md`, et non plus
  un motif à re-déduire de trois `if`. Livrable en ADR plutôt qu'en constante
  dans un `core/decide.py` neuf : le dépôt tient déjà une discipline ADR
  testée, créer le module vide allumerait trop tôt l'exemption du cliquet
  d'exclusivité, une constante sans logique serait du poids mort dans un
  paquet que `RM-04` dégonfle, et `ADR-013` est citable depuis le code là où
  `RM-01` ne l'est pas. **Décision : garder le partage 4/3** — l'écrivain
  unique de `RM-01` diffère sur les sept chemins, ce qui est un changement de
  comportement sur les quatre sites assignants **invisible parce que `I-1`
  les rend inatteignables deux fois**. Couverture des 7 sites complétée (4 →
  7) ; le cas tranchant est réécrit avec la même assertion et la lecture
  inverse — il était épinglé comme défaut à corriger, il est épinglé comme
  correction à protéger.
- **Done** — `RM-01` phase 2/3, première moitié (session 5) : `core/decide.py`
  existe et **4 sites sur 7 y passent**, un commit par site — 22 → **15**
  écritures de décision hors du writer unique. Trois verbes plutôt qu'un,
  parce qu'il y a trois choses différentes à dire d'une ligne : `accept`
  (une correction tient), `fall_back` (une correction est retirée),
  `renormalise` (une décision déjà prise tient, seule son orthographe
  change).

  **Le seul changement de comportement de la migration a été mesuré avant
  d'être fait.** `_fall_back_to_source` assignait `fallback_reason` ;
  `decide.fall_back` diffère (`ADR-013`). Les deux règles ne divergent que
  sur une collision, donc la question était : une collision est-elle
  atteignable ? Instrumenté sur tous les corpus du dépôt, avec un producteur
  échouant ~20 % de ses appels pour forcer le chemin d'épuisement — **145
  fallbacks sur 190 lignes, zéro collision**. Ce que `I-1` prédisait, et ce
  que les corpus disent maintenant.

  Deux questions tranchées et écrites là où le code est.
  `routing._confirm_skipped_lines` → `accept` : un skip est une
  **acceptation**, pas un repli, et ce que `accept` **ne** touche pas
  (`model_input_text`) est ce qui garde la signature auditable du skip.
  `finalize._preserve_break_chars` → `renormalise`, ni `accept` ni dehors :
  la passe ne décide rien, elle réorthographie une décision prise, et
  `accept` estamperait `CORRECTED` sur des lignes dont elle n'a pas à fixer
  le statut.
- **Done** — `RM-01` **fermé** (session 6) : les 3 sites restants migrés, un
  commit par site. **22 → 0** écriture de décision hors `core/decide.py`, et
  **4 → 0** écriture non conditionnelle de `fallback_reason` dans tout
  `core/`. Les deux pièges annoncés se sont levés par **preuve**, pas par
  exception : les 5 branches de rejet de `check_line` retournent
  `source_ocr` avec une raison non nulle (donc `fall_back` y écrit
  exactement le texte que le site écrivait), et `classify_reconcile_outcome`
  ne retourne `"fallback"` **que si** `final_p1 == ocr_1 and final_p2 ==
  ocr_2` — la classification est *définie* par cette égalité. Aucune
  exception écrite n'a été nécessaire. Les deux garanties sont épinglées
  (`test_acceptance_translation.py`, `test_reconcile_translation.py`) parce
  qu'elles sont invisibles au site d'appel. `hyphen_subs_content` reste dans
  `_reconcile_one_pair` : ce n'est pas un champ de décision, c'est de l'état
  de césure, et le déplacer mettrait du territoire `S1` dans `RM-01`.
- **Done** — le **garde d'ordre** (session 6) : `_FinalizeOrder`, jeton de
  séquencement **par run**, créé dans `_finalize_document`, jamais partagé.
  Écarté : un drapeau d'état sur le manifeste (remettrait de l'état de run
  sur un objet partagé, ce qu'`ADR-011` a retiré) et « un point d'entrée
  unique » (`_finalize_document` l'est déjà et ne refuse rien — les passes
  restent importables). `RuntimeError` et non `SaknussemmError` : un ordre
  faux est un bug moteur, et `SaknussemmError` est la famille que la boucle
  de chunk absorbe (`ADR-008`). Le jeton est **optionnel** — `None` =
  non vérifié — parce que c'est la seule façon pour le test de
  démonstration de tourner l'ordre faux ; l'échappatoire est fermée de
  l'autre côté par un test statique qui lit `_finalize_document` et échoue
  si une passe y est appelée sans jeton. **Le `xfail` strict est levé ; il
  ne reste aucun `xfail` dans la suite.**
- **Done** — `RM-04` (session 7), **et son périmètre était surestimé de
  moitié** : la mesure a précédé le déplacement, et elle a coupé l'item en
  deux. `integrations/qe.py` et `integrations/vision.py` — **818 des 1600
  lignes** — étaient **déjà** derrière `saknussemm[qe]` / `saknussemm[vision]`
  et **déjà** hors de la barre de couverture, avant la vague. Le mécanisme
  d'option A était en place ; ce qui manquait, c'était **ce qui tient la
  frontière**. Une entrée `pyproject.toml` et un `omit` de couverture
  n'empêchent aucun module du chemin d'installation de base d'en importer un,
  et un seul import transforme une dépendance optionnelle en dépendance
  obligatoire au runtime — la panne tombant sur qui a installé exactement ce
  que les métadonnées annonçaient. Le test de frontière est écrit et vérifié
  en sous-processus (import du paquet **et** run par défaut complet, parce
  qu'un scan statique ne voit pas un import paresseux sur le chemin chaud).
- **Périmètre retiré de `RM-04`, mesuré** : `core/routing.py`,
  `core/quality.py`, `core/confidence.py`, `core/batching.py` **ne peuvent
  pas** sortir de la couverture. Sur un run par défaut avec producteur
  factice : batching **27 %**, confidence **21 %**, quality **49 %**, routing
  **22 %**. Ils sont importés par `core/driver.py` et `core/pipeline.py`, et
  leurs chemins no-op s'exécutent à chaque run. Les omettre ne mettrait pas
  du code de recherche derrière une porte, cela **cesserait de mesurer du
  code qui part dans la wheel**. Le « 20 % non exercé » de l'audit était un
  compte d'**énoncés** juste ; ce n'était pas un compte de **modules
  séparables**, et `RM-04` ne peut déplacer que les seconds. Réduire ces
  quatre-là demande de retirer les 5 boutons correspondants du constructeur
  — rupture bien plus large, à instruire séparément, pas à glisser ici.
- **Done** — `RM-07` (session 8) : `core` n'énumère plus les formats. Le
  partage de `core/losses.py` a été **mesuré, pas jugé** — le réécriveur PAGE
  n'importait que `COUNTS_INVALIDATION` et `INVALIDATION_COUNTER` et n'a
  jamais eu besoin de la table ; ALTO en importait cinq, dont trois que seule
  la table peut répondre. La moitié partagée est donc ce que les deux formats
  lisent et qu'aucun ne possède ; tout ce que la table répond part avec elle
  dans `formats/alto/losses.py`. **Aucune valeur n'a changé** :
  `test_loss_accounting_is_real.py` est le différentiel qui compare le
  réécriveur à la table sur les trois chemins d'écriture, vert à la nouvelle
  adresse, plus la parité octet et la parité de rapport PAGE.
  `_adapter_for_format` rejoint `formats/loader.py`, à côté de la dispatch de
  parseurs qui répond à la même question. `core/rendering.py` atteint toujours
  un format — le moteur doit bien en toucher un pour écrire — mais **ne sait
  plus lesquels existent** : il demande au loader. Le seam est resté,
  l'énumération a bougé. Bilan : **3 imports interdits dans `core` → 1**.
- **Done** — le contrat d'import énonce une **règle** au lieu d'un compte
  (session 8). `assert len(violations) == 3` était un plafond : il disait
  combien d'effraction était tolérée sans dire par qui, donc une nouvelle
  violation n'importe où dans `core` restait légale tant qu'une ancienne
  disparaissait dans le même commit. C'est désormais une carte nommée
  (`_render_outputs`, `for_provider`), qui échoue dans les deux sens — une
  fonction non nommée qui atteint un format, et une fonction nommée qui a
  cessé de le faire. Une seconde règle interdit l'import de niveau module.
- **Décision tranchée** — la boucle `from saknussemm import __version__`
  (`core/rendering.py`, `core/provenance.py`) **reste ouverte**, et sur le
  fond : elle porte **un** symbole, une chaîne de niveau module ; un import
  paresseux ne peut ni interbloquer ni rendre un objet à moitié initialisé.
  La fermer veut dire déplacer `__version__` dans son module, donc éditer
  `[tool.hatch.version] path` (la source de version de la wheel) **et** le job
  CI qui grep `__init__.py` — la chaîne de publication, pour zéro gain de
  comportement, dans un item dont le sujet est « le cœur ignore les
  **formats** ». Mais elle est désormais **bornée** plutôt que simplement
  connue : les deux fichiers sont épinglés par nom et l'ensemble des symboles
  portés est épinglé à `{"__version__"}` — un troisième site ou un second
  symbole est une décision différente, pas la même.
- **Done** — `RM-03` (session 9), trois gestes. **`PageWorkspace`** : les
  trois index qui voyageaient ensemble (`line_by_id` 24 occurrences,
  `cross_page_partners` 38, `traces` 35) sont liés une fois par page. Le
  périmètre a été **mesuré avant d'être choisi** — les 9 fonctions portant
  les trois sont *exactement* le chemin de chunk, ce qui fait de la
  frontière un constat et non une préférence. Gelé, sans méthode, et la
  limite de cette affirmation est écrite : les dicts à l'intérieur sont
  l'état vivant du run, `traces` est écrit par `decide.py`, et les
  regrouper ne les rend pas immuables — ce que ça rend impossible, c'est de
  les **séparer**. Le piège nommé (en refaire le fourre-tout qu'`ADR-011` a
  retiré) est fermé par un test et non par une résolution :
  `test_page_workspace_is_not_a_bag.py` échoue sur un 4ᵉ champ, sur le
  dégel, et sur **toute** méthode — cette dernière règle étant la subtile,
  une méthode qui muterait serait un second écrivain de décision déguisé en
  objet, invisible au cliquet d'exclusivité qui scanne l'affectation
  d'attribut et non l'intention.
- **Done** — `for_provider` **19 → 9** paramètres nommés. La recopie
  manuelle de 13 arguments n'était pas seulement longue : c'était une
  **seconde déclaration** de la signature d'`__init__`, que rien ne
  contraignait à concorder — un bouton ajouté au constructeur et oublié ici
  était silencieusement inatteignable par la porte que le README met devant
  tout usager LLM. `observer` reste **nommé** à contre-courant, et c'est le
  snapshot d'API publique qui l'a attrapé : transférer un argument *requis*
  déplace l'erreur du site d'appel vers le constructeur. Le pin a résisté
  pour une vraie raison, ce qui est ce à quoi sert un pin.
- **Done** — `budget: list[int]` → `ChunkBudget`. Une cellule mutable
  déguisée en liste, correcte (une descente dépense la **même** bourse) et
  coûtant deux questions au lecteur à chacun de ses 8 sites. Délibérément
  **non gelé**, à l'inverse de `PageWorkspace` un commit plus tôt, et le
  contraste est le propos : un workspace se lit, un budget se dépense.
- **Done** — `RM-06` (session 10), et l'ordre du geste est le résultat. Le
  **test d'abord** : `test_adr_references_resolve.py` devient
  `test_references_resolve.py` et couvre les deux vocabulaires qu'un
  commentaire peut citer sans mentir — `ADR-NNN` (la généalogie) et `§n`
  (le contrat). Deux `§` ne résolvaient pas et **ressemblaient** à des
  renvois au SPEC : `ARCHITECTURE.md §3.2` (histoire gelée) et « prior
  audit §7.1 » (un audit que personne ne peut nommer). Le reste — `Fnn`,
  `P3.n`, `Sn`/`Ln`/`Rn`, tranche nue, `Audit-…` — est interdit par un
  **cliquet à base mesurée** : 215 tags dans 48 fichiers, chaque fichier
  libre de décroître et jamais de croître, un fichier à zéro devant quitter
  la carte. Sensibilité vérifiée puis annulée dans les deux sens. Le
  nettoyage devient alors mécanique et vert fichier par fichier : **215 →
  23**, les 23 restants étant *exactement* les trois fichiers que la vague
  s'interdit d'ouvrir (`core/pairing.py`, `core/hyphenation.py`,
  `formats/alto/rewriter.py`).
- **Done** — et c'est la moitié du travail : **on trie, on ne rase pas.**
  Sept commentaires portaient la revendication dans le tag et sont
  réécrits, pas dépouillés — « the whole of R1 » devient « the whole of the
  false half above » (la fausseté que le docstring mesure trois paragraphes
  plus haut), « exactly the shape of R1 » devient « exactly the
  double-count this table exists to prevent », « `F8` pins both pair
  members » devient le composant qui le fait vraiment (le planner), et
  « moving it would put `S1` territory inside `RM-01` » devient ce que ça
  signifie pour qui lit la ligne. Deux `slice E` nus **gagnent** leur ancre
  (`ADR-011 slice E`) au lieu de la perdre : un `ADR` documente ses
  tranches, donc celui-là résout. La connaissance de domaine signalée
  n'était dans aucun tag et est intacte : le cas BnF `TL000454`,
  l'inatteignabilité d'`EXACT` en ALTO, la distinction
  STRUCTURAL/SEMANTIC.
- **Done** — les docstrings brouillées de `core/schemas.py` relevées en
  session 3, **et une troisième que personne n'avait vue** : le `ValueError`
  qu'un hôte lit en demandant `write_wc` disait « the calibration harness
  (the vision/QE programme/3) », où le `/3` est la queue de « (ROADMAP V3
  Phase 2/3) ». Cause identifiée : `e7b465c` a substitué « Phase 2's job »
  → « the job of a calibration against a real corpus » à l'aveugle, et là
  où la phrase contenait déjà le membre, elle s'est mangée elle-même. Deux
  descendantes de la même substitution dans `core/confidence.py` sont
  **laissées** : elles se lisent correctement.
- **Done** — `RM-09` (session 10). `core/schemas.py` (1 538 l.) devient
  `core/schemas/` en quatre familles strictement stratifiées —
  `manifest` ← `policies`/`producer` ← `report`, sans cycle. Le shim
  n'était pas une commodité : `__all__` est **identique à l'octet** (39
  noms, diffé), et les onze noms publics-de-fait qui n'y figuraient pas
  (`ImageAsset`, `ModelCapabilities`, `HyphenSplit`, les cinq `DEFAULT_*`,
  `CORRECTION_REPORT_VERSION`) sont réexportés en forme `X as X`. Ce
  détail est le seul piège de l'item : sous `--strict`,
  `no_implicit_reexport` aurait cassé leurs consommateurs au typage tout
  en passant à l'exécution. **Vérifié plutôt que supposé** : `git status`
  ne montre que le module supprimé et le paquet ajouté — zéro importateur
  touché, dans la lib comme dans le backend ; 1 376 tests lib, 472 backend,
  `mypy --strict` sur 74 fichiers, et le snapshot OpenAPI inchangé.
  `SPECS_LIB_V2` §3 nomme l'arbre, donc il nomme le paquet.
- **Done** — `RM-05b`, **première tranche** (session 10) : `tests/hyphenation/`.
  Dix-neuf items de test portant sur un seul objet — un mot coupé sur deux
  lignes physiques — vivaient dans trois fichiers nommés d'après la vague
  qui les avait trouvés. Ils sont regroupés par la question posée
  (`test_pair_vetting` 3, `test_pair_reconciliation` 7,
  `test_unit_atomicity` 7, `test_fusion_detection` 2). **Un déplacement et
  rien d'autre, contrôlé et non affirmé** : `pytest --collect-only` donne
  les *mêmes* 1 383 items avant et après, et le diff des deux listes est
  exactement 19 lignes retirées sous les anciens noms et 19 ajoutées sous
  les nouveaux (P5). La seule ligne éditée est dans un *helper*
  (`_reconciled_chain` appelle `_hyphen_line`, parce que le fichier importe
  aussi le `_line(i, text)` de la suite planner). Le `_line` qui existait
  en double au caractère près devient `tests/hyphenation/_lines.py`.
- **Done** — `RM-05b`, **deuxième tranche** (session 10) : le filet de `S1`
  devient *un* répertoire. Les 19 fichiers dont le sujet entier est l'unité
  de césure (4 828 l., ~200 cas, de `test_pairing_core` à `test_units`)
  rejoignent `tests/hyphenation/` en `git mv` pur — git les enregistre tous
  les 19 comme renommages à zéro ligne modifiée, et le seul fichier édité
  est `test_decisions.py`, dont l'import suit le module qu'il lit. Preuve
  que c'est un déplacement : la liste triée des IDs collectés, privée de son
  préfixe de répertoire, est identique à l'octet — 1 383 items.
- **Done** — **le prérequis mesuré du déplacement, et il n'était pas
  cosmétique** : sept sites dans six fichiers atteignaient `examples/` en
  comptant quatre `.parent` depuis `__file__`. Descendus d'un répertoire,
  les sept résolvaient vers un chemin inexistant — **silencieusement**, six
  d'entre eux étant gardés par `skipif(not PATH.exists())` : ils auraient
  simplement cessé de s'exécuter. `tests/_pipeline_harness.EXAMPLES`
  existait déjà et reste à la racine de `tests/`.
- **Done** — `RM-05b`, **troisième tranche** (session 10) : `tests/identity/`,
  pour la règle sur laquelle toute la bibliothèque est indexée — l'identité
  d'une ligne est `(page_id, line_id)`. `test_duplicate_ids.py` (`ADR-007`)
  et `test_line_ref.py` (`ADR-009`) y entrent en `git mv` ; cinq cas les
  rejoignent depuis deux fichiers-vague. Le cas difficile est **l'acceptation**
  et non les refus : un id de bloc répété sur chaque page d'un export OCR
  page-par-page est *légitime*, l'identité étant page-qualifiée. La frontière
  est écrite : l'ordre de lecture et la traversée récursive
  (`test_structure_traversal`) portent sur les éléments que le parseur
  *visite*, pas sur ce qui les nomme — ils partagent des fixtures avec ce
  répertoire, pas un invariant. Pas de garde de complétude ici, et pour une
  raison mesurée : `line_ref` est la façon dont *tout* indexe une ligne, donc
  « importe `core.identity` » nommerait la moitié de la suite au lieu de la
  borner.
- **Done** — **et le déplacement a révélé une classe entière que la tranche
  précédente avait mal bornée.** `test_line_ref.py` déplacé résolvait
  `examples/sample.xml` un répertoire trop haut et a échoué. Échouer était la
  moitié chanceuse : un grep a trouvé **35 modules de plus** faisant la même
  arithmétique, et la plupart des tests adossés au corpus sont derrière
  `skipif(not PATH.exists())` — déplacés, ils résolvent vers rien, *skippent*,
  et annoncent un succès. Une suite qui cesse silencieusement de s'exécuter
  ressemble exactement à une suite qui passe. `tests/_paths.py` calcule
  `REPO`/`PKG`/`SRC`/`TESTS`/`EXAMPLES` une fois, depuis le seul module qui ne
  bougera jamais ; 59 modules les importent.
  `test_paths_are_not_counted_in_parents.py` interdit le retour du motif — et
  a échoué deux fois à son propre premier run : son docstring citait la
  chaîne interdite mot pour mot, et sa première prise a été **la garde
  précédente**, `test_the_net_is_bounded.py`, qui calculait `TESTS` de la
  façon interdite.
- **Done** — `RM-05b` **clos** (session 10), et son second constat était
  **faux**. « 277 imports de symboles privés » : mesuré, c'est **64 imports,
  38 symboles, 32 fichiers** (en élargissant aux imports privés entre modules
  de test et aux accès d'attribut : 175 — 277 n'est reconstituable par aucune
  définition essayée). Surtout, le compte n'était pas le sujet. Classés, les
  38 forment quatre familles et **aucune n'est du gaspillage à réduire** :
  **`surface` (2)** — `__version__` et `_LAZY` sont les *instruments* du test
  de surface publique, pas des internes ; **`alias` (3 symboles, 12 imports)**
  — `_detect_namespace` **est** `formats._xml.detect_namespace`, un nom
  **public** porté sous alias privé et listé dans le `__all__` des deux
  paquets de format, soit près d'un cinquième des imports « privés » comptés
  par l'audit ; **`value` (~23)** — fonctions de leurs arguments, où passer
  par la façade affirmerait *moins* et non autrement ; **`run-state` (~10)**
  — les passes qui écrivent l'état du run, porteuses **par construction**, et
  le plan le dit déjà : la suite publique vérifie l'état *final*, pas la
  dépendance à l'ordre des passes (`RM-05a`).
- **Done** — le livrable est donc un **cliquet nommé, pas une réduction** :
  `tests/test_internal_seams_are_named.py`, où un 39ᵉ import privé est une
  décision que quelqu'un prend exprès. Et la classification est **vérifiée,
  pas déclarée** : une entrée `run-state` doit porter `traces`, `workspace`
  ou `order` dans sa signature réelle lue dans `src/`, une `value` n'en porte
  aucune, une `alias` doit résoudre vers un nom public. Ce dernier contrôle a
  échoué au premier run et avait raison : `formats/alto/parser.py` réimporte
  le nom *déjà* privé, donc la chaîne de réexport a deux maillons et
  n'interroger que le dernier faisait passer le second pour un interne.

- **Done** — `RM-05b`, **cinquième tranche** (session 10) :
  `test_text_integrity_cluster.py` dissous à son tour. **Il ne reste dans la
  suite aucun fichier nommé d'après le moment où un défaut a été trouvé
  plutôt que d'après ce qu'il garantit** — le constat qui ouvrait `RM-05b`
  est clos sur son versant « fichiers-vague ». Ses 21 cas ont rejoint sept
  destinations, dont quatre fichiers neufs nommés par l'invariant :
  `identity/test_ops_are_attributable.py` (une édition reste attachée à la
  ligne pour laquelle elle a été calculée — `line_id` seul se répète entre
  fichiers), `hyphenation/test_subs_marker_convergence.py` (ce que le
  rewriter *demande* d'un marqueur et ce qu'il *écrit* concordent : le défaut
  n'était pas un fichier faux mais une **route** fausse, une ligne
  octet-correcte reclassée « à réécrire » à chaque run),
  `test_line_separators_are_refused.py` (une ligne corrigée est UNE ligne,
  aux deux portes — `str.splitlines` coupe sur huit caractères, une porte qui
  en refuse deux en laisse passer six) et `test_page_custom_groups.py`.
  Mêmes 1 389 noms collectés (P5).
- **Done** — et le corollaire, appliqué : **supprimer un fichier est la façon
  la plus rapide de créer une référence morte.** Quatre commentaires
  pointaient vers les fichiers supprimés ; ils sont réparés dans le même
  commit. C'est exactement le défaut que `RM-06` vient de retirer de `src/`,
  et il se recrée à chaque déplacement si personne ne regarde.
- **Done** — `RM-05b`, **quatrième tranche** (session 10) : deux fichiers-vague
  **dissous, pas renommés**. Renommer un sac de constats sans rapport ne fait
  que lui donner un meilleur nom ; chaque cas restant de
  `test_audit_d_lib_fixes.py` et `test_review_fixes.py` a rejoint l'invariant
  dont il parle, et six cas de `test_text_integrity_cluster.py` ont suivi ceux
  qui partageaient une destination — pour qu'aucun invariant ne finisse coupé
  en deux. Un fichier neuf, `test_adjacent_duplicates.py` : une seule garde
  (`check_adjacent_duplicates`), quatre endroits où elle peut être mise en
  défaut (dans un chunk, à une frontière de chunk, à une couture de page, à
  une descente de granularité), jusqu'ici répartis sur trois fichiers. Mêmes
  1 389 noms de test collectés avant et après (P5).
- **Done** — et un refus délibéré, noté parce qu'il aurait été tentant : les
  quatre cas de traversée déplacés construisent leurs documents avec des
  constructeurs *plus permissifs* (un corps de `Page` sans `PrintSpace`, un
  `TextBlock` dont l'id peut être vide ou absent) que les homonymes de
  `test_structure_traversal`. Ils sont importés sous alias
  (`_alto_page_doc`, `_tb_optional_id`) **et non fusionnés** : les deux
  émettent un XML différent, et les unifier changerait en silence ce que les
  tests plus anciens affirment. C'est une mesure à faire exprès, pas un effet
  de bord de déplacement.
- **Done** — le regroupement est **tenu par un test**, parce que rassembler
  ne tient pas tout seul : `test_the_net_is_bounded.py` exige que tout
  module de test important `saknussemm.core.pairing`, `.units` ou
  `.hyphenation` vive dans ce répertoire, à cinq exceptions **nommées avec
  leur raison**. Deux gardes sur la garde : une entrée d'allowlist qui
  n'atteint plus le code doit *partir*, et le scan doit continuer à voir au
  moins dix modules à l'intérieur — sans quoi un motif dérivé passerait au
  vert en ne prouvant rien. La première a sauté **dès le premier run,
  contre son propre auteur** : `test_parser.py` avait été listé sur la foi
  d'un grep alors qu'il ne cite `core.pairing.HYPHEN_CHARS` que dans un
  docstring. Nommer un module en prose n'est pas une façon de casser quand
  il change ; le motif porte donc sur le chemin d'import.
- **Blocked** — aucun.
- **Remaining** — `RM-05b` (suite) ; `RM-08`, hors vague.
- **New bugs discovered** — un, trouvé en étendant le ratchet et corrigé dans
  le même geste (l'instrument était en cause, pas `src/`) : la clé était le
  nom nu de la fonction, donc un fichier déclarant deux fois le même nom
  n'en mesurait qu'un. `core/confidence.py::score_line` et
  `core/quality.py::needs_correction` existent chacun en double (protocole,
  puis implémentation) et une moitié de chaque paire échappait au test. Clés
  désormais qualifiées, et les quatre définitions sont épinglées.
- **New bugs discovered** — deux phrases brouillées de plus dans `core/
  schemas.py`, **non corrigées** (P6 : hors périmètre d'une session
  tests-only, et `src/` ne devait pas bouger) : `LossPolicy.
  min_alignment_score` dit « Calibration against a real corpus is the job of
  a calibration against a real corpus » ; `ConfidencePolicy` dit « locked
  until the calibration against a real corpus harness proves the values
  against a real corpus ». Même famille que la clause dupliquée de
  `RoutingPolicy` fermée par `RM-11` — un mot a manifestement été substitué
  en masse dans les docstrings à un moment. À ramasser avec `RM-06`.
- **~~New bugs discovered~~ — RETIRÉ (session 4, vérifié faux).** La session 3
  annonçait que l'attribution d'une révocation pouvait être fausse et que
  `CorrectionResult.fallback_reasons` comptait faux d'autant de lignes
  signalées deux fois. **C'est inexact.** Le constat de code était juste
  (`_apply_unit_reverts` écrit texte et statut sans condition, la raison
  seulement dans une trace vide) ; l'inférence ne l'était pas. Elle supposait
  qu'une ligne puisse porter une raison **tout en tenant encore une
  correction**, ce qui n'arrive pas :

  > **I-1 — une ligne porteuse d'un `fallback_reason` est déjà revenue à sa
  > source : son texte final égale son texte OCR.**

  Mesuré, pas supposé : producteur adverse sur `X0000002`, `sample`, les
  quatre fixtures PAGE et `corpus_gt`, sous trois politiques de perte — **756
  lignes décidées, les 8 familles de raisons, zéro ligne** porteuse d'une
  raison en tenant une correction. Une seconde révocation est donc
  **idempotente** sur le texte ; la passe qui a réellement retiré la
  correction est la première, et différer est ce qui garde la raison
  **vraie**. Le dernier-écrivain-gagne nommerait une passe qui n'a rien fait.
  Tranché et écrit en `ADR-013` ; `I-1` est désormais un test.
- **New bugs discovered** — aucun en session 4.
- **New bugs discovered** — session 8, **non corrigé** (P6) :
  `LOSS_MATRIX_VERSION` n'est **lu par personne**. Son commentaire dit « les
  consommateurs du rapport y accrochent leurs attentes, pas à la version de
  la bibliothèque » — or il n'apparaît dans aucun champ de
  `CorrectionReport`, dans aucun test, dans aucun script. C'est un contrat
  versionné qui n'est émis nulle part : soit il rejoint le rapport, soit le
  commentaire cesse de promettre. À trancher avec `R*`, pas ici.
- **New bugs discovered** — aucun en session 9 ; aucun en session 7 ni 6.
- **New bugs discovered** — session 5, **non corrigé** (P6, hors périmètre) :
  `LineTrace.projected_text` peut être périmé pour un consommateur.
  `_finalize_chunk_traces` le fixe au `corrected_text` du moment, puis
  `_preserve_break_chars` réécrit `corrected_text` sans le rafraîchir. Le
  champ est écrit à 6 endroits et **lu nulle part dans `src/`** — c'est de
  l'information pure pour l'hôte, et `LineTrace` est dans la surface
  publique. Sans effet sur le texte livré ni sur les décisions, donc hors
  `L*`. `decide.renormalise` a délibérément gardé le comportement
  historique (aucune écriture de trace) plutôt que de corriger au passage.
- **Tests added** — session 2, `tests/test_orchestrator_budget.py` : `RM-02`
  ajoute `test_no_unnamed_function_exceeds_the_parameter_target`,
  `test_known_overparameterised_functions_only_shrink`,
  `test_finished_signatures_are_not_still_listed` ; `RM-10` ajoute
  `test_the_scan_sees_the_whole_package` ; le trou de clés ajoute
  `test_keys_are_unique_per_definition`. 11 → 34 cas dans le module.
- **Tests added** — session 3, `tests/decision/` (5 fichiers, 19 cas dont 1
  `xfail` strict et 1 `skip` conditionné à l'existence de `core/decide.py`) :
  `test_finalize_pass_order.py` (l'ordre change le texte livré ; un ordre
  faux n'est pas refusé), `test_fallback_reason_precedence.py`
  (caractérisation des 7 écritures de raison + épinglage statique du partage
  4/3), `test_decision_write_exclusivity.py` (cliquet des 22 écritures).
  Premier répertoire de tests groupé par **invariant** et non par vague —
  amorce de `RM-05b`.
- **Tests added** — session 10, `tests/test_references_resolve.py` (8 cas,
  dont les 3 hérités de `test_adr_references_resolve.py`) : `§n` résout
  contre `SPECS_LIB_V2.md`, une garde contre le vert par vacuité (si le
  motif de titre dérive, le test échoue au lieu de comparer à un ensemble
  vide), et les trois cas du cliquet — aucun fichier propre ne se salit,
  aucun fichier sale ne grossit, aucune entrée périmée ne subsiste.
  `tests/hyphenation/` ajoute 4 fichiers et 0 cas : **exactement 19 items
  déplacés**, ce qui est le propos. La deuxième tranche en déplace 19 de
  plus — des fichiers entiers, en `git mv` — et ajoute le seul test neuf du
  répertoire, `test_the_net_is_bounded.py` (3 cas).
- **New bugs discovered** — session 10, aucun dans le comportement. Un
  seul constat, corrigé : la troisième phrase brouillée par `e7b465c` est
  un message d'erreur, pas un docstring — donc le seul des trois qu'un
  hôte pouvait lire.
- **Tests added** — session 9, `tests/test_page_workspace_is_not_a_bag.py`
  (4 cas) : champs exacts, gel, aucune méthode, et le gel exercé plutôt
  qu'introspecté.
- **Tests added** — session 8, `tests/test_import_contract.py` : la règle
  nommée remplace le compte (`test_only_the_named_sites_reach_a_format_or_producer`),
  l'interdit d'import de niveau module (`test_no_core_module_reaches_out_at_import_time`),
  et la borne sur l'auto-import du paquet
  (`test_the_package_self_import_stays_where_it_was_measured`). Sensibilité
  vérifiée puis annulée : un 3ᵉ site d'accès depuis `core` échoue **par nom**.
- **Tests added** — session 7, `tests/test_research_boundary.py` (8 cas) :
  le paquet et un run par défaut ne chargent aucun module derrière un extra
  (sous-processus), et les 6 chemins d'import des 4 scripts de calibration
  résolvent toujours — « derrière une porte » ne doit jamais devenir
  « déplacé ».
- **Tests added** — session 4, `tests/decision/test_fallback_reason_precedence.py`
  passe de 6 à 21 cas : un pin par site (1-3 `_apply_line_acceptance`, 6
  `_refresh_pair_traces` × 3 branches), le mécanisme qui empêche les sites
  assignants de se croiser (l'acceptation saute toute ligne déjà décidée), et
  **`I-1` bout-en-bout** paramétré sur 2 corpus × 3 politiques de perte, avec
  une garde contre le vert par vacuité : si le producteur adverse cesse de
  produire des fallbacks, le test échoue au lieu de passer sans rien vérifier.
- **Risks remaining** — `RM-01` reste ouvert, et la session 3 a relevé son
  enjeu : la classe de défaut visée n'est pas seulement une ligne
  `CORRECTED` portant son texte source (`L9`), c'est une **correction non
  validée qui part dans le fichier** dès que deux passes s'exécutent dans le
  mauvais ordre. Démontré, pas supposé.
- **Risks remaining** — (levé) propre à `RM-1` : la consigne « plafond, pas
  file d'attente » a été tenue — `integrations/vision.py`,
  `producers/llm_edit.py` et `formats/alto/rewriter.py::_emit_string` sont
  intacts. Il reste **8 entrées**, et ce qui reste est une dette d'une autre
  nature avec une autre réponse : les deux constructeurs de `pipeline` sont
  de la **surface de configuration**, pas du threading, et `_attempt_chunk`
  / `_build_correction_report` **assemblent** depuis plusieurs sources au
  lieu de faire suivre une seule chose. Aucun `PageWorkspace` ne les aidera ;
  les réduire demande de trancher ce que le pipeline expose, ce qui touche
  `RM-04` et le gel. À instruire, pas à enchaîner.
- **Risks remaining** — propre à `RM-05a` : les trois tests visent des
  fonctions privées et sont **délibérément tournés vers l'implémentation**.
  C'est le prix d'un filet posé avant la correction ; `RM-01` doit les
  réécrire, pas les contourner, et le `xfail` strict est ce qui force la
  question à se reposer le jour où le garde arrive.

### Mesures de référence — base 2026-08-06, à recomparer à la clôture

Arités mesurées `self`/`cls` exclus : ce qu'un APPELANT doit assembler.

| Métrique | Base | Courant | Cible |
|---|---|---|---|
| Écritures de décision (`corrected_text`/`status`) | 22 énoncés, 7 fonctions, 5 modules | **0** hors `core/decide.py` | atteint |
| Écritures de `fallback_reason` | 4 sans condition / 3 différées | **0 / 2**, un seul écrivain | atteint |
| Ordre des passes de finalisation | contrat en docstring, 0 garde | **refusé si faux** (`_FinalizeOrder`) | atteint |
| `xfail` dans la suite | 1 (strict, `RM-01`) | **0** | 0 |
| Fonctions > 100 lignes, `core/` | 7 (toutes épinglées) | **6** | ≤ 7 |
| `I-1` (raison ⇒ ligne revenue à sa source) | vraie, non énoncée, 0 test | énoncée (`ADR-013`), 6 tests | tenue par `RM-01` |
| Paramètres, maximum du paquet | 19 (`for_provider`) | **11** | ≤ 8 |
| Fonctions > 8 paramètres | 13 | **8**, épinglées | 0 hors liste |
| Fonctions > 8 params sur le chemin de chunk | 9 | **3** | 0 |
| Fonctions > 100 lignes, paquet entier | 13, dont 6 hors mesure | 13, épinglées | ≤ 13 |
| Définitions sous mesure | 0 hors `core/` | 348, paquet entier | tout `src/` |
| Symboles dans `__init__.__all__` | 68 | **66** | atteint (`RM-04`) |
| Modules derrière un extra, frontière tenue | 2 gelés, 0 test | 2 gelés, **3 tests** | tenue |
| Imports interdits dans `core/` | 3, plafonnés par un compte | **1**, nommé par une règle | 1 (seam d'écriture) |
| Noms de format cités dans `core/` | ALTO ×12 attributs + dispatch | **0** | 0 |
| Imports de symboles privés depuis `tests/` | 277 | 277 | en baisse |
| Ratio (commentaires + docstrings) / code, lib | 0,79 | 0,79 | non ciblé, mesuré |
| Couverture bibliothèque | 96,4 % (seuil 85 %) | 96,4 % | ≥ 85 % |

---

## T — Programme de tests (nouveau)

868 fonctions de test bibliothèque, 400 backend — et les deux défauts
d'intégrité de ligne du 25 juillet sont sortis de la **mesure**, pas de la
relecture ni des tests. La cause est identifiée : les fixtures portaient les
`SUBS_TYPE` explicites qui évitaient précisément le chemin heuristique cassé.
**La population de tests est trop proche des abstractions du code.**

Ajouter des tests unitaires ne referme pas cet écart. Trois familles :

| id | item |
|---|---|
| T1 | **Métamorphiques** — **entamé** (`test_metamorphic_hyphenation.py`) : page vide insérée → mêmes décisions **et** paire toujours liée (a trouvé le cas `L5` de la page vide) ; même coupure intra-page ou inter-pages → même texte ; tout signe du répertoire apparie pareil. Même document découpé autrement → même décision (`fcd7804`) ; mêmes pages regroupées autrement → même décision ; même césure intra-page ou inter-pages → même résultat logique ; page vide ajoutée → aucune autre décision ne bouge ; signe de coupure substitué par un équivalent autorisé → unité conservée. **2026-08-13** : ordre des fichiers d'entrée indifférent (`test_input_order_is_not_a_decision.py`, élargie au script d'édition après qu'une première version soit passée sur `F4`) ; **seconde passe sur la sortie = point fixe** sauf le `postProcessingStep` ajouté (`test_a_second_pass_changes_nothing.py`) — la mutation qui réutilise ce pas au lieu de l'ajouter laisse **toute la suite au vert**, donc la perte de provenance d'un re-run n'était vue par rien |
| T2 | **Corpus adversarial** — le corpus de formes qui n'existe pas : U+00A0 et U+202F, gamme complète des tirets, chaînes de 3-4 membres, césure inter-pages réelle, lignes sans `SUBS_TYPE`, lignes vides et éléments non textuels intercalés, ALTO de plusieurs producteurs, PAGE Transkribus et eScriptorium réels |
| T3 | **Différentiels** — comparer décision logique, texte réextrait, octets XML, attributs conservés, géométrie, compteurs de perte et statut de ligne. « Le XML est valide » n'est pas le résultat attendu. **Entamé, trois invariants** : `test_status_truthfulness.py` (statut × texte source × proposition) a trouvé `L10` sur le fichier BnF ; `test_payload_truthfulness.py` (ce qu'on dit au modèle × ce que porte le manifeste) a trouvé la promesse de jointure fausse ; `test_link_symmetry.py` (A pointe B ⟺ B pointe A) — **résultat négatif** : la symétrie tient sur le corpus généré et les fixtures réelles, ce sur quoi le cœur de `S1` pourra s'appuyer. **2026-08-13, deux de plus** : la somme des pertes par ligne reproduit l'agrégat (`test_the_two_loss_accountings_agree.py`) — promesse du contrat, vérifiée nulle part, famille `R1` ; rejouer le script d'édition rendu reproduit le fichier rendu (`test_the_edit_script_replays_to_the_delivered_text.py`) — promesse écrite dans la docstring de `_build_final_edit_script`, et les deux surfaces n'étaient jamais comparées ; **ce que le rapport dit du fichier, relu dans le fichier** (`test_the_report_and_the_file_say_the_same_thing.py`) — le réécriveur lit ses textes de sortie sur l'arbre « without a second full parse of the output », et rien ne relisait les octets rendus : retirer U+00A0 après sérialisation laisse 1407 tests au vert |

`T2` alimente `M5` (le corpus épinglé bloquant) : c'est le même corpus.

---

## G — Ce que le système ne peut pas établir (post-`0.10`, requis pour `1.0`)

Les gardes comparent des caractères et n'ont **aucune notion de sens** : sur 12
contre-exemples passés dans la vraie `check_line`, tous acceptés aux deux seuils
— dont une négation supprimée (0.8955), une date changée (0.9388), un montant
tronqué (0.9643) et la copie verbatim d'une ligne voisine (0.8852).
**Aucun réglage de seuil ne ferme cette famille** ; c'est une propriété de
conception, pas un bug à corriger par des seuils.

Un détecteur empirique a levé 56 lignes à chiffres modifiés sur le run réel : la
quasi-totalité étaient de **bonnes** corrections, ce qui n'a pu être déterminé
qu'avec la vérité terrain. En production il n'y en a pas.

| id | item |
|---|---|
| ~~G1~~ | **fait (2026-08-27).** `LineStatus.REVIEW_REQUIRED`, quatrième statut terminal. La correction est **livrée** — mêmes octets, même opération dans l'`EditScript` — et le run déclare ne pas pouvoir l'établir. Un quatrième verbe dans `core/decide.py`, `refer_for_review`, qui n'écrit **que** le statut : c'est le miroir exact de `renormalise`, qui n'écrit que le texte. Le seul site du paquet qui demandait `status is CORRECTED` pour savoir « cette ligne porte-t-elle une correction ? » était `_build_final_edit_script` ; il demande maintenant `LineDecision.carries_a_correction`, sans quoi rejouer le script aurait cessé de reproduire le fichier livré |
| ~~G2~~ | **fait pour ce que le moteur peut alimenter, et les absences sont écrites.** Cinq règles rendues, six codes clos dès l'écriture (`REVIEW_REASON_CODES`) : `digits_changed` (couvre dates et montants — aucune grammaire, le constat suffit), `negation_changed`, `proper_noun_changed`, `systematic_substitution` / `systematic_removal` (la règle au niveau du RUN, le cas `⸗` 34/34 et `’` 69/69), plus `hyphen_unit_review`, conséquence et non décision (ADR-010). **Trois n'existent pas, chacune parce que le moteur n'a pas d'entrée pour elle** : « ligne propre modifiée » — écrite, mesurée, retirée : sans lexique elle renvoyait **30 des 47 lignes modifiées** du corpus de vérité terrain, 23 sur son seul indice, et ce qu'elle attrapait était de simples corrections `f` → `ſ` ; le désaccord texte/vision — aucun run n'interroge deux producteurs sur la même ligne, l'escalade *remplace* ; la confiance sous seuil — l'agrégat est construit après que le `DecisionSet` est immuable, et `core/confidence.py` dit lui-même que ses valeurs ne sont pas calibrées. Taux mesuré sur le corpus de vérité terrain : **11 des 47 lignes modifiées** renvoyées, 23 % |
| ~~G3~~ | **fait.** `docs/la-vie-d-une-ligne.md` §3 bis (le tableau repli/renvoi, les six codes, les trois absences), `docs/reading-a-report.md` (`review_lines` n'est pas un taux de défaut), `README.md` (« What it does not claim to have checked »), `docs/promises.md` (relevé du 2026-08-27), `docs/versioning.md` (ajouter un membre à `LineStatus` est une rupture, et celle-ci est assumée) |

**Ce que la vague `G` n'a pas fait, et où c'est suivi.** Les trois règles
absentes ci-dessus ne sont pas de la dette : deux demandent une entrée que le
moteur ne produit pas (un lexique injecté, un mode de routage qui interroge
deux producteurs et garde les deux réponses) et la troisième demande le
harnais de calibration. Chacune est écrite à l'endroit où quelqu'un ira la
chercher — le module qui aurait dû les porter — plutôt qu'ici comme un item
qui attend.

---

## M — Mesure

| id | item |
|---|---|
**Où ces items s'exécutent — changé le 2026-08-16.** `M1`-`M4` et `M7` ne
s'exécutent plus dans ce dépôt : le banc local (`scripts/vision_benchmark.py`
et ses voisins) est **retiré**, pas déménagé, au profit de `cinoc`. La raison
est dans la décision n°6 ci-dessus. Ce qui reste ici est le **critère** — la
règle de publication ci-dessous, et `M5`, qui est une porte de CI de ce dépôt.

| id | item |
|---|---|
| M1 | Le chemin **inter-pages n'est mesuré par aucun run** : aucun fichier du corpus ne finit sur un mot coupé, et le banc traite chaque fichier comme un document d'une page. **Constat élargi le 2026-08-16** : `cinoc` n'a pas non plus la notion de document multi-pages — tous ses importeurs émettent un document par page et son standardiseur tronque au premier feuillet. `M1` demande donc un corpus multi-pages réel **et** la notion de volume côté banc |
| M2 | Variance : **≥5 runs par configuration, publier une fourchette, jamais une décimale isolée**. **Campagne du 2026-08-14 : faite, puis invalidée par elle-même.** Les cinq runs (0.0338–0.0357, écart 5,6 %) précèdent le correctif de banc `2e0b7bc` et héritent donc du défaut qu'ils ont trouvé — l'appariement de césure était dérivé de la référence humaine et non du texte donné au moteur. Le contrefactuel (0.0243–0.0263) est un re-calcul, pas une mesure. **Une campagne post-correctif reste due**, et elle se fera sur `cinoc`, qui n'a aujourd'hui **aucun mécanisme de runs répétés** — c'est la brique 4 de la phase d'intégration |
| M3 | **≥2 familles de modèles** pour séparer ce qui tient du système de ce qui tient du modèle. **Fait le 2026-08-21, à coût nul, et il répond à sa question.** Trois familles sur la vérité terrain BNL, base propre de **516 lignes** (voir plus bas pourquoi 516 et non 522) : OCR brut **0,1049** ; `churro-3B` en vision **0,1044** (62 mieux / 11 pire) ; `gemma4:e2b` en texte **0,1021** (112 / 43) ; `mistral` en vision **0,0361** (337 / 10). **Le système ne varie pas, le modèle varie d'un facteur trois** — même chaîne, mêmes gardes, même alignement, et aucune des trois familles n'a fait casser l'appariement. Ce que `M3` existait pour séparer est donc séparé : l'écart de qualité est imputable au modèle, pas au harnais. **Deux conséquences qui coûtent plus cher que le classement** : aucun modèle local mesuré n'approche Mistral, et le bras local le plus gagnant en CER (`gemma4:e2b`) est aussi celui qui **abîme quatre fois plus de lignes** que `churro-3B` — pour une bibliothèque dont le principe est « l'application décide », le CER seul choisit mal. Le prérequis reste vrai et non fait : l'adapter Ollama de `cinoc` est `text_only`, la vision a été prototypée hors dépôt |
| ~~M4~~ | **retiré le 2026-08-16, sur mesure.** L'item disait : récupérer les 16,5 % de CER dus à deux « normalisations systématiques » du modèle, par consigne de prompt ou normalisation inverse. Ses deux exemples sont mal attribués, et le compte contre l'ENTRÉE plutôt que contre la référence le montre : le signe de coupure `⸗` **n'atteint jamais le modèle** (0 occurrence dans l'OCR d'entrée, 36 dans la référence — il n'y en a jamais eu à effacer), et l'apostrophe typographique est **détruite par l'OCR puis réparée par le modèle** (50 lignes améliorées, 0 dégradée). Il n'y a donc rien à récupérer *ici* : la perte est en amont, dans l'OCR, hors du périmètre de cette bibliothèque par conception. **Ce qui survit et vaut mieux que l'item** : compter une substitution contre l'entrée et non contre la référence, faute de quoi on attribue au correcteur ce que l'OCR a fait. Et le cas `⸗` reste une entrée de `G2` — une substitution qui porte sur *toutes* les occurrences d'un signe est invisible ligne à ligne et évidente au run |
| ~~M5~~ | **fait (2026-08-16).** Trois pages Gallica réelles épinglées — *Le Temps* du 1ᵉʳ janvier 1890 (quotidien multi-colonnes, 1,7 Mo), et deux monographies de 1850 dont une en mode texte. 1,89 Mo pour deux époques et deux mises en page. Les trois empreintes étaient déjà dans `manifest.json` et le téléchargement les a vérifiées **sans dérive**. Mesuré : le tier épinglé fait tourner **6 tests hors ligne et sans marqueur** là où l'état d'avant en sautait 2 — le corpus externe ne contribuait donc à **aucun** merge. Le tier téléchargé reste `continue-on-error` à dessein : il dépend de gallica.bnf.fr, et une panne de réseau ne doit pas arrêter un merge |
| M6 | Corpus GT : 2 paires réelles seulement dans `tests/corpus_gt/`. Sourcer de la GT publiée plutôt que la fabriquer |
| M7 | Rendre publiables : CER **et** WER, lignes améliorées / dégradées / faux positifs, **analyse par classe Unicode**, et mesure séparée sur OCR mauvais / moyen / déjà propre. **Largement acquis par le déménagement** : `cinoc` porte 24 métriques dont CER, CER diplomatique, WER, MER, taux d'insertion/délétion, hallucination, sur-normalisation, et des tests de significativité. Restent à ajouter là-bas : la ventilation par classe Unicode générale et la strate « qualité d'OCR d'entrée » |

Aucune revendication de qualité ne sort du dépôt sans `M2` + `M3`.

---

## D — Vérité documentaire — **close (2026-07-28)**

Le 25 juillet a consolidé `docs/` ; **les documents d'entrée n'ont pas suivi**.
`D8`-`D11` étaient les trois portes par lesquelles un lecteur arrive.

**Les douze sont fermés.** Le motif récurrent mérite d'être noté, parce qu'il
se reproduira : dans **cinq** cas sur douze le corps du texte était juste et
c'est le **nom** ou le **titre** qui mentait — `institutional` (`D12`),
`PUBLIC_API_1_0` (`S3a`), le titre d'`I4` (`D1`), les en-têtes de version du
`CHANGELOG` (`D4`), l'arbre `§3` (`D2`). Un lecteur fait confiance à
l'étiquette avant le paragraphe. Et dans **deux** cas, l'énoncé du plan était
lui-même inexact (`D2` plus large, `D4` plus dur), ce qui est la raison de
mesurer avant de corriger.

| id | item |
|---|---|
| ~~D1~~ | **fait** — vérifié le 2026-07-28 : `SPECS §I4` est titré « Le cœur est aveugle aux pixels » et porte la portée en trois niveaux ; `packages/saknussemm/README.md` dit « **the core** forwards an opaque image reference and touches no pixel ». Remplacement de mots, aucun arbitrage — la conception, elle, était déjà juste et vérifiée mécaniquement |
| ~~D2~~ | **fait (2026-07-28)** — et plus large que l'énoncé. L'arbre `§3` décrivait un paquet nommé `lib/` avec **7** modules de cœur, sans `integrations/`, sans `errors.py`, sans `facade.py`, et avec un `producers/llm.py` inexistant ; le vrai cœur en a **21**. Réécrit depuis l'arborescence réelle. `§5.1` montrait `produce(payload: ModelPayload, *, policy: RetryPolicy)` : un type qui n'existe pas, et le `RetryPolicy` complet que **P3.7 a précisément retiré** de cette couture — la spec contredisait sa propre prose sur `ProducerOptions` |
| ~~D3~~ | **fait (2026-07-28)** — `0.0021` porte désormais sa provenance : un **VLM oracle**, producteur simulé qui rend la vérité terrain. Le chiffre mesure le **routage**, pas un modèle. Lu comme une borne supérieure de ce que le routage peut acheter, jamais comme une revendication de qualité |
| ~~D4~~ | **fait (2026-07-28) — et le vrai constat est plus dur que l'énoncé.** Le nombre a grossi : **1 221** lignes / **81** entrées sous `[Unreleased]` (827 au 25/07). Mais le défaut n'est pas la taille : le `CHANGELOG` porte **trois en-têtes de version datés** (`[0.9.0]`, `[0.9.0 initial scope]`, `[0.1.0a1]`) alors qu'il existe **0 tag git** et **0 publication** — des jalons de développement présentés comme des versions. Corrigé en tête de fichier, sans mentir : rien n'a jamais été publié, donc rien n'est dû à personne, et la section qui porte tout l'historique des ruptures d'API est bien celle que SemVer déclare non engageante. Plus un **index des ruptures** (13 entrées) pour qu'elles soient une *liste* et non une trouvaille au défilement. Découper une section de release demande un tag : c'est `P1`/`P2`, pas ici |
| ~~D5~~ | **fait (2026-07-28) — l'asymétrie était juste, son silence ne l'était pas.** On dispatche sur `report.report_version`, le **champ** lu sur l'artefact qu'on tient : la constante dit ce que *cette* installation émet, donc la comparer à un rapport chargé n'apprend rien sur ce rapport. D'où la différence avec `EDIT_PROTOCOL_VERSION`, exporté : la version du protocole d'édition, un producteur la **déclare** ; celle du rapport, un lecteur la **trouve**. Écrit dans `versioning.md`, avec le chemin de module pour l'outil qui a vraiment besoin de la constante. Ajouter la constante à `__all__` aurait fait **grandir** la surface, ce que le cliquet de `S3a` interdit |
| ~~D6~~ | **fait (2026-07-28)** — `packages/saknussemm/docs/reading-a-report.md` : pour chaque chiffre du rapport, ce qu'il dit **et ce qu'il ne dit pas**. `0 fallback` = « aucune proposition refusée », ce qui est presque l'inverse de « rien n'a changé » ; `format_losses is None` ≠ « rien n'a été perdu » (un caractère aplati est compté sur l'échelle de fidélité) ; `exact` compare le fichier à la **décision**, pas à la vérité. Plus la section qu'aucun chiffre ne couvre : les gardes sont **structurelles** — aucune ne connaît le français, et une lecture plausible, fluide et fausse les passe toutes |
| ~~D7~~ | **fait (2026-07-28) — zéro sur les quatre.** Mesuré avant : `src/`+`app/` **27** `ROADMAP V3` / **69** `Phase N` / **25** `Audit-F`, tests **33 / 56 / 4 / 1**. Après : **0 / 0 / 0 / 0** dans tout `.py` et dans les documents normatifs. La forme dominante était une **étiquette de provenance** devant une phrase qui portait déjà sa raison : l'étiquette part, la phrase reste. Les usages en prose (« la calibration de Phase 2 ») sont remplacés par la **raison** — « la calibration contre un corpus réel » — parce qu'un numéro de jalon d'une feuille de route gelée n'est pas consultable. Quatre fichiers de test dont le **nom** était l'étiquette ont été renommés d'après ce qu'ils testent. **Incident à retenir** : la première passe portait une règle de rangement de parenthèses qui a recollé des fermetures multi-lignes dans **213 fichiers** — syntaxiquement valide, donc les tests seraient passés au vert sur un diff qui reformatait tout le dépôt. Revertée. Un balayage sur du source touche le **texte** des commentaires, jamais la forme du code autour |
| ~~D8~~ | **fait** — le `README` annonce ALTO **et** PAGE dès le titre, l'accroche et la matrice de versions |
| ~~D9~~ | **fait** — la carte documentaire nomme `docs/PLAN.md` comme **le** plan unique et `docs/audit/` comme les constats, à côté de l'avertissement sur `docs/history/` |
| ~~D10~~ | **fait** — `SECURITY.md` ne renvoie plus vers `docs/history/` : vérifié, zéro occurrence. La question qui décide de l'adoption ne pointe plus vers un document gelé |
| ~~D11~~ | **fait** — vérifié le 2026-07-28 : la seule chaîne visible par l'utilisateur dit « Upload ALTO / PAGE files ». Les occurrences restantes d'« ALTO » dans `frontend/src` sont des commentaires internes et des fixtures de test |
| ~~D12~~ | **fait (2026-07-28)** — `institutional` → **`proxy_protected`**. Le corps de `SECURITY.md` était honnête (pas de comptes, pas de propriété de job, pas de quotas, pas de base, mono-worker) ; le **nom** disait l'inverse de son propre paragraphe. Le nouveau nom énonce exactement ce qui est asserté : un proxy authentifiant est devant, rien de plus. `DEPLOYMENT_PROFILE` est une variable **publique**, donc l'ancienne valeur reste acceptée et **avertit** — et pas seulement par courtoisie : une valeur inconnue retombait sur le défaut tolérant au CORS joker, donc un simple renommage aurait fait **accepter en silence** ce qu'un opérateur avait demandé de refuser. Cinq tests, dont celui du message d'erreur qui doit nommer le **nouveau** nom |

---

## P — Publication

| id | item |
|---|---|
| P1 | Répétition sur TestPyPI (le workflow n'a jamais été exercé, 0 tag git) | **répétée en local (2026-08-01), upload non fait** — il demande l'OIDC de GitHub Actions. Toute la chaîne du workflow rejouée : `python -m build`, `twine check` (PASSED sur les deux artefacts), smoke-install de la wheel (`_smoke_imports.py` : 67 symboles publics), SBOM CycloneDX + l'assertion anti-pollution, cohérence `__version__` ↔ CHANGELOG, forme du tag attendu (`saknussemm-v0.9.0`). **Deux constats, corrigés** : (a) le sdist livré ne correspondait pas à son allowlist — hatchling traite les entrées comme des MOTIFS, donc `README.md` attrapait `tests/corpus_gt/README.md` et `tests/external_corpus/pinned/README.md` ; aucune donnée de corpus n'est jamais partie, mais le test de packaging vérifiait la *déclaration* et non l'artefact. Entrées ancrées (`/README.md`), test réécrit pour lire le sdist et la wheel CONSTRUITS. (b) la CI sautait `twine check` sur une raison périmée (twine < 7 rejetait `License-File` de Metadata 2.4) : twine 7 l'accepte, vérifié sur cette wheel, la porte est rétablie | reste : dispatcher le workflow sur `testpypi` depuis GitHub, ce qui exige le tag donc `P2` |
| P2 | Premier tag `0.10.0`, SBOM, publier l'artefact testé |
| P3 | `1.0.0` uniquement : revue humaine externe indépendante de l'API publique, après `V1`-`V9` |

---

## Explicitement différé — NE PAS TOUCHER

Ce sont des décisions, pas des oublis. Détail et justification dans
`AUDIT-2026-07-25.md` §5.

- **`OracleVisionProducer`** — pas du code mort : c'est la mesure du plancher de
  plomberie, hors ligne et gratuite. Reste le défaut du banc.
- **`write_wc`** verrouillé tant que la calibration ne passe pas.
- **`CandidateSet`**, **sérialisation seq2seq** (§5.4), **producteur
  `replace_span`** (v2.1), **remappage d'offsets `custom` PAGE** (v2.x).
- **`split_forward_link` retirant Stage A/B** — repli conservateur assumé.
- **Césure inter-pages jamais escaladée vers le VLM** — conservateur volontaire.
- **L'aveuglement sémantique des gardes** — propriété de conception. Aucun
  réglage de seuil ne ferme cette famille ; la réponse est `G*`, post-`0.10`.
- **Parité inter-formats §6.3**, byte-parity côté PAGE, fixtures eScriptorium —
  post-`0.10`.

---

## Répartition

**Claude Code CLI** — dépôt, tests, mesures : `L*`, `R*`, `S*`, `T*`, `G1`-`G2`,
`M1`-`M5`, `M7`, `D1`, `D3`-`D5`, `D7`-`D11`, `P1`-`P2`.

**Claude Desktop** — recherche, décision, documents : `Gate 0`, `M6`, `D2`,
`D6`, `D12`, `G3`, `P3`.

### Ordre

**Lot 0 — vérité documentaire, sans risque, immédiat.** `D8`, `D9`, `D10`, puis
`D11` et `D1`. Ils ferment quatre mensonges de façade en quelques lignes et ne
dépendent de rien. À faire avant le reste, parce que chaque jour où ils restent
est un lecteur trompé.

`D1` était assigné à Desktop tant qu'on le croyait porteur d'un arbitrage de
conception. Il n'en porte aucun — l'architecture est déjà celle qu'il faut et
elle est testée ; il ne reste qu'un mot à corriger à trois endroits. Il revient
donc ici, en Lot 0.

**Lot 1 — intégrité (bloquant `0.10`).** `L0` → `L1` → `S1`+`L2` ensemble →
`L3` (doit tomber presque seul) → `L5`, `L7`.

**Lot 2 — honnêteté (bloquant `0.10`).** `R0` d'abord, puis `R1`-`R8`. `S2` peut
s'intercaler ici : la comptabilité est plus facile à réparer une fois le rapport
assemblé hors du contrôle d'exécution.

**Lot 3 — réduction (bloquant publication).** `S3`, `S4`, `S5`, `D7`, `D4`,
`D5`. Puis `P1`, `P2` → **`0.10.0`**.

**Lot 4 — vers `1.0`.** `T1`-`T3` et `M5` en continu dès le lot 1 (ils trouvent
les défauts des lots suivants) ; `M1`-`M3`, `M7` ; `G1`-`G3` ; `D12` ; `P3`.

**Vague `RM` — structurelle, s'intercale avant `S1`.** `RM-0` (vérité) est fait.
`RM-1` (instrument) et `RM-2` (le défaut `RM-01`) précèdent tout autre travail
sur `core/` : le premier répare la métrique qui gouverne les découpages, le
second ferme la seule classe de défaut latent de la vague. `RM-3` à `RM-6`
peuvent s'intercaler librement. **`RM-1` et `RM-2` doivent précéder `S1`** —
`S1` est le plus gros refactor restant sur `core/`, et l'engager avec une
métrique qui récompense le drilling et sans garde sur l'ordre des passes
reproduirait dans la famille césure ce que `S2` a produit dans
l'orchestration. `RM-08` est un constat d'entrée de `S1`, pas un item séparé.

`Gate 0` en parallèle sur Desktop, du premier jour au dernier — c'est le seul
item qui peut bloquer `P2` sans avertissement.

---

## VR — Vus en run (2026-09-24)

Le premier passage d'un corpus à vérité terrain (OCR17+, 9 pages, `medium`)
**à travers le pipeline lui-même** — et non à côté, comme toutes les
campagnes de `hans` jusque-là — a montré sept choses que les scripts ne
pouvaient pas voir (dépôt `hans`, rapport `H16` ; PR #166). Chacune est un item ici,
avec la mesure qui l'a fait apparaître et celle qui dira qu'il est clos.
Règle commune : **tout item qui change ce que le modèle voit ou ce que le
garde accepte se vérifie par un run**, parce que les gardes, les retries et
la descente de granularité font différer le résultat de celui du script.

### Carte

| ID | Titre | Nature | Gravité | Fichiers | Dépend de | Statut |
|---|---|---|---|---|---|---|
| `VR-1` | Aucun producteur ne donne au modèle **l'image de la page entière** — le levier de qualité mesuré (4,58 % contre 6,25–6,74 % pour les recadrages, zéro ligne mal rattachée) n'a pas de chemin dans la bibliothèque | **fonctionnalité** | **critique** | `producers/vision.py` | — | **fait et vérifié** : `page-vision` + note de corpus + `vision(attachment_scope="page")` = **4,19 %**, 0 mal rattachée (script `hans` : 4,58 %) |
| `VR-2` | Le planificateur BLOCK fait **un chunk par groupe de régions** sans regrouper les petites : 105 chunks pour 251 lignes, bandes composites de 2–3 rangées | correctif (planificateur) | important | `core/planner.py`, `core/schemas/policies.py` | — | **fait et vérifié** : 105 → 16 chunks, jetons ÷ 2 ; avec la note de corpus le composite regroupé lit à **4,23 %** |
| `VR-3` | `VisionEditProducer` sans `max_images` déclaré envoie 19 recadrages ; le fournisseur refuse ; le pipeline **retente et redescend au lieu de découper** | correctif (configuration silencieuse) | important | `producers/vision.py` | — | **fait** |
| `VR-4` | Le prompt générique de `page_aligned` **modernise** le français du XVIIe (`meritay-je` → `mériterais-je`) : 10,96 %, pire que ne rien faire ; une règle nommant l'époque ramène à 6,71 % | correctif (contrat de prompt) | **critique** | `integrations/llm.py` | — | **fait et vérifié** : texte 10,96 → 6,71 % ; vision 6,29 → **4,39 %** (page entière), 6,19 → 4,23 % (composite). Sans la note, aucun producteur n'atteint le chiffre du script ; avec, tous le dépassent |
| `VR-5` | Un séparateur de ligne dans une ligne rendue épuisait la page sous `characters` (4 retries, 1 descente, 19 lignes en `all_attempts_exhausted`) | bugfix | important | `producers/page_llm.py` | — | **fait (4d2c5c5)** |
| `VR-6` | `hyphen_pair_fallback` touche 13 à 18 lignes par bras (5–7 %) ; on ne sait pas combien de bonnes corrections il coûte | mesure | important | `core/hyphenation.py` (lecture) | `VR-1` | **mesuré** : sur `page-vision·page`, 21 lignes (8 %), CER source 10,7 % gardé tel quel ; corrigées au taux des autres, le CER global passerait de 6,29 à ~5,87 % — 0,4 point. Le reste de l'écart avec le script (4,58 %) est dans la lecture des lignes corrigées (4,98 % contre 4,08 %), donc dans le prompt (`VR-4`) |
| `VR-8` | `crop_region` décodait, transposait et convertissait **la page entière pour chaque ligne** : sur une page de presse de 60 Mpx, deux copies de 190 Mo par recadrage, vingt par chunk — run tué par macOS | bugfix (mémoire) | **critique** sur la presse | `producers/vision.py` | — | **fait** : `open_page` une fois par chunk, recadrage avant conversion, octets identiques |
| `VR-9` | Une ligne rendue **vide** par un producteur vision (« illisible », comme son prompt le demande) est refusée par le validateur : 29 retries sur 67, 22 descentes, **342 lignes rendues à l'OCR par chunks entiers** sur NewsEye | bugfix (contrat producteur ↔ validateur) | **critique** sur la presse | `producers/vision.py` | — | **fait et vérifié** (NewsEye, 8 pages) : chunks repliés 234 → 115, retries 67 → 41, `all_attempts_exhausted` 342 → 166 ; CER inchangé, les chunks rendus étant sur des pages hors domaine |
| `VR-10` | L'étage A (`validator._check_pair_drift`) **refuse le chunk entier** quand une ligne PART2 « s'effondre » (moins de 0,4 × ses mots OCR). Sur la presse Tesseract, les PART2 en bouillie (`monter... ‘1 Dore Se`, `à M me ne`) sont rendues en un mot lisible : effondrement, retry, descente, et **64 chunks entiers rendus à l'OCR sur une seule page** (0401692, avec `VR-9` en place) — 180 lignes, dont la quasi-totalité n'avait rien à voir avec la paire | **décision** (remède de l'étage A, spec §7) | **critique** sur la presse | `core/validator.py`, `core/attempt.py` | `VR-9` | à trancher : (a) au dernier essai, replier la **paire** seule et garder le reste du chunk — l'étage B sait déjà replier une paire ; (b) ne pas compter comme « mots » les jetons sans lettre d'une PART2 OCR, pour qu'une bouillie de quatre jetons rendue en un mot ne soit pas un effondrement. (b) est un correctif de mesure, (a) change le remède ; mesurer (b) d'abord. **Incidence mesurée** : sur le run NewsEye avec VR-9, 155 lignes rendues à l'OCR par chunks entiers, à 22,5 % de CER ; le bras recadrage-par-ligne, qui les a corrigées, les a mises à 20,2 % (47 améliorées, 12 dégradées) — soit **0,07 point** de CER global. Le remède compte pour le coût (retries, descentes) et la propreté, pas pour la qualité : ces chunks sont sur les pages où le modèle ne peut pas grand-chose. **Une paire qui dérive n'est pas le signe d'un chunk pourri** : sur ces mêmes lignes, corrigées par le bras recadrage-par-ligne, 72 % améliorées / 18 % dégradées — exactement le taux de toutes les autres lignes (72 / 18). **Fait (a), vérifié (2026-09-24, NewsEye, bras composite)** : chunks repliés **115 → 1**, retries 41 → 29, `pair_drift_fallback` 18 lignes, `all_attempts_exhausted` 17 ; CER 18,59 → **18,48 %** ; le run a fait apparaître `VR-11` |
| `VR-7` | Le profil `vision()` abaisse le plancher à 0,15 sans la portée page ; avec elle, le plancher bas est-il tenable ? | mesure puis décision | important | `core/schemas/policies.py` | `VR-1` | **mesuré, deux corpus.** OCR17+ : `vision(attachment_scope="page")` 6,03 % / 4,19 % avec note, **0** mal rattachée, contre 6,17 % / 4,39 % à 0,35. NewsEye (production, 5 102 lignes) : à 0,15 + page, 21,20 → **18,28 %** (script : 18,30 %), **3 lignes réellement mal rattachées** sur 2 568 changements, toutes sur les deux pages hors domaine (45–57 % de CER, un tiers des lignes ratées par Tesseract), toutes sorties en `review_required` ; à 0,35 + page (composite), 1. Dans les quatre cas le texte posé est celui d'**une ligne que l'OCR n'avait jamais produite** — la marge ne peut pas voir une source qui n'existe pas, c'est la limite écrite en `hans` H12. Décision proposée : `vision()` adopte `attachment_scope="page"` ; le plancher 0,15 reste réservé aux pages qui passent le triage géométrique. **Coût de la marge, mesuré sur les sorties des scripts (mêmes trois corpus)** : OCR17+, plancher seul 4,10 % / 0 mal rattachée, avec marge 4,61 % / 0 — la marge coûte 0,5 point (12 corrections justes refusées, toutes des jumelles) et ne gagne rien là où le modèle ne dérive pas ; HIPE, 0,15 seul 2,31 % / **1**, avec marge 2,36 % / 0 ; NewsEye (boîtes VT), 0,15 seul 6,84 % / **64**, 0,35 seul 6,70 % / **10**, avec marge 7,37 % / **0**. La marge coûte 0,5–0,7 point et c'est elle qui fait le zéro dès que le modèle dérive. Normaliser la ressemblance (casse, ſ/s, accents) n'aide pas ; l'exemption des jumelles rend 0,2 point sur le théâtre ; une marge à 0,10 rend 0,3 point sur NewsEye en gardant zéro — mais réglée après coup, donc non retenue. **Décidé et fait (2026-09-24)** : `vision()` tient `attachment_scope="page"`, plancher 0,15 gardé |
| `VR-11` | **Un membre de paire de césure réconcilié saute l'étage C** : `_apply_line_acceptance` passe toute ligne qui tient déjà un texte, et l'étage B ne juge que la migration entre les deux moitiés — ni plancher, ni marge. Vu au run de vérification de `VR-10` : PART1 rendue « ce que notre grand mor- » (source « au. nt comme orateur, 'une situation in- »), livrée `corrected` alors que la page tient une ligne OCR « ce que notre grand mo » ; rejouée, `check_line` la refuse (`closer_to_another_line`, 0,95 contre 0,31) | bugfix (garde) | **critique** — la règle du mainteneur est 0 ligne mal rattachée | `core/acceptance.py`, `core/guards.py`, `core/outcome.py` | `VR-7` | **fait** : les membres que B vient d'accepter repassent plancher + marge (pas l'absorption, que B possède), un refus replie l'unité (`hyphen_unit_fallback`) ; `check_line(absorption=...)` ; deux empreintes `drift` bougent (bouillie sur une paire, rendue à la source). **Vérifié** (NewsEye, composite, 2026-09-24) : 18,48 → 18,45 %, 36 signalées / 3 réelles — les trois connues, toutes hors domaine, aucune nouvelle ; la garde a joué une fois, sur une chaîne de trois membres de *Paris-Soir* refusée au plancher (`too_different_from_source` + 2 × `hyphen_unit_fallback`) |
| `VR-12` | **Une demi-ligne réécrite sans appui dans la source passe le plancher** — vu à l'œil (`hans`, H19) : sur NewsEye (composite), « Lutte contre l'impérialisme des puissances, lutte contre le fascisme et contre la guer- » pour « raison au sein de l'Union rationaliste, lutte contre le fascisme… » : la première moitié n'est nulle part sur la page (une invention sur le moule de la ligne du dessus), la seconde est juste, la ligne reste à ~0,6 de sa source, le plancher 0,15, la marge et l'absorption passent, et c'est livré `corrected`. Deux autres cas, d'un mot pris à la voisine en tête de ligne (« TIR. », « pouvoir »), ont été annotés `review_required` par la règle des noms propres — ce qui ne change aucun octet livré : **les trois sont livrés**, et en production personne ne relit. Les comptes « 0 mal rattachée » de `VR-1`/`VR-7` sont ceux du proxy (ligne entière) et tiennent : aucune ligne n'a reçu le texte d'une autre en `corrected` | mesure puis garde | important | `core/guards.py` | `VR-11` | **à mesurer avant d'écrire** : par mots — la part des mots de la correction sans mot proche dans la source de la ligne (ici 5 sur 13). Sur les runs existants, chiffrer cette part pour les corrections justes (une ligne en bouillie corrigée juste en a beaucoup) ; s'il n'y a pas de seuil qui sépare, il n'y a pas de garde — un renvoi en revue n'est pas une réponse, il ne change aucun octet et personne ne relit en production. Le composite y est plus exposé que le recadrage par ligne |
| `VR-14` | **Une réponse en NFD rend la page non livrable** : les parseurs lisent en NFC, les réécrivains écrivent en NFC, mais la décision garde le texte du modèle tel quel ; « aisé » décomposé (e + U+0301) décidé, écrit précomposé, et `_verify_projection` voit deux chaînes → `ProjectionError`, fichier absent de `corrected_files`. Vu trois fois sur OCR17+ (Descartes ×2, Corneille) pendant la campagne H20, intermittent | bugfix | **critique** (une page entière perdue sans erreur visible) | `core/editing.py` | — | **fait** : `ReplaceLine.text` et `ReplaceSpan.text` normalisés en NFC à la construction — le seul point par lequel tout producteur passe ; test de bout en bout avec un producteur qui répond décomposé |

### Ordre

`VR-1` d'abord — c'est le producteur qui porte le gain, et `VR-6`/`VR-7` se
mesurent sur son run. Puis `VR-3` (petit, ferme un défaut silencieux),
`VR-2` (le composite ne peut pas être mesuré à sa vraie taille sans lui),
`VR-4` (une constante et une phrase de documentation ; la mesure est déjà
faite). Chaque item change soit ce que le modèle voit, soit ce que le garde
accepte : **run de vérification à chaque fois**, sur les mêmes neuf pages,
comparé au bras équivalent de `hans`.

**Clôture (2026-09-24, mise à jour après le run de vérification de `VR-10`).** Onze items : `VR-1` à `VR-6`, `VR-8`, `VR-9`, `VR-10` faits et vérifiés par run ; `VR-7` décidé par le mainteneur et fait ; `VR-11` fait et vérifié (18,45 %, aucune nouvelle ligne mal rattachée **au proxy**). Relecture à l'œil (`hans`, H19) : au sens de la règle (aucune ligne ne reçoit le texte d'une autre), deux mots pris à la voisine et une demi-ligne **inventée** (composite), **tous trois livrés** — `review_required` n'y change aucun octet — et que le plancher ne voit pas ; d'où `VR-12`, à mesurer. Mesuré aussi : le voisinage des paires `VR-10` n'est pas plus mauvais que le reste (68,9 / 17,8 % contre 66,2 / 22,7 %). **La vague est close hors `VR-12`** ; reste au mainteneur : merger la PR #166, et décider de `VR-12`. Sur la presse en production (`hans`, rapport `H17`) : recadrage par ligne + `vision(attachment_scope="page")` 21,20 → 18,28 %, composite avec `VR-10` 18,48 %, au niveau du script. Le run de `VR-10` a aussi montré ce que `VR-10` coûte, tel que le mainteneur l'avait prévu : un chunk que l'étage A coulait entier passe maintenant, et une ligne rendue de nulle part (« quitter la peine d'im- » pour « ui à nom: », page à 57 % de CER) passe le plancher 0,15 sans qu'aucune ligne OCR de la page ne la réclame. Ce n'est pas un défaut de garde — c'est la limite du plancher sur une page hors domaine, que le triage géométrique (`hans`, `H18`) écarte avant tout appel.

---

## Clos — déplacé dans `docs/history/`

- `AUDIT-2026-07-13.md` + `PLAN-CORRECTIONS.md` — 37 findings, exécutés intégralement.
- `PLAN-REMEDIATION-2026-07-15.md` — vagues 1-4 livrées ; seul reliquat `V4.5`,
  repris ici en `P3`.
- `PLAN-1.0-2026-07-15.md`, `ROADMAP_LIB_V3.md` — remplacés par ce document.
