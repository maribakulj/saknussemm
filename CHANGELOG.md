# Changelog

All notable changes to **saknussemm** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Nothing here has ever been released

Read before using the version headings below (`D4`).

**There are zero git tags and the package has never been published to an
index.** The `[0.9.0]`, `[0.9.0 initial scope]` and `[0.1.0a1]` sections are
dated development milestones, not releases: no artefact carrying those
version numbers exists anywhere. `docs/PLAN.md` schedules the first real tag
as `0.10.0` (`P2`), after a rehearsal on TestPyPI (`P1`).

That matters for one reason in particular. SemVer's promise not to break
things attaches to *released* versions, so the section that carries the whole
history of this library's API breaks — `[Unreleased]`, 81 entries — is the one
section SemVer declares non-binding. Nothing is owed to anybody yet, and that
is the honest state; the index below exists so the breaks are readable as a
list rather than found by scrolling.

### Breaking changes so far, in reverse order

Every one of these predates any release. They are listed to be *findable*,
not because a migration is owed.

| change | what it broke |
|---|---|
| **`LineStatus` gains `review_required`** | a consumer filtering on `status == "corrected"`, or matching exhaustively on the enum, no longer sees the lines the library corrected without being able to verify them. Deliberate — that is what the value is for — and reversible per run with `ReviewPolicy.silent()`. The delivered bytes are identical either way |
| **A divergent file is withheld, not fatal to the run** | `run()` no longer raises `ProjectionError` when an artefact does not carry its decisions. The file is absent from `corrected_files` and named on the new `CorrectionResult.undeliverable_files`; `write()` refuses the incomplete set unless passed `allow_partial=True`. Callers with `except ProjectionError` around `run()` now see a returned result instead |
| **The `[qe]` extra is gone** | `pip install saknussemm[qe]` and `saknussemm.integrations.qe`. The scorer moved to the bench repository on 2026-08-16: it needed onnxruntime and a 545 MB model no CI could fetch, so its suite skipped everywhere and the module sat outside the coverage gate. The `QEScorer` protocol stays — the injection point is public, the implementation is not |
| **The library is renamed `corrigenda` → `saknussemm`** | everything a caller writes: the distribution name, the import name, the extras (`saknussemm[qe]`, `saknussemm[vision]`), the error root `SaknussemmError`, the release tag prefix, and the `<softwareName>` the rewriter stamps into corrected files. The largest break in this list, and the cheapest: nothing has ever been published, so it is owed to nobody. Doing it after a release would have cost a major version and every consumer an edit |
| OCR-confidence invalidation is counted per line | the PAGE `format_losses` key `conf_dropped` is gone; its replacement counts lines, not attributes |
| `ProducerMetadata` replaces bare provider/model strings | producer identity |
| The producer seam takes `ProducerOptions`, not `RetryPolicy` | `EditProducer.produce()`'s signature |
| Generic vocabulary replaces the LLM-branded names | several exported names |
| `PipelineEventType` names only engine events | the observer's event vocabulary |
| Report v2: staged `LineOutcome` entries | the `CorrectionReport` JSON shape (`report_version` 1.0 → 2.0) |
| `run()` never mutates its input | callers reading results off the input manifest |
| Persistence left the engine surface | `output_writer` on the pipeline constructor |
| Page images are keyed by page, not by file | `run(page_images=…)` |
| `LineRef` — line identity is `(page_id, line_id)` | anything keyed on a bare `line_id` |
| Recoverability is an allowlist | providers raising raw transport exceptions |
| Parsers stamp identity | hand-built manifests |
| Fallback accounting counts LINES, not chunks | `CorrectionResult` counters |
| The two research knobs left the top-level surface | `from saknussemm import ConfidencePolicy, RoutingPolicy` |

The **top-level import surface** is provisional until `1.0.0`. It went from
95 accreted symbols to the computed 68 (`S3b`), then to 66 (`RM-04`). See
`docs/versioning.md`.

## [Unreleased]

### Added

- Les producteurs vision à alias (`CompositeVisionEditProducer`,
  `PageVisionEditProducer`) rendent une ligne vide à son texte source au
  lieu de la laisser au validateur. Leur prompt dit « rends son identifiant
  seul » pour une ligne illisible ; le modèle obéit, le validateur refuse le
  texte vide, et le chunk entier part en retries puis en descente puis en
  repli. Mesuré sur NewsEye : 29 retries sur 67, et 342 lignes rendues à
  l'OCR par chunks entiers (`VR-9`).

- `open_page(asset)` et `crop_region(..., source_image=…)` : la page est
  décodée **une fois par chunk** et le recadrage est converti, pas la page.
  Jusque-là chaque recadrage transposait et convertissait la page entière —
  deux copies par ligne, vingt lignes par chunk ; sur une page de presse de
  6 867 × 9 329 px, macOS a tué le run. Les octets de chaque recadrage sont
  identiques, donc les empreintes enregistrées tiennent (`VR-8`).

- **`with_corpus_notes(prompt, *notes)` et `CORPUS_NOTE_EARLY_MODERN_FRENCH`.**
  Le prompt générique ne sait pas quel siècle il corrige : à travers le
  pipeline sur OCR17+, `page_aligned` réécrivait `meritay-je` en
  `mériterais-je` et `vn` en `un` malgré la règle « ne modernise pas » —
  10,96 %, pire que ne rien faire (8,55 %). Une phrase de plus nommant
  l'époque et le ſ long : 6,71 %. La note s'ajoute comme règle numérotée à
  la suite du prompt de n'importe quel producteur et entre dans son
  empreinte de configuration (`VR-4`).

- `ChunkPlannerConfig(coalesce_blocks=True)` : à la granularité BLOCK, les
  groupes de régions consécutifs sont fusionnés en un chunk tant que les
  deux budgets tiennent. Défaut `False` (un chunk par groupe, comme avant).
  Mesuré à travers le pipeline sur OCR17+ : des fichiers PAGE à régions
  d'une ou deux lignes donnaient 105 chunks pour 251 lignes — 32 sur une
  seule page — et un producteur vision qui lit du contexte recevait des
  bandes de 2 ou 3 rangées (`VR-2`).

- `VisionEditProducer` lit le plafond d'images que son client déclare
  (`max_images_per_call` ou `MAX_IMAGES_PER_CALL`) quand l'hôte ne passe pas
  de `capabilities`. Mesuré à travers le pipeline : sans plafond déclaré, 19
  recadrages partaient, le fournisseur refusait le neuvième, et le moteur
  retentait puis redescendait au lieu de découper (`VR-3`).

- **`PageVisionEditProducer` : la page entière en une image, l'identité dans
  le texte.** C'est le levier de qualité mesuré (`hans`, H10/H12) et qui
  n'avait aucun chemin dans la bibliothèque : sur OCR17+, un recadrage par
  ligne lit à 6,4–6,7 %, une bande étiquetée à 6,25 %, la page en une image
  à 3,7–4,6 % — le modèle se sert de la typographie et de la langue autour
  d'une ligne pour la lire. Pas de géométrie (rien n'est recadré), une image
  JPEG bornée à `max_side` (1 024 px mesuré meilleur que 2 048), des alias
  opaques comme le composite, et le même chemin partagé après la réponse.
  À coupler avec `GuardConfig(attachment_scope="page")` (`VR-1`).

- **La marge de voisinage peut porter sur toute la page.**
  `GuardConfig(attachment_scope="page")` tient le garde 2 de `check_line`
  — « la correction ressemble plus à une autre ligne qu'à la sienne » —
  contre chaque ligne de la page et non plus contre les deux voisines, avec
  le code de refus `closer_to_another_line`. Le défaut reste `"adjacent"`.

  Pourquoi. Une ligne mal rattachée porte le texte d'une AUTRE ligne, et
  cette autre ligne n'est pas toujours voisine : un modèle qui supprime ou
  coupe une ligne décale toutes les suivantes, et un modèle à qui l'on
  montre une colonne la lit en travers. Mesuré sur 5 111 lignes de presse
  des années 1930 à vérité terrain humaine : les décalages se concentrent à
  ±1 mais vont jusqu'à ±15 ; la portée voisine en laissait passer 1 746, la
  portée page zéro. Sur 12 000 lignes de quatre corpus, avec les deux
  nombres inchangés (plancher 0,35, marge 0,15) : zéro ligne mal rattachée.
  Le prix monte avec le bruit de la source — 5 % de refus sur un OCR propre,
  la moitié des corrections à 60 % d'erreur simulée.

  `attachment_twin_similarity` (défaut `None`) exempte de la marge les
  lignes jumelles — deux didascalies nommant le même personnage — entre
  lesquelles un échange est sans dommage et la marge impossible à tenir. À
  0,85 sur OCR17+, il rend la moitié des refus (CER 4,58 → 4,31 %) sans
  laisser passer une ligne ; dessiné après avoir vu les échecs, il reste une
  option.

- **`CompositeVisionEditProducer` : une seule image par bloc, l'identité
  peinte dedans.** Chaque ligne est recadrée séparément, les recadrages
  sont empilés en une bande (`compose_line_strip`), chaque rangée précédée
  de son alias opaque peint en rouge (`line_aliases`), et le JSON porte les
  mêmes alias. `max_lines` (20) est déclaré comme `max_images` : le batcher
  existant borne ainsi le nombre de rangées sans code nouveau.

  Pourquoi. Le modèle apparie par l'image, pas par le texte : avec les
  identifiants dans le texte seulement, sur la même presse des années 1930,
  il transcrit le recadrage de haut en bas et remplit les identifiants dans
  l'ordre — 1 746 lignes sous le mauvais identifiant. Peints à côté de
  l'encre, en bandes de 20 : 84, et un CER de 39 % à 6,4 % sans garde. Les
  entiers ne conviennent pas comme alias : après une suppression, le modèle
  renumérote ; un jeton opaque, il le recopie.

- `PageLLMEditProducer` aplatit tout séparateur de ligne dans une ligne
  rendue avant de l'apparier. Mesuré sur OCR17+ à travers le pipeline : un
  U+2028 dans une ligne rendue faisait, sous `"characters"`, refuser la
  page entière par le validateur, retenter quatre fois, redescendre d'un
  cran et finir en `all_attempts_exhausted` sur ses 19 lignes.

- `PageLLMEditProducer(line_matching="characters")` documente qu'il ne
  vérifie pas l'hypothèse d'ordre dont il dépend et ne doit jamais tourner
  sans `attachment_scope="page"` : sur un flux qui n'est plus la page, il
  découpe quand même — 46 % de CER mesuré.

- **Le mode `page_aligned` peut retrouver l'identité de ligne au CARACTÈRE,
  pas seulement par jetons.** `core.page_alignment.reproject_page_lines`
  recoupe le flux rendu sur les frontières des lignes source, et
  `PageLLMEditProducer(..., line_matching="characters")` le sélectionne. Le
  défaut reste `"jaccard"` : la surface livrée ne change pas.

  Pourquoi. `align_page_lines` compare des **jetons**, et une post-correction
  qui scinde un mot — `Maisiepenfois` devenant `Mais ie penſois` — ne partage
  aucun jeton avec sa source. Les lignes qui profitent le plus de la
  correction sont donc exactement celles qu'il refuse. Mesuré sur 9 pages
  d'OCR17+ à vérité terrain humaine, correction de page entière par VLM :
  **43 lignes sur 251 non appariées**, et l'écart à la vérité terrain
  retombe de **3,7 % à 6,4 %**.

  Ce n'était pas un mauvais choix. Le Jaccard a été validé contre une copie
  **corrompue**, où les jetons survivent ; il devient faux contre une copie
  **corrigée**, où ils ne survivent pas.

  La contrepartie est mesurée aussi : le recollage au caractère suppose un
  flux **dans l'ordre** et ne refuse jamais. Sur des sorties délibérément
  mutées il passe de 3,7 % à 10,5 % (deux lignes échangées) là où le Jaccard
  tient à 7,1 %. Ce qui le rattrape existe déjà — la garde
  `min_source_similarity` refuse une ligne trop éloignée de sa source : avec
  elle, les mêmes mutations rendent **4,3 %**, mieux que les deux stratégies
  seules, et **zéro refus** sur une sortie normale.

  Le défaut ne bouge pas parce que la mesure porte sur neuf pages ; changer
  le comportement livré est un arbitrage de mainteneur.

### Fixed

- **La géométrie des tokens ALTO ne dépend plus de la version de Python.**
  `_compute_geometry` pesait ses tokens en flottants — `0.6` par caractère
  d'espace — et sommait ces poids avec `sum()`. CPython 3.12 a donné à `sum()`
  la sommation compensée de Neumaier : les mêmes dix-sept tokens pèsent
  `48.80000000000001` sur 3.11 et `48.8` sur 3.12, donc **le fichier livré
  différait selon l'interpréteur**. Les poids sont des entiers depuis, en
  dixièmes de caractère, et chaque frontière est arrondie depuis une division
  exacte plutôt que depuis un flottant qui s'accumule.

  Deux empreintes d'octets bougent, classées par TextLine avant régénération :
  1 ligne sur 33 (`Descartes…_alto4.xml`) et 1 sur 1 145
  (`bpt6k2324031_p0002.alto.xml`), géométrie seule, deux éléments décalés d'un
  pixel, aucune dérive de texte ni de structure, somme des `WIDTH` inchangée.
  La nouvelle empreinte 3.11 est exactement celle que 3.12 produisait déjà.
  Les empreintes de `test_byte_parity_corpus.py`, `test_byte_parity_page_corpus.py`
  et `test_rewriter_byte_stability.py` ne bougent pas : 81 des 83 assertions
  d'octets du dépôt sont indifférentes au correctif.

  Trouvé par `tests/test_byte_parity_all_fixtures.py`, ajouté par la vague
  `RS` : aucune empreinte préexistante ne tombait sur un arrondi à la
  demi-unité.

### Added

