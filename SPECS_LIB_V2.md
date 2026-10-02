# SPEC — bibliothèque d'édition sûre de transcriptions patrimoniales

> **Statut** : proposition v2, issue de la revue de code complète d'`alto-core`
> (commit courant de `alto-llm-corrector`) + pesée du protocole d'édition par
> spans (« C »). Ce document est la **cible** : ce que la bibliothèque doit
> être. Il ne porte plus de calendrier — le plan unique est `docs/PLAN.md`
> (§13 ci-dessous est conservé comme trace historique et **remplacé** par lui).

---

## 1. Identité & principes

**Ce que la lib est** : une bibliothèque Python pour **éditer le texte de
transcriptions structurées patrimoniales (ALTO, PAGE XML) via des modèles ou
des règles, sans jamais corrompre la structure**. Parser → représentation
pivot → plan de chunks → production d'éditions ancrées → validation
multi-étages → recomposition minimale du XML d'origine.

**Ce que la lib n'est pas** : un OCR, un segmenteur, un évaluateur, un
visualiseur, un convertisseur universel (§12).

Trois invariants fondateurs, hérités de l'existant et non négociables :

- **I1 — Le texte ne voyage jamais sans son ancre.** Toute donnée envoyée à
  un producteur d'éditions (LLM, règles, modèle spécialisé) porte l'identité
  de sa ligne ; toute édition revient adressée à cette identité. La
  recomposition est une écriture indexée, jamais une recherche d'alignement.
- **I2 — L'application décide, le modèle informe.** Aucune sortie de modèle
  n'atteint le XML sans passer les gardes ; au moindre doute, repli sur le
  texte source. Aucune édition structurelle (fusion/scission/déplacement de
  lignes) n'est représentable dans le protocole — pas seulement interdite :
  **inexprimable**.
- **I3 — La structure d'origine est intouchable.** IDs, géométrie ligne,
  ordre XML, attributs non textuels : préservés à l'octet quand rien ne
  change (stratégie 4 chemins), modifiés au minimum quand le texte change.
- **I4 — Le cœur est aveugle aux pixels.** Le cœur ne charge, ne découpe et
  n'encode jamais d'image. La correction *guidée par l'image* (VLM) est un
  **producteur** qui reçoit une **référence** d'image opaque ; charger et
  cropper les pixels est la responsabilité de l'implémentation du producteur,
  hors du cœur (§5.2 bis). C'est le corollaire vision de « zéro I/O dans
  `core` ».

  **Portée exacte, en trois niveaux** — I4 contraint le cœur, pas la
  distribution entière :
  1. `core/` et les formats ne touchent jamais un pixel, et n'importent
     jamais de bibliothèque d'image. Ligne rouge (§12), vérifiée par le scan
     statique I4.
  2. L'installation de base (`pip install saknussemm`) n'embarque **aucune**
     dépendance image : `dependencies` se limite à Pydantic et lxml.
  3. L'extra `saknussemm[vision]` — `integrations/vision.py`, le producteur
     de référence — **décode, oriente et crope effectivement des pixels**,
     avec Pillow pour seule dépendance image, importée **paresseusement à
     l'intérieur des fonctions** pour que le chemin d'installation de base ne
     la charge jamais. C'est un producteur, donc hors du cœur : I4 tient.

  Le point 3 est ce que le titre de cet invariant a longtemps laissé croire
  interdit. Il ne l'est pas — il est la raison d'être du seam. Ce qui reste
  interdit est de faire entrer un pixel ou une dépendance image **dans le
  cœur**. `tests/test_import_contract.py` tient les trois niveaux.

Corollaire transverse : **le cœur est agnostique de la modalité**. Validation
1:1, gardes, réconciliation et rewriter ne voient jamais que du texte-in /
texte-out clé par `line_id` — qu'il vienne d'un LLM texte, d'un VLM qui a lu
l'image, ou d'un moteur de règles ne change rien pour eux. C'est ce qui fait
que la correction par VLM « traverse » la lib sans en toucher le cœur.

---

## 2. Décision : intégrer le protocole d'édition par spans (« C »)

### Pesée

**Pour** :
1. Le pipeline actuel EST déjà un cas particulier du protocole : `enrich_chunk_lines`
   compile les manifests en représentation simplifiée, le modèle édite, le
   rewriter recompose par `line_id`. C nomme et généralise l'existant —
   coût de conception marginal, pas d'étage étranger.
2. Une édition ancrée est **plus vérifiable** qu'une réécriture complète :
   existence de l'ancre, borne de taille, non-chevauchement, dérive mesurée
   *par édition*. Les gardes deviennent plus fortes, pas plus faibles.
3. Sorties plus courtes → moins cher, plus rapide, et c'est le format de
   sortie naturel d'un futur modèle spécialisé de post-correction.
4. Le **moteur de règles déterministe** (§5.3) émet nativement des spans :
   le protocole a un premier producteur réel, testable et gratuit dès sa
   livraison — l'objection « pas de consommateur » tombe.
5. Un consommateur qui benche des pipelines de correction consomme ce
   protocole au lieu de construire le sien : un seul lieu de conception.

**Contre** (et mitigations) :
1. *Spéculation* : concevoir le protocole avant le modèle spécialisé qui le
   nourrira. → Discipline des deux axes : l'**enveloppe** (types, ancres,
   recomposeur) est conçue maintenant ; la **surface** arrive
   incrémentalement, le moteur de règles servant de producteur de référence.
2. *Les offsets de caractères sont un piège pour les LLM* (ils comptent
   mal). → Deux modes d'adressage (§4.3) : `match` (sous-chaîne + occurrence,
   robuste pour LLM) et `range` (offsets, pour producteurs déterministes),
   normalisés en `range` par le recomposeur qui rejette l'ambigu.
3. *Sur-abstraction* : si tout devient « document générique + spans », la
   valeur spécifique (césure) se dissout. → La césure reste une logique de
   **paires de lignes** dans le cœur, hors du protocole d'édition ; le
   protocole n'exprime que de l'intra-ligne.
4. *Grossir la v1 retarde la sortie.* → Staging strict (§13) : v1.0 publie
   l'existant corrigé, le protocole vient en v2.0 en **ré-exprimant**
   l'existant (la réécriture de ligne devient l'op `replace_line`).

### Verdict

**Oui — comme enveloppe de la v2, pas comme chantier de la v1.** La v2.0
ré-exprime le pipeline actuel dans le protocole (aucun changement de
comportement) et livre le moteur de règles comme premier producteur de spans
réels. Le producteur LLM d'éditions fines et le modèle spécialisé viennent
ensuite, chacun avec sa preuve.

