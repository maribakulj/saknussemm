# La vie d'une ligne

À quoi sert cette page : répondre à *« pourquoi cette ligne n'a-t-elle pas été
corrigée ? »* sans ouvrir le code. C'est la question de diagnostic la plus
fréquente, et la réponse traversait dix-sept modules sans qu'aucun document ne
la rassemble.

Trois choses à savoir d'abord :

- l'identité d'une ligne est **toujours** `(page_id, line_id)` ; un `line_id`
  nu se répète légitimement d'un fichier à l'autre (`ADR-001`, `ADR-007`) ;
- **les lignes ne fusionnent jamais** et **aucun texte ne migre** d'une ligne à
  l'autre : c'est l'invariant que tout le reste protège ;
- au moindre doute, la ligne **retombe sur son texte source**. Un repli n'est
  pas un échec du système : c'est le système qui refuse de deviner ;
- et quand il ne peut ni deviner ni douter — quand la correction tient
  debout et qu'il n'a aucun moyen de l'établir — il la **livre en le
  disant** : `review_required`. C'est le §3 bis.

---

## 1. Le trajet

```
CorrectionPipeline.run
│
├─ preflight            refuse ce qui ne peut pas démarrer (6 contrôles)
├─ indexing             une passe : traces, index page-qualifié, nb d'unités
│
├─ POUR CHAQUE PAGE ─── PageDriver.process_page
│  │
│  ├─ planner.plan_page          PAGE → BLOCK → WINDOW → LINE
│  │                             une unité de césure n'est jamais coupée
│  ├─ (routing)                  hors chemin par défaut — voir §5
│  ├─ (batching)                 hors chemin par défaut — voir §5
│  │
│  └─ POUR CHAQUE CHUNK ─── driver._run_chunk
│     │
│     ├─ attempt._attempt_chunk         jusqu'à 3 essais, rampe de température
│     │  ├─ hyphenation.enrich_chunk_lines   ce que le producteur voit
│     │  ├─ producer.produce                 ← le seul appel sortant
│     │  ├─ editing.apply_edit_script        E1–E5, protocole d'édition
│     │  └─ validator.validate_llm_response  ÉTAGE A, avant tout retry
│     │
│     ├─ succès → outcome._finish_successful_chunk
│     │  ├─ reconcile._reconcile_chunk_hyphens   ÉTAGE B
│     │  ├─ acceptance._apply_line_acceptance    ÉTAGE C
│     │  └─ traces._finalize_chunk_traces
│     │
│     └─ échec → descente d'un cran de granularité, ou repli sur la source
│
├─ finalize._finalize_document    quatre passes, dans CET ordre
│  ├─ 1. doublons adjacents + migration de frontière (document entier)
│  ├─ 2. préservation du caractère de coupure
│  ├─ 3. politique de perte (strict / token_realign)
│  └─ 4. renvoi en revue — n'écrit aucun texte, voir §3 bis
│
├─ decisions.derive_decision_set  la décision devient immuable
├─ rendering._render_outputs      réécriture + invariant de projection
└─ report / result                ce que l'appelant reçoit
```

Où lire la réponse, côté appelant :

```python
d = result.decisions.by_ref[LineRef(page_id="P1", line_id="TL7")]
d.status          # CORRECTED, REVIEW_REQUIRED ou FALLBACK
d.fallback_reason # le code du §3, suivi éventuellement de ": détail"
d.review_reasons  # les codes du §3 bis — un tuple, pas un code
result.fallback_reasons           # agrégat par code, pour tout le run
result.review_lines               # combien de lignes sont à relire
result.review_reasons             # agrégat par code, pour tout le run
result.report.edit_rejections     # les ops refusées par le protocole d'édition
```

---

## 2. Les trois étages de garde

Ils sont **délibérément trois**, à trois moments, et ils se règlent ensemble
(`GuardConfig`). Resserrer un seul étage peut ouvrir un trou entre deux.

| étage | quand | où | ce qu'il juge | ce qu'il fait en cas de refus |
|---|---|---|---|---|
| **A** | avant tout retry | `validator._check_pair_drift` | la dérive d'une paire de césure dans la réponse brute | lève → **nouvel essai** |
| **B** | après la réponse validée | `hyphenation.reconcile_hyphen_pair` | la cohérence des deux moitiés d'un mot coupé | **repli des deux membres** |
| **C** | après la réconciliation | `guards.check_line` | la ligne seule et ses voisines — y compris, depuis `VR-11`, un membre de paire que B vient d'accepter (plancher et marge seulement : la coupe du mot reste à B) | **repli de la ligne** — de l'unité entière pour un membre de paire |