- **`LineStatus.REVIEW_REQUIRED` — la bibliothèque dit ce qu'elle ne peut pas
  établir** (critère `V4` du plan). Une quatrième valeur de statut terminal,
  distincte de `corrected` / `fallback` / `failed` : la correction est
  **livrée** — mêmes octets, même opération dans le script d'édition — et le
  run déclare n'avoir aucun moyen de vérifier qu'elle est juste.

  Pourquoi : les gardes de l'étage C comparent des caractères. Sur douze
  contre-exemples passés dans la vraie `check_line`, les douze sont acceptés
  aux deux seuils — négation supprimée 0,8955, date changée 0,9388, montant
  tronqué 0,9643, ligne voisine recopiée mot pour mot 0,8852. Aucun réglage
  ne ferme cette famille ; ranger ces lignes sous `corrected` faisait
  affirmer « j'ai vérifié » là où c'est faux.

  Ce qui arrive avec : `ReviewPolicy` (exporté au niveau supérieur, §15),
  `saknussemm.core.decide.REVIEW_REASON_CODES` (six codes, vocabulaire clos
  dès l'écriture), `DecisionSet.review_lines` / `review_reason_counts()`,
  `CorrectionResult.review_lines` / `review_reasons`,
  `DecisionStage.review_reasons` sur le rapport (additif — pas de bump de
  `report_version`), `LineTrace.review_reasons`,
  `LineDecision.carries_a_correction`.

  **Aucun octet livré ne change** : la passe de renvoi n'écrit pas de texte,
  ce que `tests/test_review_pass.py` vérifie en comparant les fichiers de
  deux runs, l'un avec les règles et l'autre sans.

  Les règles sont conservatrices et mesurées : sur le corpus de vérité
  terrain, **11 des 47 lignes modifiées** sont renvoyées (23 %) —
  8 `proper_noun_changed`, 3 `negation_changed`, 2 `digits_changed`.
  Trois règles du programme d'origine ne sont **pas** implémentées et
  `src/saknussemm/core/review.py` dit pourquoi chacune : « ligne propre
  modifiée » (écrite, mesurée à 30 des 47 lignes et retirée — sans lexique
  elle attrapait de simples corrections `f` → `ſ`), le désaccord entre deux
  producteurs (aucun run n'en interroge deux sur la même ligne), et la
  confiance non calibrée sous seuil.
- `GuardConfig.text()` — le profil d'un producteur de texte, nommé face à
  `GuardConfig.vision()`. Mêmes valeurs que `GuardConfig()`.
- `saknussemm.core.decide.FALLBACK_REASON_CODES` — le vocabulaire clos des
  vingt raisons de repli, jusqu'ici dispersé en littéraux sur huit modules.

### Changed

- **`GuardConfig.vision()` tient la marge de voisinage contre toute la page**
  (`attachment_scope="page"`), et garde son plancher à 0,15. Les deux
  réglages sont une seule décision : le plancher bas seul laissait passer 64
  lignes échangées sur 5 111 lignes de presse (et 1 sur HIPE) ; avec la
  marge de page, aucune sur les corpus mesurés, à 4,19 % contre 4,39 % pour
  le plancher 0,35 sur OCR17+ (`VR-7`). L'empreinte du profil change ;
  `GuardConfig()` ne bouge pas.

- **Une paire de césure que l'étage A refuse encore au dernier essai retombe
  seule, et le reste du chunk passe** (`pair_drift_fallback`). Jusque-là la
  réponse entière était refusée, retentée, redécoupée, puis rendue à l'OCR :
  sur la presse NewsEye, 64 chunks entiers sur une seule page pour des
  secondes moitiés en bouillie rendues en un mot lisible, 180 lignes qui
  n'avaient rien à voir avec la paire. Mesuré : ces lignes, corrigées par
  un autre bras, sont aussi bonnes que les autres (72 % améliorées, 18 %
  dégradées — le taux général). Les essais 1 et 2 restent ; seule la fin
  change, et les 18 autres lignes passent ensuite par tous les gardes de
  l'étage C comme n'importe quelle ligne (`VR-10`).

- **Un membre de paire de césure que l'étage B a accepté passe désormais le
  plancher et la marge de l'étage C** (`VR-11`). La réconciliation juge les
  deux moitiés d'un mot coupé l'une contre l'autre — le texte a-t-il migré
  d'une ligne à l'autre — et rien d'autre ; un membre réconcilié sautait
  ensuite `check_line` entièrement. Vu au run de vérification de `VR-10`
  sur NewsEye : une PART1 rendue « ce que notre grand mor- » sous une source
  « au. nt comme orateur, 'une situation in- », livrée `corrected` alors que
  la page tenait une ligne OCR « ce que notre grand mo » — rejouée hors
  run, `check_line` la refuse à 0,95 contre 0,31. Le garde d'absorption
  reste hors jeu sur ces membres (l'étage B possède la coupe du mot) ; un
  membre refusé entraîne son unité (`hyphen_unit_fallback`, ADR-010). Deux
  empreintes d'octets bougent (`X0000002`, `0253902003`, scénario
  `drift`) : une unité de césure dont la bouillie traversait, rendue à la
  source. `check_line` gagne `absorption: bool = True`.

- **Une ligne corrigée peut désormais rapporter `review_required` plutôt que
  `corrected`.** C'est la seule rupture que `LineStatus.REVIEW_REQUIRED`
  introduit, et elle est délibérée : un consommateur qui filtre sur
  `status == "corrected"` cesse de balayer avec lui les lignes que la
  bibliothèque n'a pas pu vérifier — ce qui est la raison d'être de la
  valeur, pas son coût. `ReviewPolicy.silent()` rend l'ancien comportement
  exactement. La surface publique passe de 67 à **68 symboles**
  (`ReviewPolicy`).
- **`docs/versioning.md` sort les VALEURS des seuils de politique du contrat
  SemVer** ; leurs NOMS y restent. Les gardes ne sont pas calibrées — le plan
  et `GuardConfig.vision()` le disent tous deux — et figer des nombres
  provisoires ferait de leur recalibrage un changement cassant.
- `VisionEditProducer` passe de `saknussemm.integrations.vision` à
  `saknussemm.producers.vision`. Le module n'a jamais été réexporté au niveau
  du paquet et la surface publique ne bouge pas ; un consommateur qui
  l'importait par son chemin de module doit changer cette ligne.

### Changed — BREAKING

- **Les deux voies d'édition affrontent les mêmes gardes de dérive, et le
  mot-frontière d'une `PART2` ne peut plus être effacé** (`E5b`, `E6b`).

  `E4`/`E5` étaient réservées aux spans, donc la voie ligne entière — celle du
  producteur par défaut — n'en voyait aucune : le même texte obtenait un verdict
  différent selon le vocabulaire qui l'avait proposé. Et le mot qui continue un
  mot coupé n'était protégé par rien : effacé, la ligne survit donc le contrôle
  de non-vacuité est satisfait, et la paire se relit `plu-` + `et le reste`.

  Les deux règles ont été choisies **après mesure sur un vrai run**
  `mistral-small-latest` (3 135 lignes, 1 796 propositions), pas avant.

  Pour `E5b`, la règle est « effacer sans remplacement », pas « trop changer » :
  sur 1 433 lignes `PART2`/`BOTH`, le mot-frontière est remplacé par du
  méconnaissable **25 %** du temps, et ce sont de bonnes corrections — c'est
  l'endroit le plus dégradé de la ligne, souvent réduit à un caractère isolé.
  Un seuil de similarité refuserait **23–31 %** des corrections réelles ;
  refuser le seul effacement en coûte **0**.

  Pour `E6b`, `E4` refuse **0** proposition (médiane 20 caractères changés,
  budget 200) et `E5` en refuse **205** dont **204 déjà refusées** en aval —
  elle refuse plus tôt et nomme pourquoi, elle ne refuse pas plus. La 205ᵉ a
  fait **affiner `E5`** : une espace avant la marque n'est refusée que si la
  correction l'a *introduite*, parce que sur ces 205 elle est héritée de la
  source 1 fois et introduite 0 fois. Rejoué sur les données du run :
  **204 refusées, 0 verdict changé.**

  Deux nouveaux codes d'`EditRejection` (`e5_boundary_word`, plus `e4_line_budget`
  et `e5_hyphen` désormais atteignables sur la voie ligne entière), additifs.

- **Une édition sur une ligne de contexte est refusée, plus jetée en silence.**
  `E1` avait deux clauses et la première était **inatteignable** : `attempt.py`
  passait toutes les lignes du chunk comme cibles, donc « hors ensemble » n'était
  vrai que là où « inconnue » l'était déjà. Elle passe maintenant les vraies
  cibles, et le refus porte son propre code, `e1_context_line` — quatorzième
  code de `EditRejection`, additif.

  Le texte corrigé est inchangé : une édition de contexte était déjà écartée
  plus bas par le filtrage des cibles, et la suite entière est restée verte.
  Ce qui change est qu'un opérateur peut désormais voir qu'un producteur a
  proposé quelque chose que le moteur a décliné, et laquelle des deux
  accusations : un identifiant inconnu est un producteur qui **invente** une
  ligne, un identifiant connu hors cibles est un producteur qui répond à une
  question qu'on ne lui a pas posée. Le second est le cas courant — un payload
  ne marque pas ses cibles — et le rapporter comme « inconnu » le rendait
  illisible.

- **A divergent file is withheld, not fatal to the run — surface 67 → 68.**
  `run()` used to raise `ProjectionError` the moment one source file's rewritten
  artefact diverged from what the run decided. Correct as a refusal, ruinous as
  a blast radius: a volume of 300 pages was lost for one line, and the report
  went with it — every trace, every fidelity level, every decision — so the
  operator was left holding one exception message about one line.

  The refusal itself does not move. A divergent artefact is still never a
  deliverable. What moves is its scope: the file is **absent** from
  `corrected_files` — never present in a doubtful version — and named on
  `CorrectionResult.undeliverable_files` with the reason, mirrored onto
  `CorrectionReport.undeliverable_files` for the persisted artefact.

  Withholding alone would have traded a loud failure for a quiet one: a caller
  looping over `corrected_files` would persist 299 of 300 pages and report
  success. So the loudness moves to the one door that puts bytes on disk —
  `CorrectionResult.write` **refuses** an incomplete set, and `allow_partial=True`
  is the caller saying, in reviewed code, that it read the list and accepts the
  subset.

  Measured before deciding: the argument for keeping the total refusal was that
  a word broken across two files would be delivered half-corrected. Over the two
  real Gallica issues — 12 files, 8 787 lines, 1 583 hyphen units — **zero**
  cross the boundary between two files, on a detector verified against a
  fabricated positive. The mechanism exists; on real volumes it is rare enough
  that it does not pay for losing everything else.

- **A refused edit is visible in the report (`A2b`) — surface 66 → 67.**
  `CorrectionReport.edit_rejections` names each refused op by page, line, op and
  reason code; `RefusedEdit` joins the top-level surface because it is now
  reachable from a returned type, the same reason `HyphenSplit` is there. The
  field is optional and additive, so `CORRECTION_REPORT_VERSION` does not move.
  Nothing is refused that was not refused before. What changes is that it can
  be counted: `EditRejection` had thirteen reason codes and no consumer outside
  the tests, so a line whose only op was refused reported `corrected` with no
  reason and nothing counted the refusal. The refusal rate of `E1`–`E5` was not
  unmeasured but **unmeasurable** — and a consumer loosening
  `min_source_similarity` on a degraded corpus could measure no difference
  whatever the change did. Sorted rather than accumulated in execution order,
  so two runs over one document produce the same report.

- **The published edit script no longer carries ops the guards refused
  (`A2c`).** `core/report.py` documents that script as the one the run
  *actually applied*, never carrying an op for a line reverted to OCR — because
  a consumer replaying it would otherwise diverge from the pipeline's own
  corrected XML. Measured: delivered `'Le peuple att-'`, published the refused
  `replace_span`, replayed to `'Le peuple -'`. `_script_to_raw` applied the
  span ops and discarded the refusals; the uncovered line was then filled with
  its canonical text, so the report saw `produced == final` and concluded the
  op had survived every guard. A consumer that replays a published script gets
  fewer ops than before, and the same document as the run delivered.

- **A crop is refused when its scan is no longer the one attested (`A1g`).**
  `build_image_asset` hashes what it read; `crop_region` reopened the path and
  never checked. `RunProvenance.image_digests` promises that the digest plus
  the coordinates make every crop reproducible, and measured before the change
  the report attested `e8b42963fb4dbae2` while the file actually opened hashed
  to `ec6297512ddb3c8d` — two different crops, nothing in the artefact able to
  tell them apart. An asset without a digest is still read as-is: the field is
  optional and a caller may legitimately have built one without hashing.
  Also non-breaking, and the reason the check is affordable: the producer
  crops every line of a chunk, so the file was being read once **per line**.
  It is now read and verified once per chunk, and `crop_region` takes an
  optional `source_bytes` for callers that already hold them.

- **A manifest carries its sources' digests, and a run refuses a file that
  changed (`A1f`).** `DocumentManifest.source_digests` is additive; the refusal
  is what is new, and it fires at preflight — before a producer call is spent.
  Measured before the change, with the name→path bindings of a two-file
  document swapped: the run **succeeded** and delivered, under the first name,
  **the second file's tree, geometry and page ids** carrying the first file's
  decided text — the second file's own text destroyed. `ADR-007` makes
  `line_id` unique only within a file, so both files normally carry `TL1…TLn`
  and every lookup matched. Separately, a file replaced under a run projected
  one version's decisions into another version's markup, line by line.
  The projection invariant cannot see either, structurally: it compares the
  delivered artefact to the decisions, and the artefact was *made* by writing
  those decisions into whatever tree was there.
  Corollary — `RunProvenance.source_digests` now attests the bytes actually
  parsed. It used to hash a **third** read taken after the render, so a
  document that changed mid-run was attested by a digest of bytes nothing had
  ever parsed, and its edit script carried preconditions from one version
  beside a digest of another: replayed against the file it names, it failed
  its own preconditions.

- **Three silent acceptances became refusals (`A1d`, `A1e`).** Each was a case
  where the library could not do what it was asked and reported success
  anyway; a call that used to return now raises. Measured before the change:
  - `run()` with a `source_files` mapping that does not describe the same
    document as the manifest **succeeded**. A manifest parsed from `a.xml` +
    `b.xml` run with only `a.xml` supplied counted both files' lines in
    `report.total_lines` and one file's in `projection_fidelity`; half the
    decided lines existed in no artefact. Now `ConfigurationError` at
    preflight. An empty mapping stays legal — that is the decide-only run.
  - A source removed, truncated or made unreadable between parse and render
    escaped as `FileNotFoundError` / `XMLSyntaxError` / `PermissionError`. The
    two rewriter reads were the only `read_source_tree` callers outside the
    §8.4 classification. Now `ParseError`, like every other read.
  - `result.write()` on two keys that flatten to one filename **returned three
    paths and left two files**, the second overwriting the first. Now
    `ConfigurationError`, raised before anything is written. `Path(name).name`
    is unchanged: flattening remains a deliberate path-traversal guard.

- **`ConfidencePolicy` and `RoutingPolicy` leave the top-level surface: 68 →
  66 (`RM-04`).** Both are constructor knobs of `CorrectionPipeline` whose
  defaults do nothing. `ConfidencePolicy()` is `mode="drop"` — no confidence
  is computed, and the third mode, `write_wc`, still *raises* at
  construction. `RoutingPolicy()` has both bounds at `None` — every line goes
  to the producer, so a default run is byte-identical with and without it.
  They belong to the vision/QE research programme that `docs/PLAN.md`
  suspends under its feature freeze, and a top-level export reads as an
  invitation: it says "this is ready", when what is true is "this is written,
  frozen, and executed by no default run".

  **Migration is one import line.** Both stay exactly where they are —
  `from saknussemm.core.schemas import ConfidencePolicy`,
  `from saknussemm.core.quality import RoutingPolicy` — which is the demotion
  door `docs/versioning.md` documents for symbols that leave `__all__`
  without leaving the library. Nothing is deleted, no behaviour changes, and
  the pipeline still accepts both arguments. `tests/test_research_boundary.py`
  pins those import paths because the four calibration scripts behind the
  `M*` measurement programme use them.

  What deliberately did NOT go, because the distinction is `I4`: `ImageAsset`,
  `ImageRef`, `ImageTransform` and `PageImage` stay on the surface. They are
  not vision code — they are what the pixel-blind core CARRIES for a producer
  that asked for pixels, and never opens. A custom `EditProducer` declaring
  `wants_image` is handed one, so they sit inside the producer seam's closure
  and removing them would break the promise `S3b` computed the surface from.

- **The top-level surface is 95 → 68 symbols, and it is now computed
  (`S3b`).** `saknussemm.__all__` had reached 95 by accretion: each name was
  added because something needed it that day, and nothing ever took one
  away. It is now the transitive closure of two promises and nothing else —
  what `load`/`correct`/`correct_sync` return, so a caller can type the value
  it was handed; and what a custom `EditProducer` must name to implement the
  protocol the README advertises in its first sentence. Both closures are
  reproducible by walking type annotations, and the snapshot test states how.

  **Nothing was deleted.** All 33 demoted symbols stay importable from their
  own module, which `docs/versioning.md` documents as the other supported
  door and which the repository itself uses 788 times against 56:

  | was | now |
  |---|---|
  | `from saknussemm import RulesProducer, SubstitutionRule, default_french_ocr_rules` | `from saknussemm.producers.rules import …` |
  | `from saknussemm import LLMEditProducer` | `from saknussemm.producers.llm_edit import …` |
  | `from saknussemm import build_document_manifest, parse_alto_file, rewrite_alto_file, extract_output_texts` | `from saknussemm.formats.alto.parser` / `.rewriter import …` |
  | `from saknussemm import parse_page_file, rewrite_page_file` | `from saknussemm.formats.page.parser` / `.rewriter import …` |
  | `from saknussemm import AltoFormatAdapter, PageFormatAdapter` | `from saknussemm.formats.alto.adapter` / `page.adapter import …` |
  | `from saknussemm import apply_edit_script, normalize_anchor, line_digest, EditResult, EditRejection` | `from saknussemm.core.editing import …` |
  | `from saknussemm import BaseProvider, ModelCatalog, StructuredCompletionClient, require_capabilities, require_page_images` | `from saknussemm.core.protocols import …` |
  | `from saknussemm import QEScorer, HeuristicQEScorer, RoutingDecision, route_line` | `from saknussemm.core.quality import …` |
  | `from saknussemm import ConfidenceScorer, HeuristicScorer` | `from saknussemm.core.confidence import …` |
  | `from saknussemm import ModelInfo, ModelCapabilities, LineProposal` | `from saknussemm.core.schemas import …` |
  | `from saknussemm import SYSTEM_PROMPT, OUTPUT_JSON_SCHEMA` | `from saknussemm.integrations.llm import …` |

  Six names were ADDED, because both closures reach them and a caller could
  not import them: `Coords`, `HyphenSplit`, `ProjectionFidelity`,
  `ReconcileMetrics` (reachable from the result), plus `CorrectionRequest`
  and `LineGeometry` (reachable from the producer protocol). Those four
  holes are the defect this item exists to close — a value you are handed
  whose type you cannot name.

  What is deliberately left at its module path, and why: the format-adapter
  seam (`FormatAdapter`, `RewriteResult`, `RewriteMetrics`, `AlignedPair`,
  `TokenAlignment`). Injecting an adapter is an optional argument most
  callers never pass, and those types are the rewriter's internal accounting
  vocabulary — `R5`, `R8` and `L8` all moved them this year. Freezing them
  under SemVer at 1.0 would promise a stability nothing supports.

### Added

- **`Coords` and `DocumentManifest` are frozen (`S4`, partial).** ADR-011
  slice E made `run()` work on a deep copy so a caller's document is never
  written; that guarantee held by the discipline of one call site, and now
  holds by the type. Measured before changing anything: those two carry zero
  assignment sites in `src/`. `LineManifest` carries 246 — it IS the run's
  working state — and `PageManifest`/`BlockManifest` are written once each by
  the page-id disambiguation, so they stay mutable until `S4` introduces a
  distinct working type. A hand-built manifest is now made with
  `model_copy(update={"source_format": None})` rather than by un-stamping a
  parsed one.

- **A `typecheck` extra, so `mypy --strict` means one thing.** `lxml-stubs` was
  installed by hand in the CI workflow and declared in no manifest, and without
  it mypy types `_Element.attrib` as `Any` — a local strict run checked less
  than the gate it was meant to reproduce, silently. `pip install
  saknussemm[typecheck]` now installs the pinned mypy plus the stubs, and the
  CI job installs the extra instead of carrying its own pin.

- **`CorrectionReport.hyphen_splits` — the engine's one deliberately
  destructive operation is no longer invisible (R6).** When a hyphen chain is
  longer than `max_lines_per_request` the LINE planner severs a forward link so
  the cut pair cannot straddle two requests (`split_forward_link`, ADR-010).
  The record existed — on the `ChunkPlan`, an internal planning artefact nobody
  outside the planner sees — and nothing on the report covered it: the cut
  resets the tail's role to `NONE`, so `unpaired_breaks` (which counts lines
  that still *want* a partner) is blind to it by construction; both sides keep
  their OCR text, so it is not a fallback; nothing leaves the markup, so it is
  not a `format_loss`. What a host is handed is a delivered line whose text ends
  mid-word and which declares no break at all.
  Measured while pinning it: a split can only happen at LINE granularity, which
  the planner's auto-selection never reaches (PAGE → BLOCK → WINDOW) — the one
  real path there is the granularity descent after a failed chunk. Rare, and now
  reported. Optional and additive: `None` when nothing was cut, no
  `report_version` bump.

### Fixed

- **No chunk boundary separates a still-linked pair any more (L7).** Three
  planner defects turned out to be one: asking "is my partner the NEXT line?"
  instead of "WHERE is my partner?". A linked pair has exactly two legitimate
  outcomes at planning time — together in one chunk, or severed with a
  `HyphenSplit` on the plan — and a pair that is neither is a silent hole,
  because the validator skips a pair that is not wholly in-chunk and the
  reconciler could write across the boundary.
  The previous release's own blank-line fix widened the hole: once the linker
  stepped over blanks, a pair linked `L0 → L2` failed the adjacency test, the
  chain stopped, the two members landed in different chunks and the link stayed
  live with nothing recorded.
  `_plan_line` now follows the link (an id→position *lookup*, not a resolver),
  carries the lines in between rather than leaving them out of every chunk, and
  severs on "my partner is not in my chunk" instead of "the cap cut me" — those
  coincided only while adjacency was required. A partner off-page (a cross-page
  pair) or behind is neither followed nor severed.
  `_try_window` had the same root through `should_stay_in_same_chunk`, which was
  wrong in *two* directions: it could not see a link leaving from an earlier
  line in the window, nor a non-adjacent partner. Replaced by `_unit_reach`,
  which asks how far the window must reach to hold every link that leaves it.
  The predicate had one production caller and is now **retired** — it was the
  third formulation of "who is my partner?" that S1 left standing.
  `_split_for_image_cap` was asking a different question of the wrong helper.
  `_page_local_units` answers "is this the WHOLE unit?" and returns nothing when
  it is not, which is right for the router (escalating half a unit would split
  it, so leaving it alone keeps it together). The batcher has no "leave it
  alone" — it slices one chunk into calls — so given nothing it treated each
  member as a singleton and could put a pair in two calls. Two shapes reached
  it: a group whose last pointer dangles, and one continuing onto another page.
  New `_units_visible_on_page`: same shared derivation, no pointer reads, a
  different projection — the members present, complete or not.
  Also measured: the third item on the list, "the granularity descent does not
  repatriate non-target partners", is not an independent defect. Window
  targeting already forces both members of a pair into one window; a sweep of
  3708 chunks over 7 page shapes × a config grid found 45 violations, **all** of
  them the non-adjacent-pair shape, and zero after the window fix.