---

## 3. Architecture cible

> **Relevé du 2026-07-28.** L'arbre ci-dessous décrivait un paquet nommé
> `lib/` avec 7 modules de cœur, sans `integrations/`, sans `errors.py`, sans
> `facade.py`, et avec un `producers/llm.py` qui n'existe pas. Un document
> normatif qui décrit un périmètre faux est le défaut que `V8` interdit :
> réécrit depuis l'arborescence réelle (`D2`). Ce qu'il faut y lire est la
> **frontière**, pas la liste — le cœur ne connaît ni lxml ni réseau, les
> formats ne connaissent pas le producteur, et `integrations/` est le seul
> étage qui touche un vendeur.

```
saknussemm/
├── __init__.py              # surface de sommet (PEP 562 : formats/producteurs paresseux)
├── errors.py                # hiérarchie SaknussemmError (§8.4)
├── facade.py                # load / correct / correct_sync — le chemin en 3 lignes (§2)
├── core/                    # pur : zéro I/O, zéro réseau, zéro lxml
│   ├── schemas/             # manifest / policies / producer / report — tout réexporté
│   │                        #   par `schemas/__init__.py` (§8.2, §9)
│   ├── protocols.py         # EditProducer, PipelineObserver, FormatAdapter, RewriteResult
│   ├── pipeline.py          # orchestration (retry, descente de granularité, traces)
│   ├── planner.py           # chunk planner (PAGE→BLOCK→WINDOW→LINE, césure-conscient)
│   ├── guards.py            # matrice anti-migration (3 étages) + GuardConfig
│   ├── hyphenation.py       # réconciliation de paires (logique TEXTE, format-agnostique)
│   ├── pairing.py           # répertoire de coupure + primitives de lien dirigé (ADR-010)
│   ├── units.py             # dérivation d'unité de césure + split_forward_link
│   ├── editing.py           # EditScript : validation, normalisation match→range, application
│   ├── decisions.py         # DecisionSet, assemblage des LineOutcome (ADR-011)
│   ├── identity.py          # LineRef — l'identité (page_id, line_id) (ADR-009)
│   ├── fidelity.py          # échelle de fidélité de projection (L0/L8)
│   ├── losses.py            # matrice des pertes, versionnée (R0)
│   ├── validator.py         # validation de la réponse producteur + intégrité de césure
│   ├── alignment.py         # alignement de tokens source↔correction
│   ├── confidence.py        # confiances de ligne
│   ├── quality.py           # QE + routage
│   ├── events.py            # types d'événements de l'observateur
│   ├── _norm.py             # NFC, nettoyage de CONTENT
│   └── _parse.py            # parsing d'entiers tolérant
├── formats/                 # formats de transcription concrets (lxml, durci)
│   ├── loader.py            # détection de format + façade de parsing
│   ├── validation.py        # validation XSD
│   ├── alto/                # parser + rewriter ALTO (v2/v3/v4)
│   └── page/                # parser + rewriter PAGE XML (2013/2019/2024)
├── producers/               # implémentations d'EditProducer
│   ├── llm_edit.py          # producteur LLM (enveloppe le contrat d'intégration)
│   └── rules.py             # moteur de règles déterministe
└── integrations/            # le seul étage qui connaît un vendeur
    ├── llm.py               # contrat provider LLM (payload, schéma de sortie, prompt)
    ├── qe.py                # estimateur de qualité
    └── vision.py            # extra `saknussemm[vision]` — Pillow, import paresseux (I4)
```

Règle d'import : `core` n'importe rien de `formats` ni `producers` ;
`formats` n'importe que `core` ; `producers` n'importe que `core`. La
détection de césure (qui lit `<HYP>`/`SUBS_*` ou `¬`) vit dans `formats/*` ;
la **réconciliation** (qui ne voit que du texte) vit dans `core` — c'est le
déplacement du `alto/hyphenation.py` actuel, mal rangé sous `alto/` alors
qu'il n'importe pas lxml.

Le découpage actuel (`alto_core.alto`, `alto_core.pipeline`,
`alto_core.protocols`, `alto_core.schemas`) migre vers cet arbre en v2.0 ;
les renommages sont des ruptures assumées de pré-2.0 (§8.5).

---

## 4. Le protocole d'édition par spans

### 4.1 Vue d'ensemble

```
structure (ALTO/PAGE)
   │  parse (formats/*)
   ▼
DocumentManifest ──compile──▶ ModelPayload ──producteur──▶ EditScript
   ▲                              (simplifié,                  │
   │                               ancré)                      │ validate + normalize
   └──────────── recompose (formats/*) ◀── manifests édités ◀──┘
```

Le **compilateur** existe déjà (`enrich_chunk_lines` + payload) ; le
**recomposeur** existe déjà (rewriter 4 chemins) ; la v2.0 insère l'étage
`EditScript` entre les deux et ré-exprime la réponse « ligne entière »
comme une op parmi d'autres.

Le `ModelPayload` porte **optionnellement**, par ligne, deux champs
d'ancrage physique — présents uniquement quand un producteur les demande
(producteur vision, §5.2 bis), ignorés par les producteurs texte :
`geometry` (les `coords` du manifest, déjà disponibles — bbox/polygone +
dimensions de page, de quoi calculer une bbox relative sans connaître
l'unité) et `image_ref` de page (chaîne opaque, jamais ouverte par la lib,
issue du mapping `page_images` passé à `run()`). Le compilateur ne fait
que **recopier** ces champs depuis le manifest et le mapping ; il ne touche
aucun pixel.

### 4.2 Opérations

```python
class ReplaceLine(BaseModel):      # v2.0 — ré-expression de l'existant
    op: Literal["replace_line"]
    line_id: str
    text: str                       # ligne complète corrigée

class ReplaceSpan(BaseModel):      # v2.0 (producteur règles) / v2.1 (producteur LLM)
    op: Literal["replace_span"]
    line_id: str
    anchor: MatchAnchor | RangeAnchor
    text: str                       # remplacement du span uniquement

EditOp = ReplaceLine | ReplaceSpan
class EditScript(BaseModel):
    ops: list[EditOp]
```

**Aucune op structurelle.** Pas de `merge_lines`, pas de `split_line`, pas
de `move_text` : l'invariant I2 est garanti par le type, pas par une
validation.

### 4.3 Ancrage — deux modes, un seul après normalisation

```python
class RangeAnchor(BaseModel):       # producteurs déterministes
    start: int                      # offsets DANS LE TEXTE CANONIQUE de la ligne
    end: int                        # (celui de reconstruct_textline, strippé)

class MatchAnchor(BaseModel):       # producteurs LLM
    match: str                      # sous-chaîne exacte du texte canonique
    occurrence: int | None = None   # None = unicité requise ;
                                    # n explicite (0 = première) = n-ième occurrence
```