Les jumeaux entre A et B (`pair_drift_part1_word_growth` = 2 contre
`part1_max_word_growth` = 1) ne sont pas une duplication : A est plus permissif
parce qu'un retry est moins cher qu'un repli.

**Le renvoi en revue du §3 bis n'est pas un quatrième étage**, et le confondre
avec un étage est l'erreur à éviter. Un étage RETIRE une correction ; le
renvoi la garde et se contente de dire que la bibliothèque ne peut pas
l'établir. Aucun octet livré n'en dépend.

---

## 3. Toutes les raisons de repli

La liste est close, et pas seulement en prose :
`saknussemm.core.decide.FALLBACK_REASON_CODES` la porte, et
`tests/test_the_fallback_reasons_are_a_closed_set.py` refuse un code que le
moteur émettrait sans qu'il y figure — comme il refuse un code déclaré ici et
absent de cette page. Un code inconnu dans un rapport est donc un défaut de
la bibliothèque, pas une raison inédite.

### Étage C — la ligne et ses voisines (`guards.check_line`)

| code | ce qu'il veut dire |
|---|---|
| `too_different_from_source` | la correction ne ressemble plus assez à la ligne OCR |
| `closer_to_previous_line` | la correction ressemble plus à la ligne du dessus qu'à la sienne |
| `closer_to_next_line` | idem, ligne du dessous |
| `closer_to_another_line` | idem, une autre ligne de la page — seulement sous `GuardConfig(attachment_scope="page")`, qui étend la marge des deux voisines à toute la page |
| `absorbs_previous_line` | la correction est « ligne précédente + cette ligne » concaténées |
| `absorbs_next_line` | idem vers l'aval |

Les trois derniers détectent la même faute — du texte a migré — sous trois
formes que le modèle produit réellement.

### Étage B et césure — l'unité, jamais un membre seul (`ADR-010`)

| code | ce qu'il veut dire |
|---|---|
| `hyphen_pair_fallback` | la réconciliation a refusé la paire : les deux moitiés reviennent à la source |
| `pair_drift_fallback` | l'étage A (validation, avant acceptation) a refusé cette paire jusqu'au dernier essai — moitié rendue vide, PART1 qui gonfle, PART2 qui s'effondre, mot recollé — et la paire seule est retombée sur l'OCR pour que le reste du chunk passe. Avant, le chunk entier retombait |
| `hyphen_partner_fell_back` | le partenaire direct est déjà tombé ; une paire mixte ne peut pas survivre |
| `hyphen_unit_fallback` | un membre est tombé pour sa propre raison (depuis `VR-11`, aussi un refus de l'étage C sur un membre réconcilié : `too_different_from_source`, `closer_to_*`), celui-ci est tiré avec lui |
| `orphan_hyphen_completed` | la ligne annonce une coupure sans partenaire visible, et la correction l'a complétée |

`hyphen_unit_fallback` est une **conséquence**, pas une décision : c'est ce qui
permet au rapport de distinguer la ligne fautive de celles qu'elle entraîne.

### Passes document-wide (`core/finalize.py`)

| code | ce qu'il veut dire |
|---|---|
| `adjacent_duplicate_detected` | deux lignes voisines, sources distinctes, corrections quasi identiques |
| `adjacent_duplicate_pair_atomicity` | membre d'unité tiré par un doublon |
| `boundary_migration_forward` | un mot entier a traversé la couture vers l'aval |
| `boundary_migration_backward` | idem vers l'amont |
| `format_loss: …` | `LossPolicy.strict` : la correction ne peut pas se projeter sans perdre la granularité `Word` |
| `rejected` | le défaut de `check_line` si une branche de refus ne nommait pas sa raison — aucune ne le fait aujourd'hui |
| `format_loss_pair_atomicity` | membre d'unité tiré par une perte de format |
| `token_realign: …` | `min_alignment_score` : les tokens ne s'alignent pas assez, ou un déplacement de mot est suspecté |
| `token_realign_pair_atomicity` | membre d'unité tiré par un refus d'alignement |

Sous `LossPolicy` par défaut (`REPORT`), les quatre derniers ne se produisent
jamais : la perte se projette, est comptée et attribuée ligne à ligne.
`token_realign` préserve la correction refusée dans `report.sidecar`.

### Niveau chunk (`core/outcome.py`)

| code | ce qu'il veut dire |
|---|---|
| `all_attempts_exhausted: …` | les essais sont épuisés, et aucune granularité plus fine n'aurait aidé |
| `chunk_error_absorbed: …` | une erreur de domaine récupérable a été absorbée pour laisser le run continuer |

Le détail qui suit `: ` porte la famille de l'échec, et la distinction est
utile : **`transport`** veut dire que le modèle n'a jamais été interrogé (429,
réseau) et que réessayer plus tard marcherait ; **`producer_output`** veut dire
qu'il a répondu sans tenir le contrat. Confondre les deux fait changer de
modèle quand il fallait arrêter de saturer son propre quota.