- **The hyphen guards know the whole break-mark repertoire, not just `-`
  (L5).** `HYPHEN_CHARS` has six members and the parsers use all of them, so a
  line can legitimately be a PART1 by ending in `⸗` or `¬` — yet five guard
  sites tested the ASCII hyphen alone. Measured over the 1711 ALTO/PAGE lines of
  `examples/` and `corpus/`: of 363 hyphenated lines, 331 end in `-`, **24 in
  `⸗` and 8 in `¬`**. 32 lines, 8.8%, fell outside every one of those checks —
  and it is not a corner case, `corpus/37-GT-BNL` is Fraktur ground truth whose
  break mark is `⸗`.
  Three real consequences, each with the test that fails before the fix: the
  orphan guard did not pull back a line whose correction dropped a `⸗`, so the
  delivered line no longer said the word continues; the PART1 growth guard
  measured the mark as part of the word, and since its threshold is a character
  count (default 3) a 4-character word completion read as 3 and was waved
  through; the fusion check compared against a last word with the mark still
  glued on, so a model that completed the word *and* kept the mark passed
  validation with PART2's text already migrated up.
  Two derived predicates, `ends_with_break_mark` and
  `strip_trailing_break_marks`, in `pairing.py` — the repertoire's only home.
  The first deliberately omits `trailing_hyphen_char`'s alphabetic-character
  requirement: its callers already know the line breaks a word, and re-checking
  would un-guard an explicitly marked line that happens to end in a digit.
- **An empty line is skipped over when pairing, not treated as a partner
  (L5).** `link_hyphen_pairs` took `lines[i + 1]`, so a blank line between a
  PART1 and its real continuation became the PART2: it holds no text, nothing
  reconciles, the pair-drift guards never run, and the actual continuation is
  left unlinked. Same consequence as the empty-*page* defect one scale down, and
  the same sentence rules it — a line that carries no text can say nothing about
  a word that spans it; it is a fact about the scan, not about the sentence.
  Applied to both walks from one definition, which also closes the
  `lines[-1]`/`lines[0]` facet of the cross-page walk: a blank at the foot of a
  page or the head of the next hid a word spanning the seam. Latent on this
  repo's corpora (0 empty lines in 1711), so it ships with eleven tests rather
  than a measurement.
- **`format_losses is None` no longer reads as "the run lost nothing" (R8).**
  A run that flattened a tab into an ordinary space reports
  `format_losses: None` and `projection_fidelity: {"normalized": 1}`. The loss
  was already counted — aggregated on `projection_fidelity`, attributed per line
  on `ProjectionStage.fidelity` — so what needed fixing was the claim around it,
  and the contract now says in all three places that this field counts losses of
  MARKUP granularity and that a flattened character is a loss of TEXT graded on
  the fidelity scale. Both fields have to be read to audit a run.
  Deliberately NOT mirrored as a second `format_losses` key: it would agree with
  `projection_fidelity["normalized"]` on every run by construction, and two
  accounting sites for one event are free to drift apart — which is what R1 was.
  The same reasoning that settled R4's unit settles this.
- **`LossPolicy(strict=True)` documents that it is a no-op on ALTO (R7).**
  `word_count` is populated by the PAGE parser alone, so the gate has no input
  on ALTO and a host that sets `strict=True` gets the default behaviour,
  silently. The docstring says so outright now, and says the part that actually
  matters: this is not "an ALTO rewrite loses nothing". A word-count-changing
  correction rebuilds the line and drops `TAGREFS`/`language`/vendor attributes
  plus the `STYLE` of any unmatched `String` — reported, and gated by no mode.
  Arming the gate for ALTO would change delivered output and needs a measured
  threshold, not a flag flipped in passing, so the restriction is documented and
  pinned by tests instead of discovered by a host whose gate never fired.
- **An emptied line reports the styles it loses (R2).** The ALTO rebuild has
  two exits. A correction that empties the line returns before any token
  alignment happens — there are no target tokens to align against — and that
  exit counted no `STYLE`/`STYLEREFS` at all, though nothing matched means
  every one of them went. 56 lines of the repo's ALTO corpora carry those
  attributes. Both exits now call one accounting function; a second inline copy
  is exactly how R1's phantom counts came about.
- **A dropped `<HYP>` element is counted (R3) — and the item was narrower than
  stated.** "A PART2 line's `<HYP>` removed with no counter" evokes a
  continuation line that also ends on a break mark; that line is not PART2. The
  parser reads the trailing mark as a forward break, classifies it `BOTH`, and
  the HYP is re-emitted — nothing is lost and nothing needs counting. The
  reachable shape is a `<HYP>` that is **not** line-terminal: ALTO does not
  define it, the parser tolerates it, the role stays PART2 and the element went
  silently. Now `hyp_elements_removed`. What goes is the **element** — its
  geometry and its standing as markup — not the mark, whose character is
  already in the reconstructed text and comes back inside a rebuilt `String`'s
  CONTENT; both halves are asserted so nobody "fixes" this by re-synthesising a
  HYP that would double the mark. 0 of the 1711 ALTO lines in `examples/` and
  `corpus/` have the shape, so this pins a latent path rather than a measured
  one. The key deliberately avoids the `*_dropped` suffix: in this vocabulary
  that suffix claims a `String` attribute, and the differential invariant reads
  it as one.

### Changed

- **`word_order_suspected` is no longer counted as a loss (R5).** The ALTO
  rewriter's alignment flag rode inside the loss dictionary, so any consumer
  summing `format_losses` added a non-event to the total: nothing left the
  markup, the alignment simply could not vouch for the word order it was handed.
  It now travels on its own channel — `RewriteResult.word_order_suspected`
  (line ids) → `ProjectionStage.word_order_suspected` (a per-line flag). The
  behaviour is unchanged: flagged, never acted on, because lines never merge and
  words never move. `format_losses` no longer carries the key.
- **`ProjectionFidelity` gains `source_spelling`: `exact` was untrue on 115
  lines of the repo's own BnF fixture (L8).** `exact` promises the artefact
  says the decision *character for character*. 115 of `examples/X0000002.xml`'s
  566 lines carry their break mark as U+00AD SOFT HYPHEN inside `<HYP>`; the
  reconstruction reads it back as `-` (deliberately — a soft hyphen must not
  reach a CONTENT attribute, and those lines need the collapse to pair at all),
  the rewrite re-emits the source element untouched, and the run graded all 115
  `exact`.
  It could not have graded them anything else. The collapse runs on **both**
  sides of the projection comparison and compares equal to itself — the same
  blindness that hid the break-mark doubling. So the fix is not a stricter
  invariant but a second reading: `RewriteResult.texts_verbatim` walks the same
  tree with the substitution table off, and a line whose two readings differ
  grades `source_spelling`.
  The new level sits **between** `exact` and `token_equivalent`, and the
  ordering is the claim: nothing is lost here — the file is *more* specific than
  the decision — whereas a collapsed whitespace run is gone from the file for
  good. Measured after the fix on that fixture: 451 `exact`, 115
  `source_spelling`, 0 `normalized`, and the 115 are exactly the U+00AD lines
  (pinned by set equality, not by count).
  PAGE substitutes nothing on read (NFC and strip only) and ships an empty
  `texts_verbatim` — asserted rather than assumed: every line's logical text
  must be findable character for character in the delivered bytes.
  The other half of L8 needed no change: `preserve_break_char` runs before
  decisions materialise and `ProposalStage.output_text` keeps the producer's raw
  text, so a forced source hyphen is already visible in the report as proposal
  vs decision.

- **OCR confidence invalidation is now reported, per line, by both formats
  (R4).** When a correction changes a word, the source engine's confidence in
  that word stops being a fact about the output, so ALTO drops `WC`/`CC` and
  PAGE drops `@conf`. ALTO said nothing about it; PAGE counted it as
  `conf_dropped`, once per `@conf`. Both are now one key,
  `confidence_invalidated`, counted **once per line**.
  The unit was the whole decision. Per occurrence it fires 3339 times on one
  real 566-line page — a number that tracks how wordy a line is rather than
  anything an archive acts on, and that would drown the three-digit counters
  beside it. Per line it says the fact: 566 lines lost their confidence on the
  slow path, 492 on the fast one. That gap is the point — the fast path removes
  `WC` only from `String`s whose CONTENT actually changed, so 74 lines keep
  theirs, and the counter is measured on the element before and after rather
  than inferred from which path the line took. "The line was rewritten" is not
  "the line lost its confidence", and assuming otherwise is what produced the
  phantom counts fixed in R1.
  `LOSS_MATRIX_VERSION` moves to `"2"`; `COUNTS_INVALIDATION` is `True` with
  `INVALIDATION_UNIT = "line"`. The per-`String` loss pass now excludes
  `INVALIDATED` attributes outright, so nothing is counted at two granularities
  at once. **Breaking for consumers reading `format_losses`:** the PAGE key
  `conf_dropped` is gone and its replacement counts lines, not attributes
  (0.9.x may break; `report_version` is unchanged — the report's *shape* did
  not move).

- **The top-level import surface is documented as provisional, and pinned
  against growth.** No symbol was added or removed; what changed is that three
  documents stopped describing `saknussemm.__all__` as something it is not.
  The list holds 95 names that were never ratified — they accumulated, one
  addition at a time — while `docs/PLAN.md` (`S3`) computes the surface as the
  transitive closure of what the façade returns, 54 symbols, and schedules the
  cut. Until then: `tests/test_public_api_snapshot.py` no longer calls the list
  `PUBLIC_API_1_0` / "the frozen 1.0 surface" (now `CURRENT_TOP_LEVEL_SURFACE`,
  an inventory), and gains a ratchet test — the surface may shrink, never grow.
  `docs/versioning.md` and the README state the provisional status and spell
  out the two doors: `saknussemm.*` under strict SemVer *from 1.0.0*, module
  paths (`saknussemm.core.*`, `saknussemm.formats.*`, `saknussemm.producers.*`)
  supported and documented. That distinction is what makes the pending cut a
  move rather than a removal — and it is the door this repository actually uses
  (695 module-path imports against 64 top-level ones).
- **`SPECS_LIB_V2.md §8.1` no longer promises three symbols it does not
  export.** The normative spec listed `reconcile_hyphen_pair`, `check_line` and
  `plan_page` as "déjà publics, maintenus". They are not in `__all__` and never
  were, while `__all__` exposed 95 symbols the spec never mentioned — the two
  contradicted each other in both directions. Resolved by withdrawing the
  promise rather than honouring it: the feature freeze suspends public-API
  extension, and `S3` reduces the surface. All three remain importable from
  their own modules, like everything `S3` will demote.

- **Two Unicode hyphens join the break-mark repertoire, on evidence.**
  `HYPHEN_CHARS` gains U+2010 HYPHEN and U+2011 NON-BREAKING HYPHEN. Widening
  the repertoire is not free — a new member makes lines pair that did not, on
  real documents — so this was measured first. Across the 40 ALTO/PAGE files in
  `examples/` and `corpus/`, text content only: 119 line-final `-`, 25
  line-final `⸗`, and **zero** occurrences of U+2010, U+2011, U+2013 or `=`.
  The two added are therefore provably inert on the existing corpora: latent
  coverage for a producer that uses them, and nothing else those characters can
  mean. `=` and U+2013 stay OUT for the same reason they were considered — they
  carry other meanings (an equals sign, a dialogue dash or a range) and there
  is no evidence they are needed; admitting either needs a corpus that contains
  them.

### Added