Motivation : l'expérience de terrain des formats d'édition LLM montre que
les modèles échouent sur les offsets numériques et les numéros de ligne,
mais sont fiables sur « remplace *cette sous-chaîne* ». C'est la pratique
convergente des outils éprouvés : blocs recherche/remplacement d'aider
(mesurés supérieurs aux diffs à numéros de ligne dans leurs benchmarks
d'edit-formats), commande `str_replace` de l'outil `text_editor`
d'Anthropic (correspondance exacte **et unique** exigée, sinon erreur).
À l'inverse, les systèmes déterministes (moteurs de règles, détecteurs
d'erreurs type ICDAR post-OCR, qui émettent des corrections
positionnelles) calculent des offsets exacts sans effort. Et les modèles
seq2seq fine-tunés ré-émettent naturellement des lignes entières. D'où les
trois formes : `replace_line` (LLM par défaut + seq2seq), `MatchAnchor`
(LLM avancé), `RangeAnchor` (déterministe).

Le recomposeur **normalise** tout `MatchAnchor` en `RangeAnchor` contre le
texte canonique ; un match introuvable ou dont l'occurrence n'existe pas →
op rejetée (repli I2), un match ambigu (plusieurs occurrences sans
`occurrence` explicite) → op rejetée. Le texte canonique de référence est
celui que le parser expose (`ocr_text`), ce qui rend l'adressage
indépendant du format.

### 4.4 Invariants d'un EditScript (validation `core/editing.py`)

- E1 : chaque `line_id` existe dans le chunk visé (jamais hors chunk).
- E2 : spans normalisés d'une même ligne **sans chevauchement**, appliqués
  de droite à gauche (offsets stables).
- E3 : `text` sans `\n`/`\r`, non vide après strip pour `replace_line`
  (un `replace_span` peut être une suppression : `text=""` autorisé si le
  résultat de la ligne reste non vide).
- E4 : bornes de dérive **par op** (`GuardConfig`) : ratio de longueur max
  du remplacement vs span remplacé, budget de caractères réellement
  modifiés par ligne (fenêtre différente après élagage du préfixe/suffixe
  communs — une réécriture à longueur constante coûte sa taille réelle).
- E5 : une ligne de rôle césure (PART1/PART2/BOTH) éditée par span ne peut
  pas voir son mot-frontière supprimé ni son tiret final retiré — mêmes
  gardes qu'aujourd'hui, appliquées au **résultat** de la ligne.
- E6 : après application, le pipeline de gardes existant (matrice 3 étages,
  §7 F-héritées) s'applique au texte de ligne résultant, à l'identique du
  chemin `replace_line`. Le protocole ajoute des gardes, il n'en retire
  aucune.

### 4.5 Ce que le protocole ne transporte pas