---

## 3 bis. Toutes les raisons de renvoi en revue

Un renvoi n'est **pas** un repli, et confondre les deux est la seule
erreur de lecture qui compte ici :

| | repli | renvoi |
|---|---|---|
| le texte livré | la source | **la correction** |
| ce que le run dit | « j'ai refusé cette correction » | « je l'ai livrée et je ne peux pas l'établir » |
| l'octet dans le fichier | change | **ne change pas** |
| où c'est écrit | `fallback_reason`, un code | `review_reasons`, plusieurs |

Pourquoi l'état existe : les gardes de l'étage C **comparent des
caractères et n'ont aucune notion de sens**. Sur douze contre-exemples
passés dans la vraie `check_line`, les douze sont acceptés aux deux
seuils — négation supprimée 0,8955, date changée 0,9388, montant tronqué
0,9643, ligne voisine recopiée mot pour mot 0,8852. Aucun réglage ne
ferme cette famille. Ranger ces lignes sous `CORRECTED` ferait affirmer à
la bibliothèque « j'ai vérifié » précisément là où elle ne peut pas.

La liste est close, comme celle du §3 :
`saknussemm.core.decide.REVIEW_REASON_CODES` la porte et
`tests/test_the_review_reasons_are_a_closed_set.py` la tient dans les
deux sens.

### Par ligne — l'indice est dans le couple (source, correction)

| code | ce qu'il veut dire |
|---|---|
| `digits_changed` | les chiffres ne sont plus les mêmes — couvre l'année, le prix, le numéro de page. Ni les dates ni les montants ne sont analysés : il n'y a pas de grammaire, seulement le constat |
| `negation_changed` | une particule de négation est apparue, a disparu, ou a changé de nombre |
| `proper_noun_changed` | un mot en majuscule initiale, hors premier mot de la ligne, a été réécrit, ajouté ou retiré |

### Au niveau du run — l'indice n'existe que dans l'agrégat

| code | ce qu'il veut dire |
|---|---|
| `systematic_substitution` | un caractère a été remplacé par le même autre sur **toutes** ses occurrences du run |
| `systematic_removal` | idem, mais il a été supprimé |

C'est la seule famille qu'une lecture ligne à ligne ne peut pas voir. Le
cas mesuré : `⸗` retiré 34 fois sur 34, `’` normalisé 69 fois sur 69.
Ligne par ligne, chacune est une édition d'un caractère sans intérêt ;
sur le run, c'est la typographie du document qui a été réécrite.

### Conséquence, pas décision

| code | ce qu'il veut dire |
|---|---|
| `hyphen_unit_review` | l'autre moitié d'un mot coupé est renvoyée, celle-ci suit (ADR-010) |

Aucun texte ne bouge dans un renvoi, donc l'unité ne risque pas de
devenir mixte — ce n'est pas la raison. La raison est qu'un renvoi parle
d'un **mot**, et qu'une moitié de mot n'est pas relisable.

### Trois règles absentes, et pourquoi

Le programme d'origine en prévoyait trois de plus. Elles ne sont pas
« pas encore faites » : le moteur n'a pas de quoi les alimenter, et
déclarer leur code ferait promettre une raison qu'aucun run ne rendrait.
`src/saknussemm/core/review.py` porte le détail.

- **une ligne déjà correcte modifiée quand même** — écrite, mesurée,
  retirée. Sans lexique, « la source n'a rien d'anormal » se réduit à des
  signaux structurels que la dégradation d'OCR patrimonial ne laisse pas
  (`fciences` pour `ſciences`, ce sont des lettres). Sur le corpus de
  vérité terrain elle renvoyait 30 des 47 lignes modifiées, 23 sur son
  seul indice, et ce qu'elle attrapait était de simples corrections
  `f` → `ſ`.