- **`saknussemm.core.losses` — the loss matrix (`LOSS_MATRIX_VERSION`).** The
  loss counters had grown one fix at a time and nothing ever stated what each
  attribute is *supposed* to do, so "every loss is counted" was a claim with
  no referent — and false in both directions at once. One versioned table now
  says, per attribute, which of four things happens to it (`PRESERVED`,
  `REWRITTEN`, `INVALIDATED`, `DROPPED`) and whether the report counts it. The
  ALTO rewriter consumes the table instead of keeping its own list. The
  distinction the counters were missing: `STRUCTURAL` attributes belong to the
  `String` and follow re-segmentation — a rebuild that writes *more* words has
  more `HPOS`, not fewer, and neither direction is a loss — while `SEMANTIC`
  ones carry an assertion about a reading. `WC`/`CC` are `INVALIDATED` (a
  correction makes the source engine's per-word confidence untrue) and whether
  that is *counted* is left as an explicit, documented flag rather than
  settled by silence: ALTO says nothing today, PAGE counts its equivalent as
  `conf_dropped`, and reconciling the two is a change both formats have to
  make together.

### Fixed

- **The report no longer claims hyphenation attributes it did not lose (ALTO).**
  A slow-path rebuild counted `SUBS_TYPE` and `SUBS_CONTENT` as dropped from
  every String it rebuilt — while `_apply_subs`, which runs on every write
  path, re-established both from the manifest on the same pass. On one real
  566-line page the report claimed **229 dropped SUBS_CONTENT** for a file
  whose output carries exactly as many as the source. A phantom loss misleads
  an auditor as much as a missed one, arguably more: it invites a hunt for
  damage that is not there.

### Added

- **`CorrectionReport.unpaired_breaks`** — how many lines announce a hyphen
  break that this run could find no partner for. Every cause of that was
  silent: `PairingPolicy.can_pair` returning False simply `continue`s, a
  partner on an absent page resolves to nothing, a pointer dangles. The line
  still ends mid-word, is corrected alone, and never reaches the reconciler,
  so its pair-drift guards never run either — and a host reading "0 fallback"
  could not learn that N words were split across a seam nobody sewed.
  Counted once for all causes, because the consequence is one.  Optional and
  additive — no `report_version` bump.

### Fixed

- **The payload no longer promises the model a hyphen partner that does not
  exist.** `hyphen_join_with_next` / `hyphen_join_with_prev` are assertions
  about the document, not hints, and they were set from the line's ROLE. A
  role is read off the line's own text — a trailing break mark makes it PART1
  — while the LINK is established in a second pass that can legitimately find
  nobody (the partner is on a page this run does not have, the pairing policy
  refused the candidate). The engine then told the model "this word continues
  onto the next line" about a line whose continuation does not exist, asking
  it to leave a word unfinished for a partner that never arrives — and nothing
  downstream could notice, since no pair means the reconciler never runs and
  the payload is compared against nothing. Both flags now follow the link,
  via `forward_partner_ref` / `backward_partner_ref`. A `SUBS_CONTENT`
  authority no longer travels without its link either. A linked pair's payload
  is byte-identical to before; for an orphan the key is simply absent
  (`exclude_none`), so the model is not told a continuation exists and is not
  told one is impossible — it is not told.

- **An empty page no longer severs a word broken across it.**
  `link_cross_page_hyphens` compared ADJACENT pages and skipped a page with no
  lines, so a word broken from page 1 onto page 3 was never linked when page 2
  happened to carry no text: the tail was left an orphan PART1 announcing a
  continuation to the model with no partner to reconcile against, and both
  fragments were corrected as unrelated lines. The walk now runs over the
  pages that have lines. An empty page is a fact about the scan, not about the
  sentence. Found by a metamorphic property, not by reading.

- **A mixed-role line no longer loses its forward break mark (ALTO).** A line
  can be BOTH with an explicit backward link and a HEURISTIC forward break —
  `PAG_00000002_TL000454` of `examples/X0000002.xml` opens on
  `SUBS_TYPE="HypPart2"` and ends on a bare dash with no `<HYP>`. The writer
  chose whether to strip that trailing mark from the String by reading
  `hyphen_source_explicit`, which describes the *backward* link; it answered
  "explicit", so the dash was dropped on the assumption a `<HYP>` element
  would render it. There is none, and the mark was gone from the delivered
  file. New `pairing.forward_break_is_explicit` applies the same role→slot map
  as `forward_partner_ref` to the explicitness flags. Byte diff on the real
  corpus, classified per TextLine: exactly 1 of 566, `Wal` → `Wal-`.

- **A cross-page hyphen pair no longer freezes its second member.** The
  reconciler owned a join from its TAIL, which is unreachable across a page
  break: the tail always sits on the earlier page and is decided before the
  head exists, so the tail's pass read the head's text out of a response that
  never mentioned it, fell back to raw OCR, and wrote that as the head's
  decision with `status = CORRECTED`. The later page then skipped the line
  (`corrected_text is not None`) and discarded the correction it had just paid
  for — **the first line of every page continuing a hyphenated word was never
  corrected**, and because the status was CORRECTED the loss reached no
  fallback counter. A join that leaves the page is now owned by its HEAD, the
  only point at which both sides exist. New `pairing.backward_partner_ref` is
  what made that expressible: the incoming direction had never been named,
  which is precisely why ownership could only ever sit on the tail.

- **A rejected hyphen pair is no longer reported as corrected.**
  Independently of the above and not limited to cross-page pairs: when
  `reconcile_hyphen_pair` reverted BOTH sides to their OCR text for
  incoherence, the members were still marked CORRECTED. Two lines kept their
  source text while reporting as corrections, so the revert appeared in no
  fallback counter and carried no reason. The status now follows the outcome;
  an identity correction still lands as CORRECTED, since nothing was proposed
  and thrown away. Both members' traces are refreshed by the reconciler, so a
  reverted tail whose page already closed still reports a reason (the decision
  set reads the reason from the trace).

- **A break mark is no longer doubled when the source renders it twice
  (ALTO).** Some producers write the end-of-line hyphen into the `String`
  CONTENT *and* emit a `<HYP>` for it; that is one mark rendered once, and
  `reconstruct_textline` de-duplicates it. The de-duplication tested
  `endswith("-")` — the ASCII hyphen alone — so every other mark in the
  repertoire doubled: `Ober⸗` + `HYP "⸗"` read back as `Ober⸗⸗`, `Ober¬` as
  `Ober¬¬`. It now tests the repertoire. Silent until now because this
  function feeds *both* sides of the projection invariant — the parser's
  `ocr_text` and the rewriter's UNTOUCHED comparison — so the mistake was
  made identically on both sides and compared equal to itself. Note the
  scope: no document in the repo's corpora triggers it (checked), so this
  closes a latent path rather than a measured one. The U+00AD → `-` collapse
  is deliberate and unchanged — it is what lets the 115 `<HYP>`-only lines of
  `examples/X0000002.xml` pair at all, and the bytes keep the source
  character because the rewrite paths re-emit the original element.

- **A no-break space no longer becomes an ordinary one (ALTO).** The
  rewriter's slow path tokenised on `\s`, which in Python covers U+00A0 and
  U+202F, and re-emitted every gap as an `<SP>` — an element that carries no
  content. `M.\xa0Dupont` was delivered as `M. Dupont`: the character whose
  entire job is to say "do not break here" was replaced by one that says the
  opposite, and the projection invariant compared the two as equal (see
  *Added*, below). The tokeniser now splits on **breaking** whitespace only,
  so a no-break space stays inside its `String`'s CONTENT and survives the
  round-trip verbatim. Repertoire: U+00A0, U+202F (French typography's space
  before `%`, `;`, `!`, `?`, `:`), U+2007. Token classification no longer
  goes through `str.strip()`, which calls a no-break space whitespace and was
  itself the substitution. A tab is unaffected and still normalises: it is a
  genuine break opportunity with no ALTO representation — and the run now
  reports that instead of staying silent about it.

### Added

- **Projection fidelity: the run now says what the format cost it.** The
  projection invariant compared the decided text against the rewritten
  artefact in whitespace normal form (`" ".join(text.split())`), so a
  whitespace *substitution* compared equal to no change at all. A line
  decided as `M.\xa0Dupont` and written back as `M. Dupont` passed silently:
  no error, no counter, no trace — the one corruption class the invariant
  exists to catch was the one class it could not express.
  `saknussemm.core.fidelity` replaces the boolean with an ordered scale.
  `exact` (the bytes say the decision character for character),
  `token_equivalent` (only what ALTO cannot represent was lost — a collapsed
  whitespace run, an edge space; `<SP>` carries no content) and `normalized`
  (a whitespace character was **swapped**: U+00A0, U+202F or a tab flattened
  to an ordinary space). A word-level divergence still fails the run with
  `ProjectionError`, unchanged. The level rides the report: per line on
  `ProjectionStage.fidelity`, per run on `CorrectionReport.projection_fidelity`
  as a count by level. Both fields are optional and additive, so
  `CORRECTION_REPORT_VERSION` does **not** move. Note U+202F specifically —
  French typography's space before `%`, `;`, `!`, `?` and `:`, the most
  frequent significant space in the corpus this library targets, and one that
  no earlier finding had named.

- **Real VLMs behind the vision seam + a terminal runner
  (`scripts/providers_multimodal.py`, `scripts/run_vision.py`).**
  `AnthropicMultimodalClient` (Claude, official SDK) and
  `MistralMultimodalClient` (Pixtral / multimodal Mistral, raw HTTP —
  images as `image_url` data URIs, `response_format: json_schema` with the
  backend's `json_object` fallback, plus `list_models` so a model ID is
  discovered with the caller's key rather than guessed) both implement
  `MultimodalStructuredClient`, so `VisionEditProducer` can drive an actual
  model instead of the benchmark's oracle. `run_vision.py --provider
  anthropic|mistral` corrects an ALTO/PAGE document end to end from the CLI
  — **no demo web app, no server** — in `vision` mode (every line) or
  `--hybrid` (QE routes: skip clean, escalate risky), paired with
  `GuardConfig.vision()`. **API keys are read from the environment and are
  never a CLI flag** (a flag lands in shell history and the process list),
  never printed, and never placed in a request body — only in the
  `Authorization` header; the pipeline additionally routes provider errors
  through `sanitize_error`. Two API details the adapters exist to
  get right: structured output uses `output_config.format` (schema enforced
  server-side, no forced-tool-call trick), and **`temperature` is rejected
  with HTTP 400 on current models** (Opus 5, Opus 4.8/4.7, Sonnet 5,
  Fable/Mythos) — so the engine's retry ramp (0.0 → 0.3 → 0.5) cannot be
  forwarded. The adapter drops it for those models and *records* that it
  did, rather than 400-ing every retry or pretending the ramp took effect;
  on such a model a retry is byte-identical to the attempt before it, which
  is a real limitation of the ramp, made visible. A safety refusal
  (`stop_reason: "refusal"`) returns no lines so the chunk falls back to OCR
  text instead of crashing. Tooling, not library API: vendor specifics stay
  out of the pixel-blind core (promoting provider adapters into
  `saknussemm[anthropic|…]` remains a Phase-5 item). Tests stub the SDK, so
  the request shape is asserted with no network call and no API key.

### Fixed

- **A hyphen unit now escalates as a WHOLE unit (ROADMAP V3 Phase 4).**
  Escalation previously refused hyphen units outright: no member could
  reach the vision producer, so every hyphenated line stayed with the
  primary text producer. Measured on real 19th-c. press OCR, that was the
  hybrid's **entire** residual error — predicted from those lines' own
  raw-OCR CER at 0.0079, measured at 0.0083. Now, when any member routes to
  ESCALATE, every member of its unit goes, so the pair still reaches ONE
  producer in ONE call and reconciles exactly as before: atomicity is
  preserved, not traded away. A unit whose links leave the page (or dangle)
  cannot be gathered from a single page's plan and keeps the conservative
  behaviour — it stays with the primary producer. A hyphen member is still
  never SKIPped. On the real corpus the hybrid drops from CER 0.0083 to
  **0.0021** — matching vision-on-every-line exactly, and both of those
  numbers come from an **oracle VLM**: a simulated producer that returns the
  ground truth for the lines it is given. It measures the ROUTING (which
  lines get escalated, and whether a unit travels whole), not a model. No
  real vision model has been benchmarked here; expect a real one to sit
  above both figures, and read this as an upper bound on what routing can
  buy, never as a quality claim (D3).

### Added

- **Real raw OCR beside the ground truth (`scripts/ocr_corpus.py`).**
  Removes the last synthetic ingredient from the vision benchmark: it runs
  a real OCR engine (Tesseract) over a GT corpus's own line images and
  pairs each reading with its GT line. The pairing is exact by
  construction — rather than OCR-ing the page and aligning two different
  segmentations, it OCRs **one crop per GT line**, cut with the library's
  own `crop_region` from the GT geometry (`--psm 7`), so every reading
  belongs to a known `(file, line_id)`. Two tiers, both genuine engine
  output: `--lang fra` (correct engine, CER 0.102) and `--lang spa` (a
  deliberately wrong language model on French — CER 0.105, 78/522 exact
  lines), which degrades the way bad OCR degrades (`l'entente` →
  `Ventente`) rather than the way a substitution table does. Real OCR
  merges words, invents characters and drifts apostrophes; no scripted
  table reproduces that. `vision_benchmark.py --ocr <sidecar>` consumes it,
  and the report's new `input` block always states whether the run used
  real OCR or scripted degradation. Measured on 37 real pages (real OCR
  input, oracle VLM): baseline 0.1018, text 0.1018, vision 0.0021, hybrid
  0.0083 escalating 316/522 lines. Two honest findings: the rules producer
  corrects **nothing** on 19th-c. press OCR (its table targets early-modern
  typography — a safe no-op, zero false positives), and the hybrid's entire
  residual error is the **hyphen units it refuses to escalate** (predicted
  0.0079 from their raw-OCR CER, measured 0.0083), which quantifies the
  atomicity trade-off and points at escalating a hyphen unit as a unit.
  Tesseract is not a project dependency: the sidecar is generated offline
  and its tests self-skip when the engine is absent.
- **Real-corpus extractor for QE calibration
  (`scripts/extract_press19_corpus.py`).** Derives the clean
  target-register text `fit_qe_calibration.py` needs from a **ground-truth
  ALTO corpus**, replacing the 18-line hand-written press pastiche the
  19th-c. constants were fit on. Four filters, each measured against a
  37-page BNL Luxembourg press GT set (522 lines → 178 French kept):
  **language** (heritage press is often bilingual — 312 French / 140
  German there; fitting a French model on German text inflates its
  surprisal on clean input and corrupts the Platt midpoint; `--lang de`
  extracts the German side for a German bundle), **hyphenation** (127
  hyphen-unit members are word fragments — a masked LM would score the
  truncation, not the language; dropped, never joined), **length** and
  **digits** (`Wiltz;`, `19694 74` carry no linguistic signal). Text is
  taken verbatim: period orthography is never normalised (rule 3), and the
  extracted units are OCR *lines*, matching what the scorer sees at
  runtime. Language detection is a dependency-free function-word vote plus
  German orthographic markers. This removes the *pastiche* half of the
  provisional-calibration caveat; the degradations remain scripted.
- **Vision benchmark harness (ROADMAP V3 Phase 4).**
  `scripts/vision_benchmark.py` measures text vs vision vs hybrid on a
  paired image+ALTO ground-truth corpus: it degrades each GT line into a
  plausible OCR reading with the Phase-2 deterministic scripted degrader
  (no RNG), runs the three configurations, and reports aggregate CER
  alongside the real call cost (`producer_calls`, `escalated_lines`).
  Validated on the **BNL** 19th-c. French press GT (37 pages / 522 lines,
  ALTO v4 `mm10` + 300 DPI PNGs): the XML→pixel mapping is the uniform
  `dpi/254` ≈ 1.1811 scale `ImageAsset.transform` exists for, verified by
  cropping lines and reading them back. **The images and the reference are
  real; only the OCR errors are synthetic** — the harness scores against
  human GT. Plumbing run with deterministic oracle producers (offline, 522
  real crops): baseline CER 0.0463 → text 0.0321, vision 0.0005, hybrid
  0.0073 while escalating only 326/522 lines — the cost/quality trade-off
  a real-provider run must reproduce. Measurement logic (CER, degradation,
  config comparison) is importable and unit-tested offline.
- **Per-line producer selection — the escalation tier (ROADMAP V3 Phase 4,
  §5.2 bis).** `CorrectionPipeline(..., escalation_producer=…)` routes each
  non-hyphen line the QE scorer + RoutingPolicy send to ESCALATE to a
  second producer (a VLM) instead of the primary text producer, on a
  per-line basis — the vision model routed only to the lines that earn its
  cost, the mechanism that makes the hybrid real rather than "one producer
  for the whole run". Routing stays entirely in the engine (where SKIP
  already lives): a chunk's targets are partitioned by tier into sibling
  chunks (shared context `line_ids`, disjoint targets), each carried by its
  producer through the retry/granularity-descent path. A hyphen unit is
  never escalated (atomicity — a pair split across producers could not
  reconcile), so its members stay with the primary producer. The escalation
  producer is preflighted like the primary (`require_page_images` /
  `require_capabilities`), so a run that will escalate to an image-less VLM
  fails at start-up. `CorrectionResult.escalated_lines` counts the routed
  lines and `RunProvenance.escalation_producer` records the second
  producer's identity; `producer_calls` stays honest (each routed chunk is
  one real call). Fully opt-in: without an `escalation_producer`, ESCALATE
  lines go to the primary producer exactly as before — a byte-identical
  run.
- **`ModelCapabilities` — the routing descriptor (ROADMAP V3 Phase 4,
  §5.2 bis).** A declarative descriptor (`text` / `vision` /
  `structured_output` / `max_images` / `context`) the Router reads to send
  each line only to a producer that can serve it — the mechanism by which
  a VLM is "just another producer", routed to the lines where it earns its
  cost rather than hardwired for the whole run. The brain is
  `can_serve(needs_image=…, needs_structured_output=…, image_count=…)`
  (and `reason_cannot_serve`, which explains an exclusion): it INFORMS the
  Router, it does not decide. Producers declare their own via a
  `capabilities` attribute (the same optional-attribute convention as
  `metadata`): `LLMEditProducer` a text-only descriptor, `VisionEditProducer`
  a vision-capable one (both injectable for a model's real context window /
  image cap). The pipeline preflights it with `require_capabilities` — a
  producer that wants images but declares `vision=False` is refused at
  start-up (like `require_page_images`), never a mid-run surprise. Frozen
  and additive; a producer that declares nothing is unconstrained
  (back-compatible). `ModelInfo` stays the catalog face of a model; this is
  the routing face. Per-line producer SELECTION in the pipeline (routing a
  chunk to a vision producer, honouring `max_images`) is the remaining
  Router-integration step; the descriptor and `can_serve` are the seam it
  will consume.
- **Per-page image digests in the run provenance (ROADMAP V3 Phase 4).**
  ``RunProvenance.image_digests`` (page_id → ``sha256:<hex>``) records the
  exact scan bytes a vision run saw — the mirror of ``source_digests`` for
  pixels. The pipeline copies the digest each structured ``ImageAsset``
  already carries; the pixel-blind core opens no image to compute one (I4),
  so bare ``ImageRef`` strings and digest-less assets contribute nothing.
  Together with the source digest, the per-line coords, the asset's
  transform and the producer's ``configuration_fingerprint`` (which folds
  in the crop margin / polygon-mask knobs), this makes every crop
  REPRODUCIBLE without storing N per-line crop hashes — the same
  digest-level contract ``source_digests`` gives for the XML (the report
  stores the digest, not the bytes; the caller re-supplies the inputs).
  Additive and optional: empty on text runs, no ``report_version`` bump.
- **`GuardConfig.vision()` — the VLM guard profile (ROADMAP V3 Phase 4,
  §5.2 bis).** A preset a host passes alongside a `VisionEditProducer`:
  it relaxes ONLY the Stage-C source-similarity floor
  (`min_source_similarity` 0.35 → 0.15) because a VLM reads the image, not
  the OCR, so a correct reading of a badly-garbled line diverges further
  from the source than a text model's would and the text default would
  reject it. Every inter-line migration guard — neighbour proximity,
  absorption, hyphen-pair drift, duplication — keeps its text default: a
  VLM must no more merge or move lines than a text model. The relaxed
  floor is not 0.0 (a producer that ignores the image and invents an
  unrelated line is still caught) and is **provisional** until the Phase-4
  vision benchmark refits it; an explicit override always wins
  (`GuardConfig.vision(min_source_similarity=0.22)`). Like every
  `GuardConfig`, it carries its values into the composite fingerprint, so
  choosing the profile is a structurally recorded decision, not a hidden
  mode. The library default is unchanged (opt-in), so runs without it stay
  byte-identical.
- **`VisionEditProducer` — the `saknussemm[vision]` extra, part 2 (ROADMAP
  V3 Phase 4).** ``integrations.vision.VisionEditProducer`` adapts a
  multimodal provider to the ``EditProducer`` contract: for each target
  line it crops the region from the page image (the pure
  ``crop_region``), hands the crops + OCR text to a
  ``MultimodalStructuredClient``, and shapes the reply into a
  ``replace_line`` ``EditScript`` — through the SAME response parser the
  text ``LLMEditProducer`` uses, so the guard matrix, validator and
  uncertainty channel behave identically downstream; only payload assembly
  differs. ``wants_image``/``wants_geometry`` are ``True``, so the pipeline
  copies each line's geometry and the page image into the §4.1 envelope;
  the image MUST be a structured ``ImageAsset`` (a bare ``ImageRef`` string
  cannot be cropped and is refused with a clear error). Each crop travels
  as an ``ImagePart`` carrying its own SHA-256 (the crop hash, tied to its
  ``line_id``), and the ImageAsset carries the image hash — the provenance
  a reproducible decision records. A new multimodal seam
  (``MultimodalStructuredClient``) keeps the text producer's lean,
  image-free ``complete_structured`` contract untouched. The core stays
  pixel-blind: it forwards the opaque asset and never opens it; every pixel
  goes through ``crop_region``. The shared LLM response parser and
  configuration-fingerprint helper were extracted to ``integrations.llm``
  (``edit_ops_from_response``, ``prompt_schema_fingerprint``) with the text
  producer's behaviour byte-identical (fingerprint pin unchanged).
- **Pixel-pure vision cropper — the `saknussemm[vision]` extra, part 1
  (ROADMAP V3 Phase 4).** ``integrations.vision`` is the deterministic
  half of the vision chain: ``build_image_asset(page_id, path)`` decodes a
  file into the populated ``ImageAsset`` the core carries (SHA-256 of the
  exact bytes, real decoded MIME, **visual** pixel dimensions, multipage
  TIFF ``frame_index``, EXIF orientation), and ``crop_region(asset,
  coords)`` maps an XML bbox to pixels via the asset's ``ImageTransform``,
  normalizes EXIF orientation, grows the box by an optional
  ``margin_ratio``, optionally masks to a PAGE polygon (RGBA), clamps to
  the image, and returns an encoded ``Crop`` with its own SHA-256 — the
  crop-hash the audit trail records (acceptance criterion 5). Pure and
  deterministic: identical inputs yield an identical crop hash, so every
  geometry decision is tested with a Pillow-drawn fixture and **no
  network, no API key** (the non-deterministic VLM call is a separate,
  forthcoming seam). **Pillow is the only image dependency and is imported
  lazily inside each function** — importing the module never pays the
  image runtime, and the pixel-blind core never pulls it. I4 is restated
  accordingly: the pixel-blind zone (core, formats, text producers) is
  image-lib-free by static scan AND by a runtime import contract
  (``import saknussemm`` loads no image lib into ``sys.modules``), while
  the sanctioned ``integrations/vision.py`` may import Pillow function-
  locally — the same pattern as the qe extra. New extra
  ``saknussemm[vision] = ["pillow"]``.
- **Structured `ImageAsset` — the recommended page-image contract
  (ROADMAP V3 Phase 4).** ``run(page_images=…)`` now accepts, per page,
  either the historical opaque ``ImageRef`` (str) or the richer
  ``ImageAsset`` (the new ``PageImage = ImageRef | ImageAsset`` union):
  ``page_id``, opaque ``uri``, ``sha256`` of the exact bytes, decoded
  ``media_type`` and pixel dimensions, multipage ``frame_index``,
  ``exif_orientation``, and an ``ImageTransform`` (XML-coordinate →
  pixel scale/offset) a crop needs. The asset rides the existing §4.1
  vision envelope unchanged — the compiler copies it into
  ``CorrectionRequest.image_ref`` only when the producer asks
  (``wants_image``) and forwards it **verbatim**; the pixel-blind core
  still opens **no** pixel (invariant I4). ``require_page_images`` now
  also rejects an ``ImageAsset`` filed under a mapping key that
  disagrees with its own ``page_id`` — the silent wrong-image bug the
  per-page contract exists to catch. Fully additive and opt-in: a bare
  ``ImageRef`` behaves exactly as before, and the decoding builder that
  *populates* an ``ImageAsset`` from a file is the forthcoming
  ``saknussemm[vision]`` extra (Phase 4), never the core.