La **césure** : les rôles, les paires, la réconciliation restent une affaire
de manifests de lignes (couche cœur), invisibles dans l'EditScript. Un
producteur voit les indices de césure dans le payload (comme aujourd'hui) et
édite chaque ligne séparément ; la réconciliation juge le résultat.

---

## 5. Producteurs d'éditions

### 5.1 Contrat (v2.0)

```python
class EditProducer(Protocol):
    #: Le compilateur inclut geometry + image_ref dans le payload uniquement
    #: si le producteur les réclame — évite d'alourdir un payload texte.
    wants_geometry: bool = False
    wants_image: bool = False

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]: ...
```

> **Corrigé le 2026-07-28 (`D2`).** Cette signature montrait
> `payload: ModelPayload, *, policy: RetryPolicy` — un type qui n'existe pas,
> et le `RetryPolicy` complet que P3.7 a précisément **retiré** de cette
> couture : le moteur possède la stratégie de retry, un producteur n'a besoin
> de savoir que ce qui concerne **cet appel-ci**. La spec contredisait donc sa
> propre prose sur `ProducerOptions`.

À partir de v2.0, `BaseProvider` (LLM) devient **une implémentation** de ce
contrat, pas le contrat lui-même. `Usage` (tokens in/out) remonte au rapport
et au consommateur (qui le mappe sur sa propre comptabilité de ressources) ;
en v1.0 il est déjà remonté par `complete_structured` (F14).

`run()` accepte un mapping optionnel `page_images: dict[str, ImageRef]`
(clé = `page_id`, unique au document — **une image par page physique**, pas
par fichier source : un fichier multipage a plusieurs pages et donc
plusieurs images), que la lib **forwarde** comme référence opaque et
**n'ouvre jamais**. Un producteur à `wants_image=True` sans `page_images`
couvrant chaque page → `ConfigurationError` au démarrage
(`require_page_images` — jamais un appel vision muet sans image).

### 5.2 Producteur LLM (existant, généralisé)

- v2.0 : sortie `replace_line` uniquement — comportement actuel byte-stable,
  schéma JSON strict, validation 1:1 inchangée.
- v2.1 : schéma de sortie alternatif `replace_span` + `MatchAnchor`
  (opt-in par configuration). Prompt système dédié. À ne livrer qu'avec
  un banc de mesure comparatif (`replace_span` vs `replace_line`).
- Le payload distingue **lignes cibles** et **lignes de contexte** (fix F8,
  §7) : le producteur ne doit émettre d'ops que pour les cibles.

### 5.2 bis — Producteur vision / VLM (enveloppe v2.0, surface v2.x)

Correction **guidée par l'image** : un VLM reçoit, par ligne, l'`ocr_text`
**et** l'image de la ligne, et propose la correction. Cas d'usage : un
consommateur qui met en concurrence « correction texte-seul » et « correction
image + structure » (typiquement un banc), ou qui veut simplement récupérer un
OCR très fautif que seul le pixel permet de relire. C'est la correction
d'ALTO/PAGE **ligne par ligne** guidée par l'image (write-back par `line_id`).

Ce qui appartient à la **lib** (enveloppe, minimal) :
- Le contrat `EditProducer` vision-aware (§5.1 : `wants_geometry`/`wants_image`
  + `page_images`).
- Le compilateur qui **recopie** `geometry` (déjà dans le manifest) et
  `image_ref` de page (opaque) dans le `ModelPayload` (§4.1).
- **Rien d'autre.** La lib ne charge pas l'image, ne crope pas, n'encode pas.

Ce qui appartient au **consommateur** (le producteur concret, hors lib) :
- Charger l'image de page depuis `image_ref`, **cropper** chaque ligne via sa
  `geometry` (bbox relative = `coord/dimension_page`, sans souci d'unité),
  encoder, construire le message multimodal, appeler le VLM, renvoyer le même
  JSON `{lines:[{line_id, corrected_text}]}`.
- C'est une **implémentation de producteur** — par définition hors du cœur,
  comme tout provider concret (I4 : le *cœur* ne touche aucun pixel ; un
  producteur vision, lui, en traite — c'est son travail).

**Prototypage sans changement de lib** : un producteur *stateful par document*
qui se construit avec le `DocumentManifest` + l'image, résout `coords[line_id]`
et crope, fonctionne avec la lib **inchangée** (il n'a besoin que des `line_id`
que le payload transporte déjà). L'enveloppe `page_images`/`wants_*` n'est
requise que pour un producteur **stateless et générique** (réutilisable par
n'importe quel consommateur, non reconstruit par document) — c'est la cible
v2.0 ; le producteur stateful est le raccourci de prototypage.

**Interaction avec les gardes (essentiel) :** les seuils d'acceptation
actuels sont calibrés pour du texte-seul, où « une correction très éloignée de
l'OCR est suspecte » (`MIN_SOURCE_SIMILARITY`). Un VLM a une **preuve
indépendante** — l'image — et peut légitimement diverger fortement d'un OCR
très fautif. Il faut donc un **profil `GuardConfig.vision()`** (§7 F13) :
similarité-source **détendue**, mais **garde-migration inter-lignes
maintenue** (c'est elle qui protège l'ancre, indépendante de la modalité). Les
seuils de ce profil se **calibrent par la mesure**, pas au doigt mouillé.
Réglage **hors lib** (au consommateur) : granularité des crops (par ligne /
par bloc / page entière) — arbitrage coût-tokens vs qualité de grounding ; le
crop par ligne est le plus fidèle à I1 mais le plus cher.

### 5.3 Producteur règles (nouveau, v2.0 — le premier émetteur de spans réels)

Moteur déterministe : table de substitutions (regex ou littérales) avec
garde optionnelle par dictionnaire/lexique. Exemples cibles : `ſ→s`,
confusions `rn→m` sous condition lexicale, ponctuation OCR. Émet des
`ReplaceSpan` à `RangeAnchor` (il calcule les offsets exactement).
Zéro dépendance, zéro réseau, reproductible à l'octet — c'est aussi le
producteur de référence des tests du protocole, et une passe de
pré-correction gratuite avant LLM.

### 5.4 Modèle spécialisé (futur, v2.x)

Enveloppe prévue, surface différée : sérialisation **texte** du
`ModelPayload` (lignes numérotées) + parseur de la réponse pour seq2seq
fine-tuné qui ne fait pas de JSON. Ne se construit que lorsqu'un tel modèle
existe et se benche (réflexe : pas de consommateur = pas de code).

---

## 6. Formats

### 6.1 ALTO (acquis + corrections normatives)

L'existant est conservé (parser, rewriter 4 chemins, provenance
`processingStep`) avec les corrections normatives du §7. Points fixés :

- **Réutilisation d'attributs en slow path — liste blanche explicite** :
  `ID`, `STYLEREFS` et `STYLE` sont réutilisés positionnellement ;
  `HPOS`/`WIDTH` recalculés ; `VPOS`/`HEIGHT` hérités de la ligne ;
  `WC`/`CC`/`SUBS_*` **jamais recyclés** (F2). `STYLE` (stylage inline
  bold/italics, jumeau par-valeur de `STYLEREFS`) est dans la liste par
  la doctrine F2 elle-même : elle ne proscrit que les données *invalidées*
  par le changement de texte, et le stylage ne l'est pas — le supprimer
  détruisait 45/47 `String` stylés du corpus X0000002 (mesuré, manchettes
  de presse en tête). *Ratifié le 2026-07-07.*
- La géométrie mot post-correction est une **approximation documentée**
  (attribut d'en-tête ou commentaire XML optionnel signalant la passe de
  correction ; le `processingStep` porte déjà la provenance).

### 6.2 PAGE XML (nouveau, v1.1)

PAGE (PRImA) est le format natif de Transkribus et d'eScriptorium ; le
supporter fait passer la lib de « correcteur ALTO » à « correcteur d'XML de
transcription patrimoniale ». Le cœur (manifests, planner, gardes,
réconciliation, protocole) est réutilisé tel quel ; seul `formats/page/`
est nouveau. Règles normatives :

- **P1 — Géométrie = polygones.** PAGE encode `Coords@points` (polygones),
  pas des bbox. Le manifest conserve le polygone source verbatim et expose
  la bbox englobante calculée (besoin du planner). **Aucune géométrie n'est
  jamais réécrite** — pas d'équivalent du slow path géométrique d'ALTO.
- **P2 — Texte canonique d'une ligne** = `Unicode` du TextEquiv canonique
  (P3) de la `TextLine`, NFC + strip. S'il est absent, concaténation des
  `Word/TextEquiv` séparés par des espaces. En cas de désaccord entre le
  texte ligne et la concaténation des mots, **le texte ligne fait foi**
  (signalé dans le rapport).
- **P3 — TextEquiv canonique** = celui d'`@index` minimal (absence d'index
  ≡ 0). À la réécriture d'une ligne modifiée : mise à jour de son
  `Unicode` (et `PlainText` s'il existe), **suppression de son `@conf`**
  (confiance périmée — même doctrine que F2) et **suppression des TextEquiv
  alternatifs** de l'élément (ils décrivaient l'ancien texte) ; le tout
  compté dans le `CorrectionReport`.
- **P4 — Éléments `Word`.** Fast path (compte de mots inchangé) : mise à
  jour des `TextEquiv` de chaque `Word` en place, `Coords` conservées,
  `@conf` supprimé. Slow path (compte changé) : les `Word` de la ligne sont
  **supprimés**, le texte vit au niveau ligne — fabriquer des polygones de
  mots dans une ligne inclinée serait plus mensonger que l'approximation
  bbox d'ALTO ; perte de granularité **documentée et comptée**.
- **P5 — Césure : heuristique, toujours.** PAGE n'a ni `<HYP>` ni
  `SUBS_TYPE`/`SUBS_CONTENT`. Détection de rôle sur caractères terminaux
  configurables : `-`, `¬` (U+00AC, convention Transkribus), `⸗` (U+2E17,
  Fraktur), `­` (U+00AD). `hyphen_source_explicit = False` systématiquement
  → la réconciliation tourne en mode conservateur, sans reconstruction de
  mot logique. Le **caractère de césure d'origine est préservé** à la
  réécriture (garde E5 étendue : un producteur ne peut pas normaliser
  `¬` → `-`). *Conventions à confirmer sur exports réels Transkribus et
  eScriptorium — c'est une exigence de la DoD v1.1.*
- **P6 — Microformat `custom`.** Transkribus stocke dans
  `custom="readingOrder {index:0;} textStyle {offset:…; length:…;} …"` des
  annotations dont certaines sont **ancrées par offsets de caractères**
  (textStyle, tags sémantiques). Doctrine « jamais de donnée périmée »
  (cf. F2) : les groupes **sans** offsets (`readingOrder`, `structure`)
  sont préservés verbatim ; les groupes **à** offsets sont retirés dès que
  le texte de la ligne change, et comptés dans le rapport. v2.x (chemin
  span uniquement) : **remappage des offsets** à travers l'EditScript — les
  `RangeAnchor` normalisés donnent les deltas exacts ; c'est une synergie
  directe du protocole §4, impossible avec des réécritures de lignes
  entières.
- **P7 — Sécurité & provenance.** `make_safe_parser()` obligatoire (le
  test-contrat grep s'étend à `formats/`). Provenance : mise à jour de
  `Metadata/LastChange` + écriture d'un `MetadataItem type="processingStep"`
  quand le schéma cible (2019+) le permet, repli sur `Metadata/Comments`
  sinon — à valider contre le XSD effectivement visé.

### 6.3 Parité inter-formats

Un même `DocumentManifest` en sortie de parse, quel que soit le format ;
les tests de parité imposent : texte canonique identique pour un même
contenu logique, rôles de césure détectés équivalents quand l'information
existe, round-trip byte-stable sur documents non modifiés dans les deux
formats.

---

## 7. Corrections normatives sur l'existant (issues de la revue)

Chaque entrée : constat → règle normative. Toutes sont **v1.0** sauf mention.

| # | Constat (fichier:ligne au commit revu) | Règle normative |
|---|---|---|
| **F1** | `downgrade_granularity` (`chunk_planner.py:30`) jamais appelé ; à l'épuisement des retries, `_apply_chunk_fallback` (`correction_pipeline.py:651`) reverte **tout le chunk** à l'OCR — au grain PAGE, une ligne malformée coûte la page entière | À l'épuisement du budget d'un chunk de grain G, **re-planifier les lignes du chunk au grain inférieur** (PAGE→BLOCK→WINDOW→LINE) et retenter ; seules les lignes dont le chunk LINE échoue passent en repli OCR. Budget total borné par `RetryPolicy.per_chunk_budget` (défaut : 6 tentatives cumulées). Événement `chunk_downgraded` émis à chaque descente |
| **F2** | Fast path (`rewriter.py:272`) et slow path (`rewriter.py:314`) conservent/recyclent `WC`/`CC` : confidences périmées, `CC` de longueur incohérente avec le nouveau `CONTENT` | Tout changement de `CONTENT` **supprime `WC` et `CC`** sur le `String` concerné. Le slow path ne recycle que `ID`, `STYLEREFS` et `STYLE` (liste blanche §6.1, ratifiée 2026-07-07) |
| **F3** | `etree.QName(last_child.tag)` (`parser.py:143`) lève sur commentaire/PI en fin de `TextLine` → échec du fichier entier | Toute itération d'enfants ignore les nœuds dont `tag` n'est pas `str` (commentaires, PI). Test avec fixture contenant commentaires |
| **F4** | Détection UNTOUCHED : `reconstruct_textline(el) == nfc(corrected)` (`rewriter.py:117`) non strippé vs `ocr_text` strippé (`parser.py:25`) → lignes jamais UNTOUCHED, réécritures et métriques faussées | Comparaison sur formes **strippées des deux côtés**. Test : ligne avec SP de queue non corrigée → chemin UNTOUCHED |
| **F5** | `_int_attr` (`_ns.py:46`) lève sur coordonnées flottantes (`"123.0"`) | `int(float(raw))`, arrondi trunc, avec test. Une valeur non numérique lève toujours |
| **F6** | `_compute_geometry` (`rewriter.py:67-82`) : `unit` calculé sur le compte plein mais espaces pondérés 0,6 → le dernier token absorbe tout le déficit | Le poids 0,6 des espaces entre dans `total_weight` ; la correction d'arrondi se répartit ; le dernier token n'absorbe que l'arrondi résiduel |
| **F7** | Appariement de césure purement séquentiel (`parser.py:33`), aucun contrôle géométrique inter-blocs | Documenté comme hypothèse + **politique d'appariement** injectable (`PairingPolicy`, défaut = comportement actuel). Pas de géométrie par défaut : les gardes aval couvrent ; le seam permet de durcir sans fork |
| **F8** | Chevauchement de fenêtres : ligne corrigée au chunk N (bord, contexte tronqué) **sautée** au chunk N+1 (contexte plein) — la moins bonne correction gagne ; même mécanique quand la réconciliation écrit un PART2 hors chunk | Les chunks distinguent **lignes cibles** et **lignes de contexte** : une ligne n'est cible que dans le chunk où son contexte est maximal ; les recouvrements deviennent contexte pur. Le validateur n'attend de sortie que pour les cibles (le comptage 1:1 porte sur les cibles) ; la sortie d'une ligne de contexte est **optionnelle mais strictement vérifiée quand présente**, puis écartée (la ligne est cible d'un chunk adjacent — invariant : chaque ligne est cible dans exactement un chunk). Ratifié 2026-07-07 |
| **F9** | Rampe de température 0.0→0.3→0.5 codée en dur (`correction_pipeline.py:725`) → non-déterminisme dès le premier retry | `RetryPolicy(max_attempts, temperatures, backoffs, per_chunk_budget)` injectable. `RetryPolicy.default()` = comportement actuel ; `RetryPolicy.deterministic()` = températures toutes à 0 (pour un usage reproductible) |
| **F10** | Aucun point d'annulation : un run ne peut pas être interrompu proprement | `should_abort: Callable[[], bool]` optionnel sur `run()`, sondé entre chunks et entre pages → `CorrectionAborted` levée, sorties non écrites. Les appels provider en vol ne sont pas interrompus (coopératif, documenté) |
| **F11** | Les tests de l'algorithme (`hyphenation`, `chunk_planner`, `validator`, `line_acceptance`, `rewriter`, `parser`) vivent dans `backend/tests/` — la lib ne porte pas sa propre preuve | Rapatriement dans `packages/<lib>/tests/` ; le backend ne garde que ses tests d'intégration/transport. CI de la lib indépendante (matrix 3.11–3.13) |
| **F12** | Packaging : pas de `py.typed`, enums applicatives dans le cœur (`Provider`, `JobStatus`/`JobManifest` documenté « server-side » dans `schemas`) | Marqueur `py.typed` + `mypy --strict` en CI. `Provider`, `JobManifest`, `JobStatus` (et `images: dict`) **sortent du cœur** vers le backend — le cœur n'énumère pas des vendeurs. `LineStatus`, `PipelineEventType` restent |
| **F13** | Seuils des gardes en constantes dispersées (`line_acceptance.py:37-51`, `migration_guards.py`) | `GuardConfig` (frozen) regroupant tous les seuils, défauts = valeurs actuelles (byte-compatible). Docstring : les trois étages se règlent ensemble. **v2.x** : profil `GuardConfig.vision()` (similarité-source détendue, garde-migration inter-lignes maintenue) pour la correction VLM (§5.2 bis) — seuils calibrés au banc, non livrés tant qu'un producteur vision ne les benche pas |
| **F14** | `complete_structured` ne remonte pas la consommation de tokens | v1.0 : `complete_structured` renvoie `(dict, Usage \| None)` (rupture pré-publication) ; v2.0 : porté par le contrat `EditProducer` (§5.1). Le rapport et les événements l'exposent |

---

## 8. API publique v1.0

### 8.1 Surface

> **Statut (2026-08-01) — la surface de sommet est CALCULÉE, et provisoire
> jusqu'au gel.**
>
> `saknussemm.__all__` portait **95 symboles**, jamais ratifiés : accumulés
> un ajout à la fois, chacun justifié le jour où il a été fait. `S3b` l'a
> réduite aux **68** qu'atteignent deux clôtures transitives, calculées et
> non choisies :
>
> 1. **ce que la façade retourne** — en partant des annotations de retour de
>    `load` / `correct` / `correct_sync` et en suivant les types, pour qu'un
>    appelant puisse nommer la valeur qu'on lui rend ;
> 2. **ce que la couture producteur oblige à nommer** — parce que le README
>    promet « any custom `EditProducer` », et qu'une promesse d'extension
>    sans les types pour l'écrire n'en est pas une.
>
> Reste dehors délibérément : la couture `FormatAdapter` (`RewriteResult`,
> `RewriteMetrics`, `AlignedPair`, `TokenAlignment`). C'est une injection
> optionnelle que la plupart des appelants ne passent jamais, et le
> vocabulaire de comptabilité interne du réécrivain — `R5`, `R8` et `L8`
> l'ont tous déplacé cette année. Le geler sous SemVer à `1.0` promettrait
> une stabilité que rien ne soutient.
>
> Provisoire garde son sens : la série `0.9.x` est explicitement libre de
> couper encore (`packages/saknussemm/docs/versioning.md`) si une clôture se
> révèle fausse. Ce que le cliquet
> (`tests/test_public_api_snapshot.py`) garantit, c'est que la liste ne peut
> pas **regrandir**. Rien n'est gelé sous SemVer avant `1.0.0`.
>
> **Deux portes, deux garanties** (déjà énoncé dans `versioning.md`, répété
> ici parce que c'est la section normative) :
>
> - `saknussemm.*` — la porte d'entrée. Sous SemVer strict **à partir de
>   `1.0.0`**, et déjà réduite à la clôture calculée.
> - `saknussemm.core.*`, `saknussemm.formats.*`, `saknussemm.producers.*` —
>   les chemins de modules. Supportés et documentés ; c'est la porte que le
>   dépôt emprunte lui-même (**864 imports par chemin de module contre 65
>   depuis le sommet**), et un symbole rétrogradé par `S3b` y reste
>   importable. Ce n'est donc pas une suppression, c'est un déplacement.
>
> Le bloc ci-dessous reste la photographie d'origine de la v2.0 : il dit
> quelles **entrées** existent, pas ce que `__all__` contient.

```python
# parse
build_document_manifest(files) -> DocumentManifest          # existant
parse_alto_file(path, ...) -> tuple[list[PageManifest], _Element]

# pipeline
CorrectionPipeline(
    provider: BaseProvider,
    observer: PipelineObserver,
    output_writer: OutputWriter,
    config: ChunkPlannerConfig | None = None,
    retry_policy: RetryPolicy | None = None,      # F9
    guard_config: GuardConfig | None = None,      # F13
)
await pipeline.run(
    document_manifest=..., api_key=..., model=..., provider_name=...,
    source_files=..., run_id=None,
    should_abort=None,                            # F10
    apply=True,                                   # §9 dry-run
) -> CorrectionResult

pipeline.run_sync(...)                            # façade asyncio.run, documentée

# Note (ADR-011, 2026-07) : la persistance a quitté la surface moteur —
# plus de `output_writer` au constructeur ni de `apply=` sur run() ; le
# résultat porte les artefacts (`result.corrected_files`, `result.report`,
# `result.decisions`) et `result.write(dir)` est l'aide côté appelant.
# run() ne mute plus jamais son entrée (copie interne, tranche E) : le
# garde « one run per instance » (ADR-005) est retiré, le moteur est
# réentrant. (La résorption §5.1 a déjà retiré api_key/model/provider_name
# de run() — voir ADR ; le bloc ci-dessus reste la photographie v2.0
# d'origine.)

# bas niveau
rewrite_alto_file(...), extract_output_texts(...)      # dans `__all__`
reconcile_hyphen_pair(...), check_line(...), plan_page(...)
# ^ PAS dans `__all__`. Ces trois-là étaient déclarés ici « déjà publics,
#   maintenus » ; ils ne l'ont jamais été. Corrigé le 2026-07-28 en
#   retirant la promesse plutôt qu'en l'honorant : le gel de
#   fonctionnalités suspend l'extension de l'API publique, et `S3` réduit
#   la surface au lieu de l'élargir. Ils restent importables depuis
#   `saknussemm.core.hyphenation` / `.guards` / `.planner`, comme tout ce
#   que `S3` rétrogradera.
```

### 8.2 Politiques

`RetryPolicy`, `GuardConfig`, `ChunkPlannerConfig`, `PairingPolicy`,
`LossPolicy` (ADR-012), `ConfidencePolicy`, `RoutingPolicy` : objets frozen
Pydantic, tous avec un défaut reproduisant le comportement actuel. Elles
étaient quatre à la rédaction de cette section ; les trois dernières sont
arrivées avec la comptabilité des pertes, les confiances et le routage
sélectif. **Empreinte de configuration** (`policy_fingerprint()` : hash stable
du dump JSON trié) exposée pour la provenance (§11).

L'empreinte composite `config_fingerprint()` en couvre **cinq** :
`chunk_planner`, `guard`, `loss`, `pairing`, `retry`. `ConfidencePolicy` et
`RoutingPolicy` en sont dehors, et le restent. Ce paragraphe disait « tant
qu'elles ne peuvent pas changer les octets livrés » ; c'était faux pour le
routage dès qu'une borne est posée : une ligne `SKIP` garde son texte OCR,
donc deux runs aux bornes différentes livrent des octets différents sous la
même empreinte (relevé `G4`, 2026-09-01). Les faire entrer dans l'empreinte
déplacerait toutes celles déjà estampillées dans des fichiers livrés ; les
y faire entrer sous condition rendrait l'empreinte non recalculable à partir
des seuls objets de politique. D'où la règle (2026-10-01) : **l'empreinte
reste ce qu'elle est, et le rapport porte à côté d'elle
`RunProvenance.active_policies`** — `routing` (ses bornes), `review` (ses
règles), `confidence` (son mode), `qe_scorer` (son nom), chacune sous forme
de son propre dump JSON et seulement hors de son état neutre, de sorte qu'un
consommateur recalcule `policy_fingerprint()` de chacune depuis le rapport
seul. Les fichiers livrés n'estampillent toujours que l'empreinte.

Note (ratifiée 2026-07-07) : `CorrectionPipeline(pairing_policy=…)` est un
paramètre de **provenance uniquement** — l'appariement des paires de
coupure se fait au parse, avant le pipeline, et le pipeline ne ré-apparie
jamais. Il existe pour que `config_fingerprint()` couvre les politiques
qui décident du texte livré. Contrat appelant : passer la **même** `PairingPolicy`
qu'au parse ; le pipeline ne peut pas le vérifier, et une politique
différente rendrait l'empreinte estampillée mensongère.

### 8.3 Typage & qualité

`py.typed`, `mypy --strict` en CI, `ruff`, couverture cible 85 % sur le
paquet lib. `__all__` exhaustifs (déjà en place).

### 8.4 Contrat d'erreurs

Hiérarchie unique : `CorrectionError` (base) ← `ParseError`,
`ValidationError` (réponse producteur), `HyphenIntegrityError`,
`CorrectionAborted`. Les `ValueError` nues actuelles migrent sous cette
racine en conservant l'héritage `ValueError` (compatibilité `except`).

### 8.5 Versionnage

SemVer strict après première publication. Les ruptures listées ici (F12,
§5.1, §8.4) se font **avant** le premier tag publié — d'où l'intérêt de les
grouper en v1.0. La ré-organisation de modules (§3) attend la v2.0, avec
alias d'import dépréciés pendant une version mineure.

---

## 9. Observabilité, rapport, dry-run

- **`CorrectionReport` public** : le `LineTrace` actuel (source → entrée
  modèle → sortie modèle → projeté → texte ré-extrait, chemin rewriter,
  raison de repli) devient un artefact de sortie **documenté, schéma JSON
  stable versionné** — plus seulement un fichier interne d'un hôte. C'est
  la matière d'un diff/aperçu côté consommateur.
- **Dry-run** : depuis ADR-011 (2026-07), TOUT run est un dry-run côté
  moteur — il n'écrit jamais rien ; il renvoie rapport + EditScript
  normalisé + XML corrigé (`result.corrected_files`). La « vraie »
  écriture est le choix de l'appelant (`result.write(dir)`, ou la
  transaction de l'hôte). Usage : prévisualisation, ou mesure sans
  écriture par un consommateur qui benche.
- Les événements (`PipelineEventType`) restent la seule interface de
  progression ; `chunk_downgraded` (F1) s'ajoute au contrat SSE.
- **Un événement ne nomme pas son run.** Mesuré le 2026-08-17 : sur deux
  `run()` concurrents, 106 événements et aucune des 20 clés de charge utile
  ne dit de quel run il s'agit, tandis que les `page_id` collisionnent entre
  documents. Un observateur partagé ne peut donc rien attribuer : un
  observateur par run, ou un run à la fois. Le `run_id` n'existe que sur le
  rapport, c'est-à-dire après la fin.

---

## 10. Sécurité

- `make_safe_parser()` obligatoire pour **tout** parse lxml, y compris le
  futur parser PAGE ; le test-contrat grep (`test_xml_security.py:182`)
  s'étend au nouveau dossier `formats/`.
- Zéro réseau et zéro filesystem dans `core/` (déjà vrai, maintenu par
  l'arbre d'imports §3).
- `sanitize_error` conservé tel quel (patterns de secrets) et appliqué à
  tout message d'événement sortant.

---

## 11. Reproductibilité & provenance

- `RetryPolicy.deterministic()` + producteur règles : chaîne entièrement
  reproductible à réponse LLM égale ; documenter que la reproductibilité
  totale exige un cache de réponses **côté consommateur** (hors lib — un LLM
  reste non déterministe même à température 0).
- Le `processingStep` écrit dans l'ALTO/PAGE corrigé porte :
  `provider/model` (existant) + **version de la lib** + **empreinte de
  configuration** (§8.2). Un XML corrigé dit par quoi et sous quelle
  politique il a été corrigé.
- **L'ordre de lecture des pages fait partie du contrat de sortie.** La
  réconciliation d'une unité de césure inter-pages suppose que la page
  antérieure a été décidée d'abord — le code l'écrit à découvert : *« the
  tail always sits on the earlier page and is decided before the head
  exists »*. Mesuré le 2026-08-17 : exécuter les pages dans un autre ordre
  laisse textes et statuts identiques mais **change le sha256 du XML**, les
  attributs `SUBS_*` d'une unité dont les deux moitiés tombent étant
  préservés en séquentiel et supprimés autrement. Un appelant ne doit donc
  ni réordonner ni paralléliser les pages. Réordonner les **fichiers** d'un
  même appel est en revanche garanti sans effet, et testé.
- **La réentrance est une propriété du moteur, pas de la composition.** Deux
  `run()` concurrents sur une instance donnent des décisions et des octets
  identiques aux runs séquentiels (ADR-011 slice E, mesuré). Mais rien dans
  le protocole `EditProducer` n'exige la sûreté en concurrence : mesuré, un
  producteur portant un budget par run perd 41 courses sur 42 appels, finit
  à −2, refuse deux appels qui n'auraient pas dû l'être — et **les deux runs
  se terminent « avec succès »**. Un producteur, scorer ou observateur
  partagé doit être sans état par run, ou instancié par run. La bibliothèque
  ne le vérifie pas et ne le détecte pas.

---

## 12. Hors-périmètre (explicite et définitif)

OCR ; segmentation/analyse de mise en page ; métriques d'évaluation
(CER/WER…) ; rendu HTML/visualisation ; IIIF ; conversion générique
ALTO↔PAGE↔TEI (on **corrige dans** un format, on ne convertit pas entre
formats) ; gestion de jobs/persistance/SSE (l'affaire d'un hôte) ; providers HTTP
concrets (un hôte, ou un paquet séparé) ; NER/enrichissement sémantique.

**Et — explicitement — toute manipulation de pixels (I4)** : chargement
d'image, découpe/crop, mise à l'échelle, encodage base64, construction d'un
message multimodal, appel VLM. La lib **expose l'ancrage** (géométrie déjà
dans le manifest, référence d'image opaque) pour qu'un producteur vision
résolve les pixels *lui-même* (§5.2 bis) ; elle ne les résout jamais. Faire
entrer PIL/Pillow ou de l'I/O image dans `core` briserait « zéro I/O dans le
cœur » — c'est la ligne rouge la plus stricte.

Chacun de ces points a un propriétaire naturel : l'application appelante ou
un outil dédié — **jamais la lib**. Les specs qui proposeraient de les ajouter
ici doivent citer ce paragraphe et argumenter contre.

---

## 13. Plan de livraison — REMPLACÉ

> **Ce tableau n'est plus le plan.** Il est conservé pour la provenance des
> tranches v1.0 → v2.x. Le plan unique et vivant est **`docs/PLAN.md`**, qui a
> consolidé ce §13 avec `PLAN-1.0` et `ROADMAP_LIB_V3` le 2026-07-25.
>
> État réel à cette date : le **contenu** de v1.0 à v2.0 est dans le code
> (F1–F14 : 14/14 ; PAGE P1–P7 : 7/7, P6 partiel par conception ; protocole §4
> E1–E6 complet), mais **rien n'a jamais été publié** (0 tag git), la DoD de
> v1.1 n'est pas tenue (aucun export eScriptorium, parité §6.3 partielle,
> byte-parity ALTO seulement), et v2.1/v2.x ne sont pas commencées.

Chaque tranche laisse la lib **publiable et verte** ; pas de branche longue.

| Version | Contenu | DoD |
|---|---|---|
| **v1.0** | Corrections F1–F14 ; rapatriement des tests (F11) ; API §8 (politiques, erreurs, usage, dry-run sans EditScript) ; `CorrectionReport` public ; publication PyPI sous le nom retenu (§14) | Suite verte dans le paquet ; `mypy --strict` ; byte-parity sur corpus de non-régression (mêmes entrées + `RetryPolicy.default()` → mêmes sorties qu'avant, hors fixes F2/F4/F6 documentés) ; CHANGELOG |
| **v1.1** | Backend **PAGE XML** (§6.2) : parser, rewriter 4 chemins, césure heuristique, tests de parité §6.3 | Round-trip byte-stable PAGE ; conventions **P5** (caractères de césure) et **P7** (provenance/XSD) confirmées sur exports réels Transkribus **et** eScriptorium ; mêmes gardes vertes sur ces corpus |
| **v2.0** | Protocole d'édition (§4) : `EditScript`, normalisation `match→range`, ré-expression `replace_line` (zéro changement de comportement, prouvé par les snapshots v1) ; **producteur règles** (§5.3) ; **enveloppe vision** (§5.2 bis : `EditProducer.wants_*`, `page_images`, géométrie + `image_ref` dans le payload — la lib forwarde, ne crope pas) ; ré-organisation §3 avec alias dépréciés | Snapshots v1 inchangés via le chemin protocole ; moteur de règles testé à l'octet ; producteur vision *mocké* prouvant que géométrie + `image_ref` transitent sans que la lib ouvre l'image ; doc du protocole |
| **v2.1** | Producteur LLM en mode `replace_span`/`MatchAnchor` (opt-in), benché contre `replace_line` avant d'être recommandé | Comparatif CER/coût publié ; le mode span n'est défaut nulle part sans preuve |
| **v2.x** | Profil `GuardConfig.vision()` (§7 F13) calibré au banc ; sérialisation texte pour modèle spécialisé (§5.4) — chacun uniquement quand son consommateur existe et se benche | — |

---

## 14. Nom & packaging

`alto-core`, `saknussemm`, `anastylose` sont libres sur PyPI (vérifié).
Recommandation : **`saknussemm`** — le terme d'imprimerie désignant la liste
des corrections d'un texte imprimé : c'est littéralement ce qu'est un
`EditScript`, ça porte le domaine patrimonial, et ça survit à l'extension
PAGE XML (contrairement à `alto-core`, qui devient faux en v1.1).
`anastylose` (remontage d'un monument à partir de ses pièces d'origine) est
la belle alternative métaphorique. Décision avant le premier tag — on ne
renomme pas un paquet publié.

Le paquet vit dans `packages/saknussemm/` — un reste de l'époque où ce
dépôt en contenait plusieurs, et qui disparaîtra quand l'arbre sera
aplati. Ses consommateurs l'installent comme n'importe qui : depuis git
tant que rien n'est publié, depuis PyPI ensuite. Aucun n'a de chemin
privilégié vers lui, et c'est ce qui garantit que le chemin normal
fonctionne.

---

## 15. Consommateurs & couplage (contrainte SUR la lib)

La lib est **agnostique de ses consommateurs** : elle ne nomme, n'importe et
ne cible aucune application en particulier. Ce qui la concerne, et qui est
une contrainte de conception, se réduit à ces règles :

- **Couplage à sens unique.** Les consommateurs dépendent de la lib ; la lib
  ne dépend d'aucun consommateur, ni par import, ni par entry-point qui
  inverserait le sens. Se distribue proprement (PyPI) et s'installe comme
  dépendance standard, éventuellement derrière un extra optionnel côté
  consommateur.
- **Toute variabilité passe par l'injection**, pas par un cas particulier
  câblé : le producteur (`EditProducer`/`BaseProvider`), l'observateur, le
  writer, et les politiques (`RetryPolicy`, `GuardConfig`, `ChunkPlannerConfig`,
  `PairingPolicy`, `page_images`) sont les *seuls* points par lesquels un
  consommateur adapte la lib. Un besoin qui n'y rentrerait pas est soit un
  manque d'enveloppe à corriger dans la lib, soit un concern hors-périmètre
  (§12) — jamais un `if consommateur == …`.
- **La lib ne suppose aucun environnement d'exécution** : ni job store, ni
  transport (SSE), ni gestion de clés, ni système de fichiers imposé — tout
  cela appartient à l'appelant (§12).

La façon dont un consommateur donné câble ces points d'injection (adapters,
ponts provider, réutilisation de sa propre machinerie image/VLM) est **sa**
spec, pas celle de la lib, et vit chez lui.