- **désaccord producteur texte / producteur vision** — aucun run
  n'interroge deux producteurs sur la même ligne : l'escalade *remplace*
  le producteur, elle ne le double pas.
- **confiance non calibrée sous seuil** — l'agrégat de confiance est
  construit après que le `DecisionSet` est devenu immuable, et
  `core/confidence.py` dit lui-même que ses valeurs ne sont pas des
  probabilités calibrées.

---

## 3 ter. Ce qui n'est pas un repli — les éditions refusées

Le protocole d'édition (`core/editing.py`) refuse des **opérations**, pas des
lignes : la ligne garde sa source et la refus apparaît sur
`report.edit_rejections`, pas sur `fallback_reason`.

`e1_unknown_line`, `e1_context_line`, `conflict`, `e2_overlap`, `e3_empty`,
`e3_newline`, `e4_span_growth`, `e4_line_budget`, `e5_hyphen`,
`e5_boundary_word`, `anchor_not_found`, `anchor_ambiguous`,
`anchor_out_of_range`, `anchor_empty_match`, `precondition_source_digest`.

---

## 4. Lire un cas concret

**« Cette ligne est `FALLBACK` avec `hyphen_unit_fallback` et je ne vois rien
d'anormal dessus. »** C'est normal : elle n'a rien fait. Cherchez l'autre
membre de son unité — `report.lines` donne le `hyphen_role` — il porte la
vraie raison.

**« `all_attempts_exhausted: transport: …` sur un tiers de la page. »** Le
modèle n'a pas été interrogé. Regardez `result.producer_calls` et le quota du
compte, pas la qualité du modèle.

**« Le rapport dit `corrected` mais le fichier n'a pas bougé. »** Une
correction peut aboutir à un texte identique à la source. L'autorité est le
`DecisionSet`, pas une comparaison d'octets — c'est écrit dans
`docs/promises.md`.

**« Cette ligne est `review_required` et la correction me semble juste. »**
Très probablement. Un renvoi ne dit rien de la correction : il dit que le run
n'a aucun moyen d'établir qu'elle l'est. Sur le run qui a motivé l'état, un
détecteur de chiffres modifiés a levé 56 lignes dont la quasi-totalité étaient
de **bonnes** corrections — ce qui n'a pu être établi qu'avec la vérité
terrain, dont la production n'en a pas. Le texte est livré ; `review_reasons`
dit ce qui a changé et pourquoi personne ici ne peut le confirmer.

**« `format_loss` sur toutes mes lignes PAGE. »** Vous tournez en
`LossPolicy(strict=True)` sur un fichier dont les lignes portent des `Word` :
toute correction qui change le compte de mots est refusée par conception. La
politique par défaut projette et compte.

---

## 5. Ce qui n'est pas sur le chemin par défaut

Trois mécanismes traversent le code sans qu'aucun run par défaut ne les
exécute. Si vous lisez le chemin d'un chunk et butez dessus, vous pouvez les
sauter :

- **le routage QE** (`core/routing.py`, `core/quality.py`) — sans `qe_scorer`,
  chaque ligne va au producteur ;
- **l'escalade vers un producteur vision** (`escalation_producer`) — `None` par
  défaut ;
- **le plafond d'images par appel** (`core/batching.py`) — sans producteur qui
  déclare `max_images`, aucune découpe.

Les trois sont derrière une couture, `core.routing.ChunkRouter`, à laquelle
`PageDriver` demande son plan. Le pilote ne les connaît pas — une assertion
de `tests/test_routing_pipeline.py` le tient — donc lire la boucle interne du
moteur n'oblige pas à les comprendre. Ils sont court-circuités, pas seulement
inactifs : leur coût est cognitif, pas en temps d'exécution.

---

## 6. Où lire la suite

- `SPECS_LIB_V2.md` — le contrat : ce que la bibliothèque doit être.
- `docs/reading-a-report.md` — la structure du rapport §9.
- `docs/edit-protocol.md` — `E1`–`E6` en détail.
- `docs/adr/010-atomic-hyphen-groups.md` — pourquoi une unité de césure ne se
  divise jamais.
- `docs/adr/013-fallback-reason-precedence.md` — pourquoi c'est la **première**
  passe qui a retiré la correction qui garde l'attribution.