- **Zero-shot D'AlemBERT QE scorer — the `saknussemm[qe]` extra
  (ROADMAP V3 Phase 3).** ``integrations.qe.MaskedLMQEScorer`` implements
  the pure-core ``QEScorer`` protocol with the masked pseudo-perplexity
  (Salazar et al. 2020) of D'AlemBERT — a RoBERTa masked LM pre-trained
  on early-modern French (``pjox/dalembert``, Apache-2.0) — as a
  zero-shot "does this line still need correction?" signal. No training:
  a token the period language model finds improbable is a likely OCR
  break. **Runtime is `onnxruntime` + `tokenizers` only — no torch, no
  transformers** (the heavy torch→ONNX conversion lives in the dev-time
  ``scripts/export_masked_lm_onnx.py``, never on the install path); heavy
  imports are lazy and the pixel-light core never loads them
  (import-contract test). Historical orthography is never an error
  signal (rule 3): the scorer reads a **glyph-neutralized copy**
  (``ſ→s``, ligatures → ASCII) so perplexity measures linguistic
  implausibility, not typography — the document text is untouched. The
  scorer INFORMS, the Router decides. Measured on the OCR17+ corpus
  (``scripts/qe_benchmark.py``), it beats the ``HeuristicQEScorer``
  baseline on every metric — real / synthetic: token AUC 0.66 / 0.66
  (vs 0.50), token ECE 0.04 / 0.03 (vs 0.32 / 0.29), line AUC 0.77 /
  0.88 (vs 0.50). OFF by default (opt-in scorer; byte-identical without
  it). ONNX bundle built offline via
  ``python scripts/export_masked_lm_onnx.py``.
- **Model- and register-adaptive QE — pick the model per period.** The
  same ``MaskedLMQEScorer`` drives ANY masked LM behind the seam: each
  ONNX bundle is SELF-DESCRIBING (its ``qe_model.json`` carries the Platt
  constants, the subword ``word_reducer`` and the ``line_reducer``), so
  pointing ``model_dir`` at the right bundle loads the right calibration.
  ``scripts/export_masked_lm_onnx.py --model-id <hf>`` builds any bundle;
  ``scripts/fit_qe_calibration.py`` fits its calibration on a target-
  register corpus and picks ``line_reducer`` by line-level AUC. Word→word
  mapping is now offset-based (robust to WordPiece/SentencePiece splitting
  apostrophes and hyphens, not just byte-level BPE), and the ORIGINAL
  archaic spelling is still reported. For **late-19th-c. press**,
  CamemBERT (``camembert-base``, MIT) with ``line_reducer="mean"`` is the
  recommendation — token AUC 0.98, clean/OCR line score 0.14/0.51 (``mean``
  beats ``max`` here because press proper nouns spike a few clean words a
  contemporary model rarely saw). See ``docs/qe-scorer.md``.
- **Routing cost accounting (ROADMAP V3 Phase 3).**
  ``CorrectionResult.producer_calls`` counts every ``producer.produce``
  invocation (retries included) — the real per-call cost driver for an
  LLM API. Routing lowers it by dropping whole all-skipped chunks, so
  comparing a routing-on run to a routing-off run on one document is how
  the hybrid PROVES it is cheaper (the review's "l'hybride doit prouver
  qu'il est moins cher"), no fabricated counterfactual. Additive,
  ``0``-safe, unrelated to the fingerprint.
- **Hybrid-selective routing wired into the pipeline (ROADMAP V3
  Phase 3).** ``CorrectionPipeline(qe_scorer=…, routing_policy=…)`` (and
  ``for_provider``): a line the QE scorer + policy route to SKIP is
  confirmed clean and dropped from its chunk's targets — it stays as
  context for neighbours but its output is discarded, and a chunk whose
  targets are ALL skipped is dropped entirely (no producer call, the
  token savings). A hyphen unit is never skipped (atomicity). SKIP
  lines end ``CORRECTED`` with unchanged text; the auditable skip
  signature is a corrected line whose trace ``model_input_text`` is
  ``None`` (never sent to the model). ``CorrectionResult.lines_skipped``
  exposes the count (the economics signal). OFF by default — no scorer
  and ``RoutingPolicy()`` routes every line to the LLM, so a default run
  is byte-identical (byte-parity corpus unchanged); routing is not in
  the §8.2 composite fingerprint.
- **QE scoring + routing brain (ROADMAP V3 Phase 3, core).** New
  ``saknussemm.core.quality``: the ``QEScorer`` protocol (score a
  SOURCE line's need for correction in [0,1], pre-LLM), a
  zero-dependency ``HeuristicQEScorer`` baseline, and the routing brain
  (``RoutingPolicy`` frozen thresholds, ``RoutingDecision`` enum,
  ``route_line`` — SKIP a clean line for no LLM call / LLM / ESCALATE).
  Routing is opt-in: ``RoutingPolicy()`` defaults both bounds to
  ``None`` (every line → LLM, historical behaviour). The heuristic uses
  ONLY orthography-neutral signals (a digit stranded in a word;
  out-of-lexicon against a supplied lexicon) — NOT archaic glyphs:
  measured on the OCR17+ corpus, an archaic-glyph heuristic scored the
  human-corrected reference (full of preserved long-s / u-for-v)
  HIGHER than raw OCR, the exact "flag historical spelling as
  improbable" trap. Without a lexicon the baseline abstains by design;
  distinguishing a real OCR non-word (``cukiuent``) from a valid
  historical form (``cultiuent``) needs a historical lexicon or model —
  the measured justification for the Phase 3 ONNX/D'AlemBERT scorer,
  which will sit behind the same ``QEScorer`` protocol in
  ``saknussemm[qe]``. Additive public API; not yet in the pipeline or
  the §8.2 composite fingerprint (wiring is the next Phase 3 step).

- **LLM uncertainty channel (ROADMAP V3 Phase 1).** Opt-in contract
  variant for ``LLMEditProducer`` (``uncertainty_channel=True``, also
  on ``CorrectionPipeline.for_provider``): the model must return a
  per-line ``status`` (``certain``/``uncertain`` — an explicit outlet
  for doubt instead of silent guessing) and reason-coded per-token
  ``edits`` (``confusion_connue`` / ``mot_du_lexique`` /
  ``infere_du_contexte`` / ``conjecture``). The app VERIFIES every
  verifiable claim (``saknussemm.core.confidence.score_producer_claims``
  — confusion table, lexicon, token existence); a failed check scores
  BELOW an honest conjecture. The verified score rides
  ``ReplaceLine.producer_confidence`` (additive) and feeds the
  ``producer`` component of ``LineConfidence``. Off by default: the
  base prompt/schema stay byte-identical, and the channel's different
  contract yields a different producer ``configuration_fingerprint``
  (§11).

- **Multi-component line confidence (ROADMAP V3 Phase 1).**
  ``ConfidencePolicy(mode="drop"|"report_only")`` — default ``drop``
  keeps behaviour identical; ``report_only`` fills a
  ``LineConfidence`` block on every ``LineOutcome``: named components
  (``ocr`` — the source engine's own confidence, now preserved by both
  parsers as ``LineManifest.ocr_confidence`` from ALTO ``String/@WC``
  mean / PAGE ``TextEquiv/@conf``; ``alignment`` — the token-alignment
  score of the decided text; ``scorers`` — each injected
  ``ConfidenceScorer`` by name; ``producer`` — reserved for the LLM
  uncertainty channel) plus a ``decision`` aggregate under an
  IDENTIFIED formula (``min`` over present components). New
  ``saknussemm.core.confidence`` module with the ``ConfidenceScorer``
  protocol and the zero-dependency ``HeuristicScorer`` (character
  evidence + classic OCR confusion table + optional lexicon).
  ``mode="write_wc"`` is declared but LOCKED (raises) until the
  Phase 2 calibration harness proves the values on a real corpus.
  ``ConfidencePolicy`` deliberately stays OUT of the §8.2 composite
  fingerprint until then (``report_only`` never affects the corrected
  XML) — pinned by test.

- **token_realign loss policy + sidecar (ROADMAP V3 Phase 1).**
  ``LossPolicy`` grew ``min_alignment_score`` (default ``None`` — the
  gate is off and behaviour is identical). When set, a word-count-
  changing correction whose token alignment onto the source scores
  below the threshold — or ANY correction raising the aligner's move
  flag — is not projected: the line reverts to source markup (whole
  hyphen unit, ADR-010) and the correction is PRESERVED as a
  ``SidecarEntry`` on ``CorrectionReport.sidecar`` (also written as
  ``sidecar.json`` by ``CorrectionResult.write`` when non-empty) for
  review instead of lost. New core module ``saknussemm.core.alignment``
  (char-level Levenshtein similarity → monotonic token DP; a match
  requires character evidence; moves are flagged, never applied) also
  drives the ALTO slow path's identity recycling, which is now aligned
  instead of positional. The §11 composite ``config_fingerprint``
  moved (``55dc80679dd71f94`` → ``15dc07cba9122106``): the new FIELD
  joins the fingerprinted policy surface (defaults unchanged).

- **Versioned correction benchmark + ground-truth corpus seed (P4.2).**
  ``scripts/benchmark.py`` (repo tooling, not part of the package)
  measures a producer against ``tests/corpus_gt/`` — micro-averaged
  CER/WER before/after, improved/degraded line counts, false positives
  (already-correct lines a run changed), fallbacks, reconcile outcomes,
  structural losses, latency/page and peak memory — and emits a JSON
  report a release can cite: ``benchmark_version``, ``lib_version``,
  ``corpus_version``, the §11 ``config_fingerprint`` and the producer's
  ``ProducerMetadata`` identity. Three deterministic, offline
  producers: ``rules``, ``oracle`` (cassette derived from the
  reference — the upper bound the guards still arbitrate) and
  ``cassette:<path>`` (recorded ``{line_id: text}`` replay, the P4.2
  LLM-cassette seam). The corpus ships one clearly-marked SYNTHETIC
  seed case (documented scripted degradations: long s, ﬁ ligature, one
  ``rn`` confusion the default rules deliberately cannot fix; one
  heuristic hyphen pair) — real human-reviewed Gallica pages remain
  P4.1's human work, and the corpus README pins the provenance rules.
  House rule now in force: no guard/ramp default changes without a
  measured improvement here. Smoke-tested in CI (report contract,
  rules improvement with residual, oracle at CER 0, cassette ≡ oracle).

- **The error root gets its final name (P3.11, first slice).**
  ``SaknussemmError`` — named for the LIBRARY, like
  ``requests.RequestException`` — replaces ``CorrectionError`` as the
  §8.4 root, and ``ProposalValidationError`` replaces the bare
  ``ValidationError`` (which collided with pydantic's in every
  consumer's imports; the P3.7 vocabulary already calls what it
  validates a *proposal*). The old names remain 0.9.x deprecation
  ALIASES of the very same classes — ``except``, ``isinstance`` and
  subclassing behave identically through either name; machine ``code``
  attributes are unchanged — and disappear at the P3.11 top-level
  reduction. Library internals speak the new names; both spellings are
  top-level exports for now.

- **The three-line happy path (P3.12, §2).**
  ``saknussemm.load(*paths)`` sniffs each file's root namespace (ALTO
  or PAGE — one format per document, unique basenames) and returns a
  ``LoadedDocument`` (manifest + the name → path map a run needs);
  ``saknussemm.correct(document, producer=…)`` /
  ``saknussemm.correct_sync(…)`` run a default pipeline around any
  ``EditProducer`` — no observer, no adapter, no manifest plumbing
  required for the simple case (no-op observer, default policies,
  provenance from the producer's declared identity). Purely ADDITIVE:
  ``CorrectionPipeline`` keeps every knob; the P3.11 top-level API
  reduction remains a separate, deliberate decision. All four symbols
  are lazy top-level exports (``import saknussemm`` still never loads
  lxml); the quickstart now leads with the three-line path.

- **EditScript preconditions — a script only applies to the document
  it was computed against (P3.10, §4).** ``EditScript`` records its
  ``protocol_version`` (``EDIT_PROTOCOL_VERSION``, currently ``"1"``;
  ``apply_edit_script`` raises ``ValidationError`` on a version it
  does not speak), the run's ``source_digests`` (same values as
  ``RunProvenance`` — one shared computation), and one
  ``LinePrecondition`` per op-carrying line: the :func:`line_digest`
  of the SOURCE text the ops were computed against, page-qualified
  like the ops' stamps. Applying a script to a document that carries
  the same line_id over DIFFERENT content rejects the line's ops
  (``precondition_source_digest``) — an op never lands on a lookalike.
  All fields optional/additive: hand-written scripts keep their
  historical behaviour. The run's final ``edit_script`` is fully
  stamped. ``EDIT_PROTOCOL_VERSION``, ``LinePrecondition`` and
  ``line_digest`` join the public surface.

- **`RunProvenance` — the report says exactly what produced it (P3.9,
  §11).** ``CorrectionReport.provenance`` (optional, additive — no
  ``report_version`` bump) records the library version, the §8.2
  composite ``config_fingerprint`` (the same value stamped into the
  XML), the GENERIC producer identity (``ProducerProvenance``, the
  report-side mirror of ``ProducerMetadata`` — a rules run records its
  name + configuration digest, never an artificial vendor/model pair),
  a ``sha256:`` digest of every INPUT file's bytes (empty on dry
  runs), the manifest's source format, and the installed versions of
  the critical dependencies (lxml, pydantic — resolved from package
  metadata, never by importing them: the pure core stays lxml-free).
  Generation parameters are not duplicated: the retry/temperature
  strategy is already covered by the policy fingerprint.
  ``RunProvenance`` and ``ProducerProvenance`` join the public surface.

- **`LossPolicy` — REPORT or STRICT on format-granularity loss
  (ADR-012, P3.8).** The PAGE rewriter cannot keep ``Word`` geometry
  when a correction changes a line's word count (6.2 P4 slow path).
  ``LossPolicy(strict=False)`` (the default) makes the historical
  stance explicit: the correction projects, the loss is counted
  run-wide (``CorrectionReport.format_losses``) and now ATTRIBUTED per
  decision — ``ProjectionStage.losses`` carries each line's own share
  (``RewriteResult.losses_by_line`` → ``LineTrace.projection_losses``
  under the hood). ``LossPolicy(strict=True)`` rejects instead: a
  correction that cannot project without loss makes its WHOLE hyphen
  unit fall back to source text (reason code ``format_loss``,
  ADR-010 atomicity) BEFORE any output exists, so the source markup
  keeps its word geometry. The check runs in the pure core off the new
  ``LineManifest.word_count`` (stamped by the PAGE parser; ``None`` on
  word-less lines and on ALTO, whose per-token geometry redistributes
  at any count). Stale-annotation drops (``conf``, alternative
  ``TextEquiv``, offset ``custom`` groups) describe the old reading and
  stay report-only in both modes; no third mode until a real need
  shows up. ``LossPolicy`` joins the §8.2 policy surface, the public
  API, ``for_provider``, and the §11 ``config_fingerprint`` (composite
  pin ``216aa712f1e99b79`` → ``55dc80679dd71f94`` — a fifth ``loss``
  key in the payload).

### Changed

- **BREAKING — `ProducerMetadata` replaces the bare
  `provider_name`/`model` strings (P3.7, fourth slice).** The
  ``CorrectionPipeline`` constructor takes one
  ``producer_metadata: ProducerMetadata | None`` (frozen dataclass:
  ``name``, ``version``, ``implementation``,
  ``configuration_fingerprint``) instead of the two label kwargs — a
  rules producer has no "model", so the generic identity names WHO
  produced the edits and, when one exists, the concrete engine behind
  the name. Producers may DECLARE their identity via an optional
  ``metadata`` attribute (the ``requires_full_coverage`` convention;
  explicit constructor metadata wins): ``LLMEditProducer`` declares
  ``name="llm"`` + its model, ``RulesProducer`` declares
  ``name="rules"`` plus a deterministic 16-hex
  ``configuration_fingerprint`` over its rules table and lexicon.
  ``for_provider`` keeps its pinned vendor vocabulary
  (``provider_name``/``model``) and builds the envelope itself, and the
  §11 labels stamped into corrected XML derive via
  ``provenance_labels()`` (an implementation-less producer stamps
  ``"unknown"``) — the format seam and the stamped bytes are unchanged.
  ``ProducerMetadata`` joins the public surface.

- **BREAKING — the producer seam takes `ProducerOptions`, not the
  RetryPolicy (P3.7, first slice).** ``EditProducer.produce(payload, *,
  options)`` receives a per-call envelope — ``attempt``, the RESOLVED
  ``temperature`` (ramp and hyphen 0.0-pin decided engine-side, ending
  the "policy whose first temperature is this attempt's" contortion),
  an optional ``deadline_seconds`` hint, and ``should_abort``: the
  run's cancellation probe, so a producer can abandon long I/O
  mid-flight (or wire the probe into its HTTP client) instead of the
  engine only noticing between chunks. The engine keeps the full
  ``RetryPolicy`` to itself.

- **Client/catalog split (P3.7, second slice).** ``BaseProvider`` is
  now the composition of two protocols: ``StructuredCompletionClient``
  (``complete_structured`` — the ONLY LLM capability the core consumes;
  ``LLMEditProducer`` and ``for_provider`` type against it, so a client
  with no ``list_models`` at all drives a full run) and
  ``ModelCatalog`` (``list_models`` — application vocabulary; the demo
  backend's ``/providers/{p}/models`` concern). Both join the public
  surface; ``BaseProvider`` keeps working unchanged for full vendor
  clients.

- **BREAKING — generic vocabulary replaces the LLM-branded names
  (P3.7, third slice).** ``LLMUserPayload`` → ``CorrectionRequest``,
  ``LLMLineInput`` → ``LineContext``, ``LLMLineOutput`` →
  ``LineProposal``, ``LLMResponse`` → ``ProposalBatch`` — a rules or
  vision producer receives no "LLM payload"; the edit protocol's
  request/proposal shapes are producer-agnostic. The purely-LLM
  contract (``SYSTEM_PROMPT``, ``OUTPUT_JSON_SCHEMA``) moves from
  ``saknussemm.producers.llm`` to ``saknussemm.integrations.llm`` —
  ``saknussemm.producers`` keeps only producer implementations. No
  wire/JSON shape changes anywhere: these are Python-surface renames.
  Remaining P3.7 work: ``ProducerMetadata`` replacing bare
  ``provider_name``/``model`` (a rules producer has no "model") — the
  provenance-stamping surface, a later slice.

- **BREAKING — `PipelineEventType` names only engine events (P3.6,
  first slice).** The server-side values — job lifecycle ``started`` /
  ``completed`` / ``failed`` / ``cancelled``, the frontend-only
  ``queued``, and the SSE transport ``keepalive`` / ``error`` — left
  the engine's enum for the demo backend's own
  ``app.jobs.events.JobEventType``: the library no longer enumerates
  what a HOST says about a job. The wire strings are unchanged on both
  sides (the SSE contract test still pins the union against the
  frontend's list); only the Python spelling of the server values
  moved.

- **Typed engine events (P3.6, second slice).**
  ``saknussemm.core.events`` defines one frozen ``EngineEvent``
  dataclass per ``PipelineEventType`` (``DocumentParsed``,
  ``ChunkStarted``, ``ChunkDowngraded``, ``RewriterStats``, …): the
  emit sites construct these instead of ad-hoc dict literals, so every
  payload's shape lives in exactly one importable place and the
  type↔class bijection is pinned by test. The observer port keeps its
  wire shape (``on_event(event_type, payload)``) — the pipeline renders
  ``event.type`` + ``event.payload()`` at the boundary, so observers
  and the SSE wire format are untouched. The demo backend's job-end
  ``reconcile_stats`` now goes through the typed ``ReconcileStats``
  too.

- **BREAKING — report v2: staged `LineOutcome` entries (P3.5,
  `report_version` 1.0 → 2.0).** `CorrectionReport.lines` now carries
  one `LineOutcome` per line — ``source_text`` plus three explicit
  stages: ``proposal`` (producer input/output, absent when the line
  never reached a producer), ``decision`` (terminal ``status``,
  ``final_text``, and a STRUCTURED ``reason`` ``{code, detail}`` whose
  code aggregates exactly like ``CorrectionResult.fallback_reasons``),
  and ``projection`` (``extracted_text`` — renamed from
  ``output_alto_text``, wrong in an ALTO+PAGE library — and
  ``rewriter_path``; absent when no output file was rendered). The
  builder reads the ADR-011 `DecisionSet` (the terminal stage's
  authority), completing slice C's reader migration. The decision stage
  additionally carries ``features`` (`ProposalFeatures`) — the
  similarity/length metrics the acceptance guard computed ONCE while
  deciding (recorded on ``AcceptanceResult.features``), so no consumer
  re-derives them; absent on lines that never reached per-line
  acceptance. `LineOutcome`, `ProposalStage`, `ProposalFeatures`,
  `DecisionStage`, `DecisionReason` and
  `ProjectionStage` join the public surface; `LineTrace` remains the
  Python-side working trace on ``CorrectionResult.traces`` — the two
  surfaces version independently (``docs/versioning.md``).

- **BREAKING — `run()` never mutates its input (ADR-011, slice E).**
  The engine works on its own deep copy of the document manifest: the
  caller's manifest keeps its parse-time state (`corrected_text` stays
  `None`, `status` stays `PENDING`), re-running the same document
  always starts from the original OCR text, and the run's outcome is
  read off the result — `CorrectionResult.decisions`, an immutable
  `DecisionSet` with one terminal `LineDecision` per line in reading
  order (`DecisionSet`, `LineDecision` and `LineRef` join the public
  surface). Consumers that displayed corrected text from the manifest
  project the decisions onto their own state (as the demo backend now
  does for its /diff and /layout read models).

### Removed

- **The one-run-per-instance guard (ADR-005, superseded).** With
  per-run state fully contained (fresh `RunContext` + private manifest
  copy) and no writer on the engine, concurrent `run()` calls on one
  instance are safe and supported; the `RuntimeError` guard is gone.
  The P0 run-independence property is now pinned in its final form:
  two runs on the SAME document object yield identical decisions.

- **BREAKING — persistence left the engine surface (ADR-011, slice
  D-fin).** `CorrectionPipeline(output_writer=…)` /
  `for_provider(output_writer=…)` and `run(apply=…)` are gone, and the
  `OutputWriter` protocol is no longer part of `saknussemm` (the demo
  backend now owns its own port in `app.protocols`). The engine never
  writes: every run computes `result.corrected_files` + `result.report`
  and the caller persists — `result.write(dir)` for the simple case
  (corrected XML under the source names + `report.json`), or a
  host-owned transaction. What `apply=False` used to buy is now every
  run's behaviour. The ADR-005 one-run-per-instance guard remains (its
  surviving rationale: shared observer + in-place manifest mutation
  until slice E).

### Added

- **The result carries its artefacts (ADR-011, slice D).**
  `CorrectionResult.corrected_files` maps each source file name to its
  corrected XML bytes on EVERY run — dry runs included, where the bytes
  were previously unreachable — and `result.write(dir)` persists the
  artefacts plus the §9 report (`report.json`) caller-side.

- **Terminal-decision invariant — no line ends a run undecided.** The
  page loop's ADR-008 absorb branch (recoverable `CorrectionError` →
  `chunk_error` event + continue) now OCR-falls-back every
  still-`PENDING` target line of the failed chunk before continuing —
  previously those lines silently kept no decision while the run
  reported success. A run-level backstop additionally refuses to write
  outputs while any line is `PENDING` (engine bug → loud `RuntimeError`,
  never a degraded success).

- **Projection invariant — the artefact must say what the run decided.**
  The per-line text re-extracted from the rewritten XML (previously a
  trace-only diagnostic, `output_alto_text`) is now verified against the
  final per-line decision before the writer persists anything. A missing
  line or a word-level divergence raises the new
  `saknussemm.errors.ProjectionError` and fails the run — a divergent
  artefact is corruption, never a valid output. Whitespace runs are
  compared in normal form: ALTO/PAGE word tokenization cannot represent
  consecutive spaces, a documented format property (exact-space loss
  accounting is future loss-policy work).

### Fixed

- **An identity proposal can no longer be rejected as hyphen fusion.**
  The Stage-A fusion detector flagged a PART1/BOTH line whenever its
  last corrected word equalled the pair's logical word — even when the
  SOURCE line already ended with that word (degenerate one-letter
  fragments: 'A' + 'A' → word 'AA' on a line reading 'AA-'). A producer
  proposing the source verbatim was rejected on every retry, the chunk
  hard-failed, and the descent budget OCR-fell-back every cohabiting
  line, with a blast radius that depended on the chunk partition — how
  the chunking-invariance gate caught it. The check is now
  source-relative, like every other drift check: it only fires when the
  correction *introduced* the full word.

- **A fallback now covers the whole hyphen unit, across pages
  (ADR-010).** A cross-page pair lives in two page-scoped chunks; when
  one side's chunk fell back while the other side's succeeded, the pair
  ended half OCR / half corrected — the joined word across the seam was
  rewritten on one line and kept verbatim on the other, the exact state
  `reconcile_hyphen_pair`'s contract forbids. Both directions are
  closed: a chunk fallback (and the absorb branch) extends to the
  unit's members on other pages via the shared hyphen closure, and the
  reconcile/acceptance paths refuse to correct a member whose partner
  already fell back (`hyphen_partner_fell_back` /
  `hyphen_unit_fallback` trace reasons). The duplicate-revert pass now
  walks that same shared closure instead of its own inline worklist —
  one traversal, one definition of the unit.

### Added

- **`saknussemm.core.units` — atomic hyphen groups (ADR-010, slice 1).**
  `HyphenGroup` + `derive_hyphen_groups()` are THE single derivation of
  "these lines travel together" (maximal hyphen components, members as
  `LineRef`s in reading order, `spans_pages`/`explicit` flags),
  cross-validated property-by-property against a new rich generated
  corpus (chains PART1→BOTH→PART2, multi-page files, explicit
  cross-page seam pairs). The chunk planner's window pinning now
  consumes it; its local union-find is gone. Reconciliation/fallback
  per group follows in the next slice.

### Changed

- **The format seam returns one `RewriteResult` (ADR-011, slice A).**
  `FormatAdapter.rewrite_file` now returns `RewriteResult(xml_bytes,
  metrics, rewriter_paths, texts, losses)`; the adapter-level
  `extract_texts` port is gone. The per-line texts are read off the
  very tree the bytes were serialized from, so the projection
  invariant (P1.4) verifies without re-parsing the output — one full
  lxml parse per file removed from every run. `RewriteResult` unpacks
  positionally to the historical `(xml_bytes, metrics, rewriter_paths)`
  triple during the migration. The module-level `extract_output_texts`
  helpers remain for round-trip checks over arbitrary bytes.

- **The run's decisions materialize as an immutable `DecisionSet`
  (ADR-011, slice C).** After the global consistency pass —
  the point where no later pass may change a decision — the engine
  derives `saknussemm.core.decisions.DecisionSet`: every line's
  terminal decision (source text, final text, status, fallback reason)
  in document reading order, keyed by qualified identity. The
  terminality backstop is now its construction invariant (a `PENDING`
  line refuses materialization and fails the run), and the projection
  invariant plus the result's `fallback_lines`/`fallback_reasons`
  accounting read the DecisionSet instead of re-walking the mutable
  manifests. Internal for now; it is the seam the immutable-source
  slice flips.

- **Manifest counters are computed (ADR-011, slice B).**
  `DocumentManifest.total_pages/total_blocks/total_lines` derive from
  the pages (`computed_field` — still present in the serialized shape);
  they are no longer constructor inputs and the contradictory-totals
  validator is retired: a derived count cannot lie. Constructors
  passing the legacy kwargs keep working — the values are ignored.

- **`CorrectionReport.format_losses` is finally populated.** The field
  existed since the PAGE rewriter grew its granularity counters
  (`words_dropped`, `custom_offset_stripped`, …) but no pipeline run
  ever set it. The `RewriteResult` carries each file's counters and the
  run aggregates them onto the report — dry-run included.

- **One global consistency pass (P3.3).** Adjacent-duplicate detection
  now runs ONCE over the whole document in canonical reading order
  (pages in manifest order, lines in page order, never across source
  files), keyed by qualified line identity. It replaces three partial
  sweeps — the intra-chunk sweep, the cross-chunk boundary pass and the
  page-seam pass — that each carried their own comparison base, and the
  seam pass's ambiguity skip on colliding bare ids is gone with them.
  Chunk finalization no longer reverts anything, so the pass compares
  every line's live pre-revert accepted correction on one basis, and a
  rejection pulls the whole hyphen unit via the shared derivation. Two
  lines adjacent inside a merged multi-block chunk but not adjacent on
  the page are no longer spuriously compared. Note: per-page
  `page_completed` events now report provisional correction counts —
  final decisions are made by the global pass; the report and the
  result remain authoritative.

- **Hyphen reconciliation is unit-driven (ADR-010, slice 2 complete).**
  A chunk's target lines and their resolved partners are handed to
  `derive_hyphen_groups` — the single derivation of "these lines travel
  together" — and each unit's joins reconcile with one walk in reading
  order. This replaces the two role-keyed passes (PART1→partner, then
  BOTH→forward) that re-derived the grouping from pointer fields at
  every step. The planner's block packing likewise merges blocks
  through the derivation (its per-link pointer walk is gone). Outcomes
  are unchanged; planner pinning, block packing, fallback closure,
  duplicate reverts and reconciliation all consume the one derivation.

- **The planner's over-cap chain cut is a recorded unit operation
  (ADR-010).** Severing the forward link of a chain longer than
  `max_lines_per_request` now goes through
  `saknussemm.core.units.split_forward_link` — the single writer for
  link removal — and each cut is recorded as a `HyphenSplit` on the
  `ChunkPlan` instead of happening as a silent pointer side effect
  inside the planner. Behaviour is unchanged; the cut is now visible
  to consumers of the plan.

- **Page images are keyed by page, not by file (breaking).**
  `run(source_images={source_name: ref})` gave every page of a multipage
  XML the SAME image — the vision producer looked at page 1's scan for
  every page but the first. The parameter is now
  `run(page_images={page_id: ref})` (page ids are document-unique,
  ADR-007), coverage is verified PER PAGE by the renamed
  `require_page_images` (raising `ConfigurationError`, no longer
  `ValidationError` — this is composition, not producer output), and a
  key matching no page (e.g. a legacy file-name key) is refused
  explicitly instead of silently reproducing the old behaviour.
- **Document-wide line lookups are keyed by `LineRef` (ADR-009,
  breaking).** New frozen dataclass `saknussemm.core.identity.LineRef`
  (`page_id`, `line_id` — fully qualifying under ADR-007's
  document-unique page ids) replaces the engine's three ad-hoc key
  shapes: hand-built composite strings (traces, pre-revert snapshots,
  finalization owners), raw `(page_id, line_id)` tuples (producer-op
  capture, cross-page hyphen indexes) and the string keys of
  `CorrectionResult.traces`, which now maps `LineRef → LineTrace`. A
  cross-page keying mistake is now a type error, not a runtime
  overwrite.
- **Recoverability is an allowlist (breaking for non-conforming
  providers).** The producer-attempt path re-raised eight known
  programmer-bug types and degraded EVERYTHING else to
  retry-then-OCR-fallback: a `RuntimeError` from a producer bug or a
  raw SDK transport exception nobody wrapped ended as a "successful"
  run with silently uncorrected text. Recoverable is now exactly what
  the retry classifier can route — `ProviderTransientError` and the
  `ValueError` family (`ValidationError`, `HyphenIntegrityError`,
  `json.JSONDecodeError`) — and everything else fails the run.
  Consequence: wrapping transport failures as `ProviderTransientError`
  is now the provider CONTRACT (`BaseProvider` docstring says MUST),
  enforced by failing loudly. ADR-008 revised.
- **The format travels with the document — no implicit ALTO default
  (breaking for hand-built manifests).** The parsers stamp
  `DocumentManifest.source_format` ("alto" / "page") and the engine
  derives the matching adapter from it at write time: a PAGE document
  now corrects end-to-end with no adapter injected (following the
  quickstart's PAGE hint used to rewrite PAGE with the ALTO rewriter).
  An injected adapter that contradicts the manifest's format raises the
  new `ConfigurationError` at run start; a hand-built manifest (no
  stamped format) reaching the write phase without an explicit adapter
  raises it too, instead of silently assuming ALTO.
- **Fallback accounting counts LINES, not chunks (breaking).**
  `CorrectionResult.fallback_count` (bumped once per fallen *chunk* — a
  rejected 20-line chunk reported "1") is renamed `fallback_chunks`, and
  two fields join it: `fallback_lines` — the number of lines whose
  terminal status is `FALLBACK` (manifest statuses are the authority:
  chunk fallbacks, acceptance-guard rejections and duplicate reverts all
  count) — and `fallback_reasons`, the aggregated reason prefixes per
  line. Consumers deciding "completed vs completed-with-fallbacks" must
  use `fallback_lines`: the old counter reported 0 for a guard-rejected
  line that silently kept its OCR text.
- **Provider errors join the single-root hierarchy.**
  `ProviderTransientError` and `ProviderPermanentError` (still importable
  from `saknussemm.core.protocols`) now derive from the new
  `saknussemm.errors.ProviderError`, itself a `CorrectionError` — the
  documented "catch the root once" contract previously excluded exactly
  the errors a mis-configured run raises first. Behaviour is unchanged:
  permanent rejections stay fatal for the run (explicit re-raise handlers
  precede every absorbing branch; pinned by `tests/test_error_taxonomy.py`).
- **Machine-readable error metadata.** Every error class carries a stable
  snake_case `code` and a `retryable` class flag so hosts route on
  structure instead of message text.

## [0.9.0] — 2026-07-16

### Changed

- **Re-versioned `1.0.0` → `0.9.0`, classifier `Production/Stable` →
  `Beta`.** Nothing was ever published to an index under `1.0.0` (the
  tag was never created — the release plan requires an independent
  external API review first, and the core refactor planned in
  `docs/history/PLAN-1.0-2026-07-15.md` will deliberately break the API
  beforehand). A version that promises a frozen surface while breaks are
  planned is dishonest; the 0.9.x series says what it is. The section
  below keeps its original date and content — it describes the same
  code, renumbered.

## [0.9.0 initial scope, formerly "1.0.0"] — 2026-07-15

First complete release candidate scope. Everything below shipped together —
nothing was ever published under an earlier name or number,
so there is no deprecation layer anywhere: final import paths and final
schemas from day one. The public surface is pinned by an executable
snapshot test (`tests/test_public_api_snapshot.py`); strict SemVer starts
at `1.0.0` (see `docs/versioning.md`).

Highlights: ALTO **and PAGE XML** backends producing one common
`DocumentManifest`; the §4 span edit protocol (`EditScript`,
`ReplaceLine`/`ReplaceSpan`, `MatchAnchor`→`RangeAnchor`); producers as
first-class citizens (`EditProducer`, deterministic `RulesProducer`, LLM
adapter, vision envelope with zero pixel I/O); the versioned
`CorrectionReport` as the single trace artefact; four frozen, fingerprinted
policies; byte-parity golden gates over a real BnF/Transkribus corpus.


### Audit remediation — 37 findings + per-wave adversarial reviews (2026-07-12 → 15)

The exhaustive audit (`docs/audit/AUDIT-2026-07-13.md`) and its
wave-by-wave remediation (`docs/history/PLAN-CORRECTIONS.md`) landed as part
of 1.0 — each fix reproduced by a failing test first, each wave reviewed
adversarially with its findings treated before the next.

### Fixed (audit F1-F12 + adversarial-review follow-ups, 2026-07-13)

- **Lines-never-merge, heuristic mode (Audit-F1).** The PART2 word-growth
  guard now protects EVERY reconcile accept path — explicit-with-subs,
  explicit-without-subs and heuristic — so a short heuristic PART2 can no
  longer absorb words from the following physical line.
- **Hyphen-chain revert atomicity (Audit-F2).** The duplicate-revert
  partner extension runs to fixpoint: whole 3+/4+-line chains
  (PART1→BOTH→…→PART2) revert together instead of leaving a mixed
  OCR+corrected pair.
- **Duplicate guard across seams (Audit-F3 + review).** The cross-chunk
  boundary pass and the page-seam pass compare PRE-revert accepted
  corrections (run-level snapshot), and boundary owners are the chunks
  that ACTUALLY finalized each line — granularity-descent sub-chunk
  seams (including single-chunk plans) are now covered.
- **Dry-run edit_script attribution (Audit-F4 + review).**
  ``_producer_ops`` is keyed by ``(page_id, line_id)`` so files reusing
  bare line ids no longer corrupt each other's ops; emitted ops carry an
  optional ``page_id`` and ``apply_edit_script(page_id=…)`` scopes a
  multi-file replay (additive — no report_version bump).
- **ALTO rewriter (Audit-F5/F6 + review).** The single-String BOTH guard
  is shared by ``_apply_subs`` and ``_subs_need_update`` (identity lines
  classify UNTOUCHED again); the slow-path rebuild trims edge whitespace
  before tokenizing (children tile the line exactly); the original HYP's
  WIDTH is parsed via the shared tolerant policy (an ``1e999`` value
  aborted the whole rewrite with an uncaught OverflowError).
- **Numeric parsing policy (Audit-F7/F8/F9).** ``parse_int_tolerant``
  treats inf/overflow-shaped values by contract — default in tolerant
  mode, ``ValueError`` in strict — shared by the ALTO ``_int_attr`` and
  the PAGE ``polygon_to_bbox`` (which skips non-finite pairs atomically).
- **Single-line invariant (Audit-F10).** The validator and the edit
  protocol reject the full ``str.splitlines`` separator repertoire
  (U+2028/U+2029, ``\x0b``, ``\x0c``, ``\x85``, …), not just ``\n``/``\r``.
- **Rules producer lexicon guard (Audit-F11).** Composed edits inside one
  token are re-validated as a whole against the lexicon; a composition
  that leaves it is rejected as a batch.
- **PAGE custom attribute verbatim slices (Audit-F12).** Kept groups are
  verbatim source slices (byte-identical round-trip for spacing).

### Changed (wave-3 review, 2026-07-13)

- ``CorrectionPipeline._write_outputs`` offloads ``rewrite_file`` /
  ``write_corrected`` / ``extract_texts`` to worker threads: a large
  rewrite no longer freezes the host's event loop (SSE keepalives,
  health checks). Observer events remain on the loop. ``run()`` is
  unchanged API-wise.

### Fixed (exhaustive audit — library correctness cluster, 2026-07-12)

- **Hyphen reconciliation.** The explicit-mode subs join stripped only
  ASCII `-`, so an explicit pair whose break char is `¬`/`⸗`/soft-hyphen
  (Fraktur/old print) never matched its `SUBS_CONTENT` and was
  systematically reverted to OCR — the join now strips the full
  `HYPHEN_CHARS` repertoire (matching the widened trailing-hyphen gate).
  Separately, an explicit-mode PART2 that absorbed trailing words from the
  next line (`"saires"` → `"saires du roi"`) could pass the boundary-word
  join and survive as a merged line; PART2 word growth now forces a
  fallback, preserving the "lines never merge" invariant.
- **Edit protocol (E2).** A zero-length insertion co-located with a
  replacement's start offset escaped the overlap check and, applied
  right-to-left in an ambiguous order, could leave a character the
  replacement was meant to remove — co-located span ops are now rejected as
  overlaps.
- **ALTO rewriter.** (a) A heuristically-detected PART1 (trailing dash, no
  explicit markup) no longer gets a synthesised `<HYP>` or a phantom
  trailing hyphen on the slow path — the conservative-heuristic invariant.
  (b) A single-`String` `BOTH` line keeps its backward `HypPart2` marker
  instead of the forward `HypPart1` write clobbering the same element.
  (c) *(byte change)* the slow-path rebuild reserves the trailing HYP's
  real width and repositions it flush at the line's right edge, so the
  child widths sum exactly to the line `WIDTH` with no overlap (previously
  the HYP kept its stale HPOS/WIDTH while the Strings were laid over a 4%
  estimate). The scripted byte-parity goldens move accordingly; identity
  goldens are unchanged.
- **LLM-response validator.** The hyphen fusion check now honours
  `target_line_ids`: in F8 window mode a hyphen pair sitting entirely in a
  chunk's *context* region can no longer fail the whole chunk (which
  discarded the chunk's valid *target* corrections on retry/fallback).
- **`PairingPolicy.same_block_only`** is page-qualified, honouring its
  documented cross-page guarantee when block ids repeat across pages (both
  pages exporting `TextBlock1`).
- **Adjacent-duplicate guard.** A run of three or more identical
  corrections now reverts every member; the loop used to skip the third.
- **PAGE `polygon_to_bbox`.** A half-malformed `x,y` pair (good `x`, bad
  `y`) is skipped atomically instead of leaving a dangling `x` that
  inflated the bbox.
- **`RulesProducer` lexicon guard** normalises through `ncfold` (NFC +
  casefold), so a decomposed (NFD) lexicon entry matches the parser's
  NFC-normalised tokens (previously a silently missed guarded correction).
- **Parsers refuse an id-less `TextLine`** (both ALTO and PAGE): a
  fabricated manifest id cannot round-trip through the rewriter (it matches
  on the real id attribute), so its correction would be silently dropped —
  the file is now rejected with `ParseError` instead. An id-less region
  under a `ReadingOrder` keeps document order (conservative bail).
- **Pipeline.** The cross-page duplicate-revert now reaches a hyphen
  partner living on another page, so a reconciled cross-page pair reverts
  atomically (never half OCR / half corrected). The page-seam duplicate
  pass compares a seam only within one source file. `CorrectionResult.
  edit_script` is rebuilt from the final per-line state (after
  reconciliation, acceptance and every revert), so a dry-run consumer
  replaying it reproduces the pipeline's own output — it never carries a
  stale op for a line reverted to OCR or reconciled to different text; an
  accepted-unchanged line keeps the producer's original op type. The
  producer-attempt error guard uses a denylist of genuine programming-error
  types, so a real bug (KeyError/TypeError/…) fails the run instead of
  silently degrading every chunk to OCR, while provider transport /
  validation errors still degrade.

### Fixed

- **P1-1 — recursive structure traversal.** Both parsers only visited
  *direct* children: ALTO ``TextBlock``s nested inside a ``ComposedBlock``
  and PAGE ``TextRegion``s nested inside another region were silently
  dropped — their lines never entered the manifest and were never
  corrected. Both parsers now walk the whole subtree in document order
  (each PAGE region still contributes only its direct lines, so nothing
  is double-counted). ALTO's container rule is unchanged (``PrintSpace``
  when present, else the whole ``Page``).

### Changed

- **P2-5 — configuration models validate invariants, not just types.**
  Every policy knob used to be a bare `int`/`float`: negative backoffs,
  zero chunk limits, out-of-range similarity ratios, temperatures outside
  [0, 2], a window overlap ≥ the window size, `target_line_ids` outside
  the chunk's `line_ids` and contradictory `DocumentManifest` totals were
  silently accepted, then produced arithmetic nonsense deep inside the
  pipeline. All config models (`ChunkPlannerConfig`, `GuardConfig`,
  `RetryPolicy`, `PairingPolicy`), `ChunkRequest` and `DocumentManifest`
  now fail fast at construction (`Field(ge/gt/le)` + cross-field
  validators). Policy fingerprints are unchanged (values didn't move).
  Deliberate exception, documented: *data* models fed from wild heritage
  XML (`Coords`, …) stay tolerant per F5 — a skewed scan's slightly
  negative position must not abort the file; geometry consumers treat
  degenerate boxes defensively instead.
- **P2-8 — `MatchAnchor.occurrence` is now `int | None = None`.** The old
  `int = 0` default conflated "producer said nothing" with "producer wants
  the first occurrence", making the first of a repeated pattern
  *inexpressible* (0 + multiple matches → rejected as ambiguous). `None`
  (the new default) requires uniqueness — same behaviour as before for
  producers that never set the field — while an explicit integer,
  **including 0**, always selects that occurrence. Aligns the
  implementation with §4.3's own wording ("plusieurs occurrences sans
  `occurrence` explicite → rejetée").
- **P2-9 — the E4 line budget counts characters actually changed.**
  `edit_line_max_changed_chars` used to sum `abs(len(replacement) −
  len(span))`: a length-neutral rewrite of 100 characters cost 0, so the
  knob bounded length drift, not the amount of text changed. Each span op
  is now costed by the size of its differing window after trimming the
  common prefix/suffix (0 for identical text, its length for a pure
  insertion, the larger side for a full rewrite — an upper bound on the
  Levenshtein distance). Length-neutral rewrites that previously slid
  under the budget are now rejected with `e4_line_budget`.
- **P1-2 — the default `PairingPolicy` is now geometric.** The historical
  default accepted *every* sequential hyphen-pair candidate — on layouts
  whose serialisation order diverges from reading order, a PART1 line
  could silently pair with a marginal note, an unrelated block, or an
  out-of-order line, shaping the LLM context with the wrong partner.
  Heuristic (trailing-dash) pairs are now vetted at pairing time: same
  block → candidate below within ``max_gap_line_heights`` (default 3.0)
  of the line's own height; cross-block same page → either a downward
  continuation with horizontal overlap (next block, same column) or an
  upward, horizontally disjoint, entirely-above jump (top of the next
  column — direction-agnostic, RTL-safe). Engine-asserted (explicit
  ``SUBS_TYPE``/``HYP``) pairs, cross-page seams and degenerate
  (coordinate-less) geometry are always trusted. New fingerprinted
  fields ``geometric_checks`` / ``max_gap_line_heights`` /
  ``max_rise_line_heights``; ``PairingPolicy(geometric_checks=False)``
  restores the historical behaviour exactly. Composite config
  fingerprint moves ``3a06d0a93ac4eedc`` → ``216aa712f1e99b79``.

### Added (provider error taxonomy — P0-1/P0-2)

- **`ProviderPermanentError`** *(in `saknussemm.core.protocols`, next to
  `ProviderTransientError`)* — the provider definitively rejected the
  request (invalid credentials, unknown model — the 4xx-non-429 family).
  The pipeline treats it as **fatal for the whole run**: never retried,
  never downgraded, never converted into an OCR fallback; it propagates
  out of `run()` before any output is written, like `CorrectionAborted`.
  Providers that don't wrap keep the old degrade-to-fallback behaviour.
- **P0-2 — the per-chunk `except Exception` is gone.** Only recoverable
  domain errors (`CorrectionError` subclasses) may be absorbed as a
  `chunk_error` event + continue; a programming error (KeyError, broken
  invariant, pydantic bug) now fails the run instead of letting it
  complete "successfully" with lines in an unknown state.

### Fixed (adversarial-review wave over the remediation itself)

- **Planner window walk survives config-validation bypass.** Pydantic's
  `model_copy(update=…)` bypasses the P2-5 validators, so
  `line_window_overlap >= line_window_size` spun the window loop forever
  (reproduced). A progress clamp restores the historical guarantee.
- **LINE-mode chain cap now UNLINKS the cut pair.** Truncating a
  longer-than-cap hyphen chain used to leave the pair straddling the cut
  still linked across two chunks — the validator skips such pairs and the
  reconciler could write across the boundary. Both sides now degrade to
  independent lines (OCR text preserved verbatim), so pair atomicity
  stays true by construction.
- **ALTO IDNEXT:** an empty-string block ID crashed the chain walk with a
  raw `KeyError`; an IDNEXT pointing outside the page (cross-page article
  continuation — a legitimate METS/ALTO pattern — or a margin block) now
  ends the chain instead of voiding the page's whole declared order.
- **ALTO margins:** without `PrintSpace` the recursive block walk swept
  margin-nested blocks (running heads, page numbers) into correction
  scope; they are explicitly excluded again in both container shapes.
- **Duplicate-ID gate covers the whole tree.** The rewriters match
  TextLine ids document-wide, but the parse gate only checked manifest
  scope: a margin line reusing a body line's ID passed upload validation
  and exploded at rewrite time, after the full producer spend. Both
  parsers now scan every TextLine id in the file.
- **Block IDs are page-scoped.** Per-page OCR exports that reuse
  `block_0`/`block_1` on every page of a file are legitimate (every block
  lookup downstream is page-scoped) — the per-file check refused them.
- **PAGE ReadingOrder: partial declarations are ignored.** A declaration
  covering only some regions used to yank the referenced regions ahead of
  everything else, reordering text it said nothing about; only a
  declaration covering every id-bearing region now reorders (same
  conservative rule as the IDNEXT fallbacks).
- **Identical line boxes = synthetic geometry.** Exports that copy the
  block's coords onto every line no longer have their heuristic hyphen
  pairing silently disabled by the P1-2 geometric vetting.
- **Duplicate reverts are pair-atomic and cover page seams.** Reverting
  one member of a reconciled hyphen pair left a mixed OCR+corrected pair
  (the state `reconcile_hyphen_pair` forbids) — the revert now extends to
  the partner (`adjacent_duplicate_pair_atomicity`), the revert logic is
  one shared helper instead of two divergent copies, the P2-6 pass is
  restricted to actual chunk-boundary pairs (no redundant re-checking),
  and page-boundary seams are checked too (the same leak one level up).
- The explicit-pair bypass in `PairingPolicy` is documented precisely:
  the opt-in legacy vetoes (`same_block_only`, `max_vertical_gap`) still
  apply to explicit pairs; only the geometric vetting is bypassed.
- `docs/edit-protocol.md` updated to the new `occurrence` semantics.

### Fixed (guards & budgets)

- **P1-8 — `max_input_chars_per_request` is now a real bound.** Only PAGE
  and BLOCK honoured the char budget; a WINDOW of pathologically long
  lines blew straight past it and LINE mode could follow an unbounded
  hyphen chain. Windows are now bounded by BOTH the line count and the
  char budget (the overlap step follows the actual window end so a
  budget-shortened window never skips lines — full windows keep the
  historical fixed step exactly), and LINE chains are capped at
  `max_lines_per_request`. Two documented atomic exceptions may
  overshoot: a hyphen chain (splitting corrupts reconciliation) and a
  single line longer than the whole budget. The budget's semantics are
  now documented precisely: it counts RAW OCR text, not the enriched
  request envelope — size it with headroom.
- **P2-6 — duplications straddling a chunk boundary are now caught.**
  Adjacent-duplicate detection ran per chunk on that chunk's target
  lines only, so two document-adjacent lines owned by different chunks
  were never compared. A page-level pass after all chunks re-checks
  every adjacent pair in reading order (idempotent over the intra-chunk
  results) and reverts both sides of a boundary duplicate to OCR with
  `adjacent_duplicate_detected`.
- **P2-7 — guards stage-strictness doc contradiction resolved.**
  `guards.py` called Stage A "the strictest" while the config documents
  Stage A as more permissive on PART1 growth (2 words vs 1 at Stage B).
  The docs now say what the code does: Stage A carries the most
  aggressive *remedy* (whole-chunk retry), Stage B the strictest
  *thresholds* — a maintainer can no longer tune them backwards on the
  strength of the old sentence.

### Added

- **P1-1 — explicit reading order.** PAGE ``ReadingOrder`` declarations
  (nested Ordered/Unordered groups, ``RegionRefIndexed`` by ``@index``)
  and ALTO ``IDNEXT`` block chains now drive block/region order — hence
  ``line_order_global``, prev/next neighbour context and hyphen pairing —
  instead of raw XML serialisation order (wrong on multicolumn layouts
  whose declaration diverges). Conservative by construction: regions not
  covered by the declaration follow in document order; an inconsistent
  declaration (dangling ref, cycle, converging IDNEXT chains) falls back
  to document order entirely — the library never guesses. Corpus files
  whose declaration matches document order (all of ``examples/``) produce
  byte-identical output.

- **`DuplicateIdError`** *(top-level, subclasses `ParseError`)* — P0-5
  identity-uniqueness invariant. A source file whose Page / TextBlock /
  TextLine IDs are not unique is now refused explicitly instead of being
  silently mis-corrected: previously, two `TextLine` elements sharing an ID
  made the rewriters apply the *last* parsed manifest to **both** physical
  lines (last-write-wins on an internal `line_id` dict), destroying one
  line's text. Enforced in four layers: both format parsers (right after
  manifest construction), `CorrectionPipeline.run()` (at the door, so
  hand-built manifests get the same guarantee — including cross-file
  `page_id` collisions), both rewriters, and both `extract_output_texts`.
  Duplicate IDs across *different* source files remain legitimate (every
  downstream lookup is scoped to one file). Additive change: existing
  `except ParseError` / `except CorrectionError` call sites keep working.

### v1.0 normative corrections (SPECS_LIB_V2 §7)

- **F3** — the parser tolerates comments / processing-instructions among a
  `TextLine`'s children (they carry a callable `tag`); a trailing comment
  no longer aborts the whole file.
- **F5** — `_int_attr` parses float-valued coordinates (`"123.0"`, `"800.9"`)
  via `int(float(...))`, truncating toward zero. Non-numeric values still
  raise.
- **F6** *(byte change)* — slow-path token geometry: the 0.6 space weight now
  enters the total weight and rounding is spread by cumulative rounding.
  Widths still sum exactly to the line width; the final token only absorbs
  residual rounding instead of every space's accumulated deficit. Changes
  output bytes on slow-path lines with interior spaces (UNTOUCHED /
  SUBS_ONLY / FAST paths unaffected).
- **F13** — `GuardConfig` (frozen, injectable) gathers every anti-migration /
  acceptance threshold from the three guard stages; defaults reproduce the
  historical constants byte-for-byte. `FrozenPolicy.policy_fingerprint()`
  gives a stable hash for provenance (§11). Threaded through `check_line`,
  `check_adjacent_duplicates`, `reconcile_hyphen_pair`,
  `validate_llm_response`, and `CorrectionPipeline(guard_config=…)`.
- **F7** — `PairingPolicy` (frozen, injectable) makes hyphen pairing a seam;
  default reproduces the historical purely-sequential pairing. Forwarded
  through `build_document_manifest` / `parse_alto_file`.
- **F2** *(byte change)* — a changed `CONTENT` drops the now-stale `WC`/`CC`
  confidences (fast path, per changed String); the slow-path rebuild
  recycles only `ID` and `STYLEREFS` (§6.1 whitelist), inherits `VPOS`/
  `HEIGHT` from the line, recomputes `HPOS`/`WIDTH`, and never carries
  `WC`/`CC`/`SUBS_*`. Changes output bytes on slow-path lines and on
  fast-path Strings whose CONTENT changed.
- **F4** — the UNTOUCHED comparison strips both sides, matching the parser's
  `ocr_text` derivation; a line with a trailing `<SP/>` under identity
  correction now takes the UNTOUCHED path instead of being rewritten.
- **F9** — `RetryPolicy` (frozen, injectable) externalises the temperature
  ramp, attempt cap, backoff bases and per-chunk budget.
  `RetryPolicy.default()` reproduces the historical ramp (0.0/0.3/0.5, cap 3)
  to the byte; `RetryPolicy.deterministic()` sets every temperature to 0.
  `CorrectionPipeline(retry_policy=…)`.
- **F10** — `CorrectionPipeline.run(should_abort=…)` cooperative cancellation,
  probed between pages and chunks; raises `CorrectionAborted` (new
  `saknussemm.errors` module, `CorrectionError` root) before any output is
  written. In-flight provider calls are not interrupted.
- **F1** *(behaviour change on failure paths)* — a chunk whose retry budget is
  exhausted is re-planned one granularity finer (PAGE→BLOCK→WINDOW→LINE) and
  retried (`chunk_downgraded` event), bounded by `RetryPolicy.per_chunk_budget`
  (default 6). Only lines whose finest-grain chunk still fails fall back to OCR;
  a transient burst now recovers instead of reverting the whole chunk. New
  `chunk_downgraded` event added to the SSE contract.
- **F8** — overlapping windows distinguish *target* vs *context* lines
  (`ChunkRequest.target_line_ids`): each line is corrected in exactly one
  window (its best-following-context window), hyphen pairs kept together;
  overlaps become pure context. No effect on PAGE-granularity documents.
- **F14** *(pre-1.0 break)* — `BaseProvider.complete_structured` returns
  `(dict, Usage | None)`. New `Usage` model; `CorrectionResult.usage`
  aggregates the run; per-chunk tokens on the `chunk_completed` event.
- **Error hierarchy (§8.4)** — `saknussemm.errors`: `CorrectionError` root with
  `ParseError`, `ValidationError` (both also `ValueError`), `CorrectionAborted`;
  `HyphenIntegrityError` is now a `ValidationError`. `validate_llm_response`
  raises `ValidationError`.
- **CorrectionReport + dry-run (§9)** — the per-line trace is promoted to a
  public, versioned `CorrectionReport` (`report_version` "1.0"), returned on
  `CorrectionResult.report`. `run(apply=False)` runs the full pipeline
  (production, guards, reconciliation, in-memory rewrite) but never calls the
  `OutputWriter` — the report is the deliverable.
- **Provenance (§11)** — the corrected XML's `processingStep` now records the
  library version and a configuration fingerprint
  (`RetryPolicy`+`GuardConfig`+`ChunkPlannerConfig`) alongside provider/model.
- **py.typed + `mypy --strict` (F12/§8.3)** — PEP 561 marker shipped in the
  wheel; the package passes `mypy --strict` (new `saknussemm-types` CI job).
- **F12 (relocation)** — `Provider`, `JobStatus`, `JobManifest` (and its
  `images` map) moved to the backend (`app.schemas.job`); the vestigial
  `status` field was dropped from `PageManifest`/`DocumentManifest`. The core
  keeps only the domain enums (`LineStatus`, `ChunkGranularity`, `HyphenRole`,
  `PipelineEventType`). Top-level public surface is now 34 symbols.
- **F11** — the algorithm tests were repatriated into
  `packages/saknussemm/tests`; the package gates its own coverage (~86%, gate
  85%) and its CI job runs pytest with `--cov=saknussemm`.

### Span edit protocol (SPECS_LIB_V2 §4 / §5)

- `saknussemm.core.editing` — `EditScript` of `ReplaceLine` / `ReplaceSpan`
  ops (no structural op ⇒ invariant I2 by type). `RangeAnchor` (offsets)
  and `MatchAnchor` (exact substring) normalise to a single `RangeAnchor`
  against the canonical text; unfound / out-of-range / ambiguous anchors
  reject the op (I2 fallback). `apply_edit_script` enforces E1–E5 (E6 stays
  the downstream three-stage matrix). **E4/E5 gate `replace_span` only** —
  `replace_line` keeps E1/E3/conflict, so re-expressing today's whole-line
  response is byte-identical (proved on sample.xml / X0000002.xml).
- `saknussemm.producers.rules` — deterministic `RulesProducer` (§5.3):
  literal/regex substitutions with an optional lexicon guard, emitting
  `replace_span` + exact `RangeAnchor`. Zero deps, byte-reproducible; the
  first real span emitter and a free pre-LLM pass. `default_french_ocr_
  rules()` ships ſ→s and ﬁ/ﬂ ligatures.
- `EditProducer` contract (§5.1) with `wants_geometry` / `wants_image`;
  `LLMEditProducer` adapts a `BaseProvider` (emits `replace_line` + Usage).
  Vision envelope (§4.1): `LineGeometry` + opaque `ImageRef` copied by the
  compiler only on request — the library opens no pixel (**I4**, enforced
  by an AST contract test). `require_source_images` raises `ValidationError`
  for a `wants_image` producer run without images.
- Pipeline: producers return `EditScript`s that are normalised and applied
  through `apply_edit_script` (byte-parity via the golden gate);
  `CorrectionResult.edit_script` surfaces the normalized script, and a dry
  run (`apply=False`) returns it as the deliverable.
- **BREAKING — §5.1 resorption.** `CorrectionPipeline` is constructed
  around an `EditProducer`; `run()`/`run_sync()` no longer take
  `api_key`/`model`/`provider_name` (credentials live inside the producer;
  the provenance labels are constructor state). `run(source_images=…)`
  forwards opaque image refs, checked at start-up for `wants_image`
  producers. `CorrectionPipeline.for_provider(provider, api_key=…,
  model=…, provider_name=…)` is the one-call migration for the LLM case.
  The pipeline still drives the retry ramp (it hands each attempt a policy
  whose first temperature is that attempt's — hyphen 0.0 pin included), so
  retry classification, temperatures and output bytes are unchanged. A
  producer may declare `requires_full_coverage = False` (rules engine: no
  op == no edit); LLM producers keep strict 1:1 coverage → retry. The
  prompt/schema seam moved into `LLMEditProducer`; the import-contract's
  pinned core exceptions are now `_default_format_adapter` + `for_provider`.
- **BREAKING — JobTrace → CorrectionReport unification (§9).** `JobTrace`
  is deleted; `trace.json` and the backend's `/trace` endpoint carry the
  versioned `CorrectionReport` verbatim (`report_version`, `run_id` ==
  job id, `total_lines`, `lines`). Backend `JobManifest` gains `report`;
  the frontend `TraceData` type mirrors the report.

### PAGE XML support (SPECS_LIB_V2 §6.2 / §6.3, P1–P7)

- New `formats/page/` backend (parser, rewriter, adapter) producing the
  **same `DocumentManifest`** as ALTO — the pure core is reused unchanged.
- **P1** — geometry is polygons. `Coords@points` is kept verbatim on the
  new `Coords.polygon` field; the enclosing bbox is derived for the
  planner. Geometry is **never rewritten** (no geometric slow path).
- **P2/P3** — canonical line text = the minimal-`@index` line `TextEquiv`
  (absent index ≡ 0), else the space-joined `Word` Unicode; NFC + strip.
  On rewrite the canonical `TextEquiv` is updated (Unicode + `PlainText`),
  its stale `@conf` dropped and alternative `TextEquiv` removed.
- **P4** — words: fast path (count unchanged) updates each `Word`'s
  `TextEquiv` in place and keeps its `Coords`; slow path (count changed)
  drops the `Word` children (text lives at line level) and counts the lost
  granularity.
- **P5** — heuristic-only hyphenation over `- ¬ ⸗ U+00AD` with chained
  `BOTH` detection; the source hyphen character is preserved verbatim on
  rewrite (E5 extended — no `¬` → `-`). The core reconciler's PART1 check
  now accepts the whole repertoire (`-` retained ⇒ ALTO byte-parity intact).
- **P6** — `custom` microformat: structural groups (`readingOrder`,
  `structure`) preserved verbatim; offset-anchored groups (`textStyle`,
  tags with `offset`/`length`) dropped when the line text changes and
  counted.
- **P7** — `make_safe_parser` throughout (the grep contract already spans
  `formats/**`); provenance as a `MetadataItem` on 2019+ schemas, else
  appended to `Metadata/Comments`; no wall-clock timestamp ⇒ deterministic
  output.
- **Shared pairing** — the second-pass hyphen linker, page-id
  disambiguation and cross-page linking moved to the pure `core.pairing`
  (both formats call it; §6.3 parity holds by construction).
- **`CorrectionReport.format_losses`** — optional aggregate of
  format-specific granularity losses (`words_dropped`,
  `custom_offset_stripped`, …), fed by `PageRewriterMetrics.as_losses()`.
  Additive/optional ⇒ `report_version` stays `"1.0"`.
- Validated on the real corpus (OCR17plus triplets, NewsEye columnar
  press): LaFayette parses 13 lines byte-identical to its ALTO4 export;
  identity round-trip is text-stable; synthetic fixtures pin `@index`,
  `@conf`, alternatives, `PlainText`, `custom` offsets, the 2019 namespace
  and the ⸗ Fraktur hyphen.

### Renamed (§14 — pre-publication, no aliases)

- Distribution **alto-core → saknussemm**, import package **alto_core →
  saknussemm**. *Saknussemm* — the printed errata leaf bound into books —
  is literally what this library produces, carries the heritage domain,
  and survives the PAGE XML extension (v1.1) where "alto" would become a
  lie. Nothing was ever published under the old name, so there is no
  deprecation layer: final import paths from day one. The repository slug
  (URLs in project metadata) still reads alto-llm-corrector until the
  GitHub repository itself is renamed. The `processingStep` provenance
  brand written into corrected XML is now `saknussemm` (no effect on the
  byte-parity corpus: its files carry no `<Processing>` element).

### Post-audit corrective rounds (same release)

- **F1×F8 fixed** — the granularity descent re-plans a failed chunk's
  *target* lines only; context lines are no longer stolen from their own
  window and corrected at a finer grain.
- **F1×F10 fixed** — `should_abort` is probed inside the descent (before
  each sub-chunk) and `CorrectionAborted` is never converted into a
  `chunk_error` event.
- **F8 (spec letter)** — `validate_llm_response(target_line_ids=…)`: the
  1:1 count is enforced on targets; a missing context-line output is not an
  error. Per-entry structural checks stay strict; hyphen integrity runs
  over the target set. `None` keeps the historical exact-count contract.
- **`run_sync()` (§8.1)** — synchronous façade over `run()`; refuses a
  running event loop.
- **`ChunkPlannerConfig` frozen (§8.2)** — now a `FrozenPolicy` with
  `policy_fingerprint()`, like the other three policies.
- **Provenance fingerprint unified (§11)** — public
  `CorrectionPipeline.config_fingerprint()`, composed from the four
  policies' public `policy_fingerprint()` values (sorted-JSON sha256/16)
  and now covering `PairingPolicy` (provenance-only ctor param).
  Reproducible by consumers from the public API.
- **Slow-path SP geometry recomputed** *(byte change)* — SPs no longer
  recycle stale pre-correction HPOS/WIDTH; their geometry comes from the
  same `_compute_geometry` pass as the surrounding Strings (contiguous
  layout).
- **§6.1 whitelist extended with `STYLE`** — inline styling (bold/italics)
  is preserved on the slow path alongside `ID`/`STYLEREFS`. The spec names
  only the latter two, but its doctrine targets data *invalidated* by the
  text change — styling is not; dropping it destroyed real formatting on
  the non-regression corpus. Flagged for spec ratification.
- **F6 degenerate floor fixed** — the min-1 deficit is repaid across
  multiple donors; the exact-sum invariant survives every feasible width.
- **F7 cross-page gap** — `max_vertical_gap` is skipped for cross-page
  candidates (VPOS restarts per page).
- **F14 event semantics** — `chunk_completed` reports the chunk's total
  usage across all attempts, not just the final successful call.
- **Byte-parity gate (§13 DoD)** — `test_byte_parity_corpus.py` pins
  sha256 golden hashes of two deterministic scenarios over the corpus.
  Verified against the pre-v1.0 baseline (commit 8c4789c): identity
  corrections are BYTE-IDENTICAL; scripted corrections differ only on
  documented F2 (WC/CC) and F6/§6.1 (geometry) line classes.

### Changed
- **Retry policy on HTTP 4xx (other than 429) is now non-retryable.**
  The previous class-name allowlist (`exc.__class__.__name__ ==
  "HTTPStatusError"`) caused `401`, `403`, `404`, `422` to be retried
  3 times with exponential backoff — a waste, because client errors
  (bad API key, wrong model, schema rejection) don't heal on retry.
  The classifier now routes on `isinstance(exc,
  ProviderTransientError)`, and providers' HTTP wrapper deliberately
  leaves 4xx-non-429 errors un-wrapped, so they reach the classifier
  as non-retryable and the chunk falls back to OCR source on the
  first failure. Pinned by
  `test_pipeline_classifies_client_http_4xx_as_non_retryable`.
  `5xx`, `429`, and transport-level failures (timeout, network,
  protocol) retain the previous 3-attempt exponential-backoff
  behavior.
- Clarified in the `### Added` section of `[0.1.0a1]` which symbols
  are re-exported at the package root (`from saknussemm import …`)
  versus the ones that are sub-module-only. The technical contract
  is unchanged — every symbol previously listed remains importable
  from its canonical path. (roadmap L5 / B5)

### Added
- `ProviderTransientError.status_code: int | None` — when the
  underlying transport failure was an HTTP error, the originating
  status code is preserved on the wrapped exception so observers can
  route on 429 vs 503 vs 500 without parsing the message. `None` for
  transport-level failures (timeout, network, protocol). The full
  underlying exception remains reachable via `__cause__` for callers
  that need response headers or the request URL.

### Documentation
- Public Pydantic models (`LineManifest`, `DocumentManifest`,
  `BlockManifest`, `PageManifest`, `JobManifest`, `ChunkPlannerConfig`,
  `LLMLineInput`, `LLMLineOutput`, `ModelInfo`, `Coords`) and enums
  (`JobStatus`, `LineStatus`, `ChunkGranularity`, `Provider`,
  `HyphenRole`) now carry a one-line docstring. PyPI consumers get
  IDE help/intellisense out of the box. (roadmap L5 / A5)

### CI / Release
- Single source of truth for the smoke-import check:
  `packages/saknussemm/_smoke_imports.py` iterates `saknussemm.__all__`
  and is invoked by `.github/workflows/ci.yml`,
  `.github/workflows/publish-saknussemm.yml`, and
  `scripts/release-saknussemm.sh`. Drift between the three is now
  impossible. (roadmap L5 / B6)
- Added `Programming Language :: Python :: 3.13` classifier
  (`requires-python = ">=3.11"` already permitted 3.13). (roadmap L5 / P3)

## [0.1.0a1] — 2026-05-25 (internal milestone — never published)

The extraction milestone under the working name `alto-core`. Kept for the
historical record; **this version never reached any index**, and every
item below is folded into 1.0.0 above.

Initial alpha release.

### Added

> **Import paths.** Each section below documents the path the listed
> symbols live at. Most are sub-module imports, e.g.
> `from saknussemm.formats.alto.rewriter import RewriterMetrics`. The shorter
> set of names re-exported at the package root —
> `from saknussemm import CorrectionPipeline, BaseProvider, ...` — is
> defined exclusively by `saknussemm.__all__`. Symbols listed below
> that are NOT in `__all__` (e.g. `RewriterMetrics`, `ReconcileMetrics`,
> `plan_page`, `validate_llm_response`, `AcceptanceResult`, …) are
> sub-module-only: they remain importable from their canonical path,
> but `from saknussemm import RewriterMetrics` will raise `ImportError`.

- `saknussemm.formats.alto`: ALTO XML parsing and rewriting (v2/v3/v4), with
  the Hyphenation Reconciler.
  - `parse_alto_file`, `build_document_manifest` *(top-level)*
  - `rewrite_alto_file`, `extract_output_texts` *(top-level)*, `RewriterMetrics` *(sub-module only)*
  - `enrich_chunk_lines`, `reconcile_hyphen_pair`, `ReconcileMetrics`,
    `classify_reconcile_outcome`, `should_stay_in_same_chunk` *(all sub-module only)*
- `saknussemm.core`: chunk planning, LLM-response validation,
  per-line acceptance policy, and `CorrectionPipeline`.
  - `CorrectionPipeline`, `CorrectionResult`, `sanitize_error` *(top-level)*
  - `plan_page`, `downgrade_granularity` *(sub-module only)*
  - `validate_llm_response` *(sub-module only)*
  - `check_line`, `check_adjacent_duplicates`, `AcceptanceResult` *(all sub-module only)*
- `saknussemm.core.protocols`: ports consumers implement.
  - `BaseProvider`, `PipelineObserver`, `OutputWriter` *(top-level)*
  - `OUTPUT_JSON_SCHEMA`, `SYSTEM_PROMPT` *(top-level, home: `saknussemm.producers.llm`)*
- `saknussemm.core.schemas`: domain Pydantic models (manifests, enums, LLM
  payloads, traces, model info). Top-level re-exports cover the
  models consumers typically reach for — see `saknussemm.__all__`.

### Public API guarantees (alpha caveat)
- Importable via the top-level package: `from saknussemm import
  CorrectionPipeline, BaseProvider, parse_alto_file, …` (full list
  in the package `__all__`).
- Each sub-module declares its own `__all__`.
- ARCHITECTURE.md ADR-006: the pipeline never logs by itself — every
  diagnostic is an `observer.on_event(...)` so hosts route them as
  they wish.
- Snapshot tests on a 566-line corpus pin byte-identical rewrite
  output across the 35+ commits of the refactor that produced this
  release.

### Known limitations
- API is still alpha; breaking changes possible until 1.0.
- `CorrectionPipeline.run` accepts `provider_name`/`model`/`api_key`
  individually (server-side legacy); a future release will likely fold
  them into the injected `BaseProvider`.

[Unreleased]: https://github.com/maribakulj/alto-llm-corrector/compare/saknussemm-v0.1.0a1...HEAD
[0.1.0a1]: https://github.com/maribakulj/alto-llm-corrector/releases/tag/saknussemm-v0.1.0a1
