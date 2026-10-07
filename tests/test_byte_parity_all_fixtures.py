"""Le différentiel d'octets sur TOUT le corpus, et pas sur un échantillon.

Quinze documents — neuf ALTO, six PAGE — × trois scénarios déterministes,
épinglés par sha256. C'est le filet que toute simplification traverse : si
une réécriture change un seul octet livré sur un seul fixture, elle le dit
ici avant d'être relue.

`test_byte_parity_corpus.py` couvrait deux fichiers ALTO et deux scénarios ;
`test_byte_parity_page_corpus.py` couvrait deux fixtures PAGE. Onze documents
du dépôt — dont les deux pages NewsEye de 2,4 Mo, les trois pages Gallica
épinglées et les paires ALTO/PAGE de Descartes et La Fayette — ne passaient
sous aucune empreinte. Ces deux modules restent : ils portent la
classification historique de chaque déplacement d'empreinte, qui est un
savoir que ce fichier ne remplace pas.

Huit empreintes ALTO 4 ont changé pour une provenance conforme au schéma :
Descartes et La Fayette × quatre scénarios. Comparaison avec la révision
f763824 : les 33 et 14 TextLine et tout ce qui est hors Processing sont
identiques à l'octet. Seul Processing change ; les deux violations XSD de
chaque sortie disparaissent. Les 28 autres empreintes ALTO restent identiques.

Onze empreintes PAGE ont changé pour invalider les TextEquiv des régions
dont une ligne a changé : Descartes raw scripted/probe (4/4 éléments),
La Fayette raw scripted/probe/drift (2/1/1), NewsEye 0250199004 (135/46/142)
et 0253902003 (138/62/20). Contre f763824, tous les TextEquiv de ligne
restent identiques. Seule la ligne tl_425 de 0250199004/drift perd aussi
ses quatre Word, dont les frontières ne permettent plus un appariement
positionnel. Après ces seuls retraits, chaque arbre est identique à l'octet ;
les treize autres empreintes PAGE sont inchangées, dont toutes les identités.

Les trois scénarios, et ce que chacun exerce :

``identity``
    chaque ligne corrigée par son propre texte OCR, réécriture directe. Le
    chemin UNTOUCHED de bout en bout : rien ne doit bouger dans l'arbre.

``scripted``
    corrections déterministes par index (1 ligne sur 7 gagne un mot → chemin
    lent ; 1 sur 3 change un caractère → chemin rapide), réécriture directe.
    C'est la géométrie des tokens qui est sous empreinte.

``probe``
    le **pipeline entier**, avec un ``RulesProducer`` déterministe. C'est
    celui qui compte pour les refactorisations du cœur : il exerce la
    planification, le protocole d'édition (E1-E5), le validateur, la
    réconciliation de césure, les trois étages de garde, les passes
    document-wide et la projection. Mesuré à l'écriture : 233 lignes
    corrigées et **10 replis ``hyphen_pair_fallback``** répartis sur trois
    fixtures, plus 5 ops refusées par les gardes d'édition sur
    ``X0000002.xml`` — donc les chemins de refus sont bien traversés, pas
    seulement le chemin nominal.

Les règles de la sonde sont choisies pour **déclencher**, pas pour être
justes : ``rn→m``, ``cl→d``, ``ii→n``, ``vv→w`` sont de vraies confusions
d'OCR appliquées sans lexique, donc elles produisent aussi des corrections
fausses. C'est sans importance ici et c'est le même parti que le ``" zz"``
ajouté par ``scripted`` : ce qui est sous empreinte est le déterminisme du
chemin, pas la qualité linguistique.

**Si une empreinte bouge, ne pas la régénérer.** Classer d'abord le diff par
TextLine (le patron de ``test_byte_parity_corpus.py``), puis ne mettre à jour
que pour un changement d'octets délibéré, en le nommant dans le message de
commit. Pendant la vague `RS`, une empreinte qui bouge sur une étape de
simplification est un échec de l'étape.

La réécriture est invoquée sans arguments de provenance, donc ces empreintes
sont indépendantes de la version de la bibliothèque.

**Trente empreintes ont bougé le 2026-09-30, par la seule ligne de
provenance.** ``GuardConfig`` gagne ``max_unanchored_words`` (``VR-12``,
défaut ``None`` : rien n'est vérifié), donc l'empreinte de configuration par
défaut change et, avec elle, le ``config …`` que le pipeline inscrit dans
chaque fichier livré. Classé contre ``main`` avant de régénérer, les quinze
fixtures × ``probe`` et ``drift`` : une ligne différente par fichier, celle
du ``<Comments>`` / de la provenance, aucune TextLine, aucun texte, aucune
géométrie. Les scénarios ``identity`` et ``scripted`` n'inscrivent pas
d'empreinte et n'ont pas bougé.

**Dix empreintes ont bougé le 2026-09-29, pour un changement délibéré de
la géométrie du chemin lent** (``formats/alto/_geometry.py``) : les boîtes
des mots que la correction ne touche pas sont désormais GARDÉES, et seuls
les passages qu'elle a changés sont redessinés, dans les boîtes qu'ils
consomment, avec des largeurs de lettres apprises sur la page. Classé par
TextLine contre ``main`` avant de régénérer, lignes différentes / lignes du
fichier : *Le Temps* scripted **161 / 1 145**, ``X0000002.xml`` scripted
**81 / 566** et drift **1 / 566**, ``bnf-alto-prod`` scripted **4 / 27**,
``bnf-alto-prod-latin1-control`` **4 / 27**, Gallica p.15 **4 / 31** et
p.9 **6 / 43**, ``sample.xml`` scripted **2 / 10**, Descartes **1 / 33**,
La Fayette **1 / 14** — toutes des lignes du chemin lent (le `` zz`` ajouté une ligne
sur sept, ou la dérive), géométrie seule (HPOS/WIDTH des String, SP et
HYP), aucune dérive de texte ni de structure. Les enfants ne pavent plus la
ligne de bord à bord : un mot gardé garde la boîte que le producteur lui
avait donnée, blancs compris, et le mot ajouté est dessiné après le dernier
à sa taille naturelle — au corps de SA ligne (échelle et espace relus sur
les mots gardés de la ligne : sur des insertions fabriquées, 60-90 → 74-88 %
des mots remis avec leurs deux bords à un demi-caractère). Les empreintes ``identity`` et ``probe`` n'ont pas
bougé. Mesure qui a décidé du changement : dépôt ``hans``, rapports ``H21``
et ``H22`` — 79-84 % de frontières justes pour la redistribution de toute
la ligne, 98,6-99,8 % en gardant les boîtes et en n'ouvrant que la boîte
touchée, vérifié de bout en bout sur le vrai ``rewrite_alto_file``.

``sample.xml`` scripted a été ré-épinglé une seconde fois le 2026-09-30,
avant fusion : le modèle de largeurs est désormais appris AVANT que la
première ligne reconstruite soit vidée (elle manquait à l'ajustement — sur
un fichier d'une ligne, c'était toute l'évidence). Sur cette page de dix
lignes cela compte : les deux mêmes TextLine, et dans chacune le seul
`` zz`` inséré change de largeur (99 → 81 px, 57 → 55 px, le HYP suit de
2 px). Aucune autre empreinte ne bouge.

``X0000002.xml`` drift est la seule empreinte que cette branche ET celle
du 2026-09-24 déplacent ; recalculée à la fusion de ``main``, classée
contre ``main`` : **1 TextLine sur 566** (``TL000292``, chemin lent),
géométrie seule, tout le reste du fichier identique à l'octet — le même
1 / 566 que ci-dessus, sous la nouvelle ligne de provenance.

**Et trente encore le 2026-09-24, pour la même raison, un champ plus loin.**
``ChunkPlannerConfig`` a gagné ``coalesce_blocks`` (défaut ``False``,
inerte) : son empreinte change, donc l'empreinte composite de configuration
estampillée dans chaque fichier livré. Classé de la même façon contre
``main`` : **toutes les TextLine identiques**, seule la ligne de provenance
diffère. Ré-épinglé en le nommant.

**Trente empreintes ont bougé le 2026-09-24, et pour une raison classée.**
``GuardConfig`` a gagné deux champs (``attachment_scope``,
``attachment_twin_similarity``, défauts inertes), donc son
``policy_fingerprint()`` change, donc le ``config …`` estampillé dans le
``processingStep`` de chaque fichier livré change. Classé TextLine par
TextLine sur les 30 sorties ``probe``/``drift`` contre ``main`` : **toutes
les TextLine sont identiques**, seule la ligne de provenance diffère.
C'est le cas que ``docs/versioning.md`` prévoit — un changement de
politique, non cassant, nommé au CHANGELOG. Les scénarios ``identity`` et
``scripted`` ne passent pas par le pipeline et n'ont pas bougé.

**Deux empreintes ont bougé le 2026-08-25, et pour un défaut réel.**
``_compute_geometry`` pesait ses tokens en flottants — ``0.6`` par caractère
d'espace — et sommait ces poids avec ``sum()``. CPython 3.12 a donné à
``sum()`` la sommation compensée de Neumaier : les mêmes dix-sept tokens
pèsent ``48.80000000000001`` sur 3.11 et ``48.8`` sur 3.12, donc la géométrie
du fichier LIVRÉ dépendait de l'interpréteur. Les poids sont des entiers
depuis, en dixièmes de caractère, et chaque frontière est arrondie depuis une
division exacte plutôt que depuis un flottant qui s'accumule.

Classé par TextLine avant de régénérer, comme la règle l'exige : **1 ligne
sur 33** pour Descartes, **1 sur 1 145** pour la page Gallica ; géométrie
seule dans les deux cas, deux éléments décalés d'un pixel, aucune dérive de
texte ni de structure, et la somme des ``WIDTH`` inchangée (5 542 → 5 542 ;
1 806 → 1 806) — l'invariant de somme exacte tient.

La preuve que le correctif converge plutôt qu'il ne déplace : la nouvelle
empreinte 3.11 de Descartes est **exactement** celle que 3.12 produisait
déjà. Les empreintes de ``test_byte_parity_corpus.py``,
``test_byte_parity_page_corpus.py`` et ``test_rewriter_byte_stability.py``
n'ont pas bougé — 81 des 83 assertions d'octets du dépôt sont indifférentes
au correctif, ce qui est la mesure de son rayon.

C'est ce module qui a trouvé le défaut, et rien d'autre ne le pouvait :
aucune empreinte préexistante ne tombait sur un arrondi à la demi-unité.

**Sensibilité mesurée, et les deux trous qu'elle a trouvés.** Cinq mutations
sur le chemin livré, comptées sur les 64 assertions du module :

  ============================================  =========
  mutation                                      tombent
  ============================================  =========
  slots PART1/BOTH intervertis dans `pairing`      17
  garde de similarité de `check_line` désactivée   16
  budget E4 par ligne rendu illimité               30
  ``reconcile._build_hyphen_pairs`` neutralisée     0
  ``indexing._cross_page_partners`` neutralisée     0
  ============================================  =========

Les deux dernières sont des trous, et ils sont dits ici parce qu'un filet
dont on ignore les mailles se lit comme un filet complet :

* ``_build_hyphen_pairs`` alimente le contrôle d'intégrité de paire du
  VALIDATEUR, pas une transformation. La neutraliser retire une garde, et une
  garde retirée ne change les octets que si un producteur propose de fusionner
  une paire — ce qu'aucun des quatre scénarios ne fait.
* ``_cross_page_partners`` ne rend quelque chose que sur une unité de césure à
  cheval sur deux pages. Les quinze fixtures sont chargées un fichier à la
  fois et n'en portent aucune.

Ces deux fonctions sont couvertes par
``tests/hyphenation/test_pair_map_agrees_with_the_primitives.py``, qui les
compare aux primitives dirigées plutôt qu'aux octets. Les deux nets sont
nécessaires et aucun ne remplace l'autre.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import pytest

from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.core.schemas import RetryPolicy
from saknussemm.formats.loader import adapter_for_format, build_document_manifest
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._paths import EXAMPLES, TESTS

#: Tous les documents XML que le dépôt porte, ALTO et PAGE confondus. Le
#: chemin est relatif à la racine ; le format est reniflé, jamais déclaré ici.
_FIXTURES: dict[str, Path] = {
    "sample.xml": EXAMPLES / "sample.xml",
    "X0000002.xml": EXAMPLES / "X0000002.xml",
    "bnf-alto-prod-bpt6k5406037v-f40.xml": (
        EXAMPLES / "bnf-alto-prod-bpt6k5406037v-f40.xml"
    ),
    "bnf-alto-prod-latin1-control.xml": EXAMPLES / "bnf-alto-prod-latin1-control.xml",
    "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml": (
        EXAMPLES
        / "page"
        / "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml"
    ),
    "Descartes1637_Discours_btv1b86069594_corrected_0014_page_corrected.xml": (
        EXAMPLES
        / "page"
        / "Descartes1637_Discours_btv1b86069594_corrected_0014_page_corrected.xml"
    ),
    "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml": (
        EXAMPLES
        / "page"
        / "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml"
    ),
    "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml": (
        EXAMPLES
        / "page"
        / "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml"
    ),
    "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_corrected.xml": (
        EXAMPLES
        / "page"
        / "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_corrected.xml"
    ),
    "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml": (
        EXAMPLES
        / "page"
        / "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml"
    ),
    "0250199004.xml": EXAMPLES / "page" / "newseye-fr" / "0250199004.xml",
    "0253902003.xml": EXAMPLES / "page" / "newseye-fr" / "0253902003.xml",
    "bpt6k2206225_p0015.alto.xml": (
        TESTS / "external_corpus" / "pinned" / "bpt6k2206225_p0015.alto.xml"
    ),
    "bpt6k2324031_p0002.alto.xml": (
        TESTS / "external_corpus" / "pinned" / "bpt6k2324031_p0002.alto.xml"
    ),
    "bpt6k6478860m_p0009.alto.xml": (
        TESTS / "external_corpus" / "pinned" / "bpt6k6478860m_p0009.alto.xml"
    ),
}

#: Confusions d'OCR appliquées sans lexique. Choisies pour déclencher sur
#: tous les corpus — voir la docstring du module sur pourquoi leur justesse
#: linguistique n'entre pas en compte.
_PROBE_RULES = [
    SubstitutionRule("ſ", "s", name="long_s"),
    SubstitutionRule("ﬁ", "fi", name="fi_ligature"),
    SubstitutionRule("ﬂ", "fl", name="fl_ligature"),
    SubstitutionRule("rn", "m", name="rn_m"),
    SubstitutionRule("cl", "d", name="cl_d"),
    SubstitutionRule("ii", "n", name="ii_n"),
    SubstitutionRule("vv", "w", name="vv_w"),
]

#: Le scénario ``drift`` : remplacer CHAQUE lettre par ``z``. Le producteur
#: propose alors, ligne par ligne, quelque chose qui ne ressemble plus à sa
#: source — donc les gardes doivent refuser, et le fichier livré doit être
#: une resérialisation de la source. Mesuré à l'écriture sur
#: ``X0000002.xml`` : 306 ``too_different_from_source``, 222
#: ``hyphen_pair_fallback``, 2 ``adjacent_duplicate_detected`` et 1 824 ops
#: refusées par les gardes d'édition.
#:
#: Ce scénario existe parce que ``probe`` ne suffisait pas : mesuré, le
#: court-circuit de ``check_line``'s similarity guard ne faisait tomber
#: AUCUNE des 48 empreintes — la sonde ne produit que des corrections très
#: similaires, donc l'étage C n'était jamais atteint en refus. Un filet qui
#: ne voit pas une garde désactivée n'est pas un filet sur cette garde.
_DRIFT_RULES = [
    SubstitutionRule(r"[a-zA-Zàâäéèêëîïôöùûüç]", "z", regex=True, name="every_letter"),
]

_GOLDEN: dict[tuple[str, str], str] = {
    (
        "sample.xml",
        "identity",
    ): "6b1c8ea81c28076a10b65a8e147442063a4e8671cd4ee870ba67021920c0ed16",
    (
        "sample.xml",
        "scripted",
    ): "0f5614cd95c60f6332c1e6078b577ac9f7ef15e5589703125c8af86ecf076a8c",
    (
        "sample.xml",
        "probe",
    ): "1904204089d546aa4a9a69a2eb31c8d8b42f62a76ec8d342721999543f4d1fc6",
    (
        "sample.xml",
        "drift",
    ): "3b54da787cee6c668476f772af0a2adfba7beea15e514944d5ec0ebb8a71e090",
    (
        "X0000002.xml",
        "identity",
    ): "6b29f2269127f5ec9af15b6196e2e4c2ef48db4bf804aa616c2e0477f4db102a",
    (
        "X0000002.xml",
        "scripted",
    ): "d491cebff29631a5b10555b6a97730803f19226e827f79c350739d5c18db53b7",
    (
        "X0000002.xml",
        "probe",
    ): "d03482f8b04469e3c5d293a2624cf9feb69c3894cd30f1dc31be10e1176f2b32",
    # Ré-épinglée (VR-11) : trois TextLines d'une unité de césure
    # (TL000188–190) que la bouillie « zzzz » traversait — l'étage B ne juge
    # que la migration entre les moitiés, et un membre réconcilié sautait
    # l'étage C. Le plancher les rend à la source ; rien d'autre ne bouge.
    (
        "X0000002.xml",
        "drift",
    ): "6d89e298850c93000aa65387b8cce1d02cd1d8708d08733bbc5d0197682f0e00",
    (
        "bnf-alto-prod-bpt6k5406037v-f40.xml",
        "identity",
    ): "c260bcfcad4a909dfae9e1161f9766df8b72ef3eba61dfab95a59546f2486401",
    (
        "bnf-alto-prod-bpt6k5406037v-f40.xml",
        "scripted",
    ): "f731f9599931849856e68b503fabc288b0638bcd179a7a6b50ac901c88c1281b",
    (
        "bnf-alto-prod-bpt6k5406037v-f40.xml",
        "probe",
    ): "d2d0c717bcaa670771f7aa30da357a758dc647606e8064b110f892f05f6684ab",
    (
        "bnf-alto-prod-bpt6k5406037v-f40.xml",
        "drift",
    ): "56791fe2165c45b3568a7b35de32e4205cf29332f0b909fbd217a5f54092bc9a",
    (
        "bnf-alto-prod-latin1-control.xml",
        "identity",
    ): "c260bcfcad4a909dfae9e1161f9766df8b72ef3eba61dfab95a59546f2486401",
    (
        "bnf-alto-prod-latin1-control.xml",
        "scripted",
    ): "f731f9599931849856e68b503fabc288b0638bcd179a7a6b50ac901c88c1281b",
    (
        "bnf-alto-prod-latin1-control.xml",
        "probe",
    ): "d2d0c717bcaa670771f7aa30da357a758dc647606e8064b110f892f05f6684ab",
    (
        "bnf-alto-prod-latin1-control.xml",
        "drift",
    ): "56791fe2165c45b3568a7b35de32e4205cf29332f0b909fbd217a5f54092bc9a",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "identity",
    ): "c0db1f51d0863344803ef544a54c78fe34a526cff57b09effac8de715122776b",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "scripted",
    ): "04582c3e35df01837da3feb1bf31b995653d0927fecaa70f8329ed8c60ea4a79",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "probe",
    ): "a72322fbd2ebabd52a4c4f1864e3074d14f95f61287cc5f7790a58ce35738c72",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "drift",
    ): "0377f03058f31af4e769c1de441a069d17e423aded208303bcfd418d5d388d6d",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_corrected.xml",
        "identity",
    ): "e8f214182afc933fab3c5a1604f7aac9a538cbe3f31d40528df798a6734bb9a5",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_corrected.xml",
        "scripted",
    ): "9da43aad245228308b44abdff6db43e4409bb5f5b753d26adae1135a187e3d66",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_corrected.xml",
        "probe",
    ): "426736d6f45f4911a8d8a91e6937bed1188c082138e01ca75e7a0b529d49ab51",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_corrected.xml",
        "drift",
    ): "286ebf47c241d476b3a2dd97678e99f84f134ed264b2ce31af69908425d2f51b",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        "identity",
    ): "afcf40824bc272d78b4b41fee75d76874ee92ee4fa63316581983b049f869a9a",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        "scripted",
    ): "476fe97c74d9eddda45dc40a3a9b79cb0c047c03eb7ca45860669dff20b88cf0",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        "probe",
    ): "e0fbe17c6ce5236749497668cc0fe4857cc32aadb6bcac7d5c2e1d554c096ab2",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        "drift",
    ): "3909066b9394dc2df286754a6e9c7fd93319ff624e12a224f6b901ebf6165a3d",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "identity",
    ): "89225c4aaf3e38b1424df79be35f18352da80a8246423b4454498ebeb48830f5",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "scripted",
    ): "1cd281a02a8f1a001eac8ef566daebb6d37a8633dc63343fc7b435f7107f640d",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "probe",
    ): "ab445070fa8349a516aa49aa9205e5521b5b608b573da1dc4905fb51f37bba5d",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "drift",
    ): "cadd6ded84863f63e2d859eb9eb2f25bcc78f93a26e7f86b9a1c6910c394ce2e",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_corrected.xml",
        "identity",
    ): "68c8aaad59a8f83ca2fa7305e9d9eeacc055364222f3d3c2e3124faedba1b6cf",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_corrected.xml",
        "scripted",
    ): "4031b9982cf7ab9f4e933989ee93b73de231753898dc0fa99185d259f409980d",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_corrected.xml",
        "probe",
    ): "fc2c6f68ab11e86a356dbc83a40d40eff2b10c89ca3bf80f12176af71b549306",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_corrected.xml",
        "drift",
    ): "488abca12e6bacf72c6b7e7efad067663df392b104acd9f41a2c7f1603a69499",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        "identity",
    ): "4b38b1e1ecdcc1e29ec68056115e8a1ab234414a2da3c8d05efe08bd1d7e7c7d",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        "scripted",
    ): "10c62e508fcb7ea06b98f7190a3bf3d2bf380c95a50cb0998f40adeb17160295",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        "probe",
    ): "d18835df53d3a0aa978a400c5eb007ebd7f70d6c125b0493b1eb35345cfdd03d",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        "drift",
    ): "e695256928e1ffdb265d091eef0f5f534678d81a153c47b1331b184dc6fa8e01",
    (
        "0250199004.xml",
        "identity",
    ): "6aa03461ec43921e35e3b9549c0f4c905137a7c050453d0fb2e649f3e6a87c68",
    (
        "0250199004.xml",
        "scripted",
    ): "b747b6950e2effbaf0fb743bf2821ce3aaface47959cc267b8165d8bbe39ddbc",
    (
        "0250199004.xml",
        "probe",
    ): "49af1ecc10a96649d1d5392ce4c9fb7003564c36afdabe8bd2142dec94d4c507",
    (
        "0250199004.xml",
        "drift",
    ): "78d735f07bbf74c6594b2cb6b08e8b622d486411f9af1cf821d1b8452ad6b056",
    (
        "0253902003.xml",
        "identity",
    ): "5ce0e9f5d144e5b392f6bbf3cdf1cd692d85e37d9282f843bf9c0e27c11134b0",
    (
        "0253902003.xml",
        "scripted",
    ): "45c000c7e4c78adb97fa29067e052b22ec553731694d56fd5a41f33ac3c39aa2",
    (
        "0253902003.xml",
        "probe",
    ): "bf03bf8850a411ef6de8582db5b9f027d0b1ec9fbda0d4993f24509f98a581a9",
    # Ré-épinglée (VR-11) : la paire tl_909/tl_910, même mécanisme que
    # X0000002 ci-dessus — bouillie sur un membre réconcilié, rendue à la
    # source par le plancher ; les 912 autres TextLines sont identiques.
    (
        "0253902003.xml",
        "drift",
    ): "aa868b440652332e2f3039bbc024cb516765a7c614bdfa3c5eb5ce2a1acb9943",
    (
        "bpt6k2206225_p0015.alto.xml",
        "identity",
    ): "9bbec99d79cd50fbb1acf8419ab99a84dcfced34212e07eb1cf6a50d9e482b52",
    (
        "bpt6k2206225_p0015.alto.xml",
        "scripted",
    ): "244af34abdf830aa62efd73d2e368d925b7d3b4070465dbff80d6b8fe0475ac5",
    (
        "bpt6k2206225_p0015.alto.xml",
        "probe",
    ): "fea3a3b09009c3b903604f229e75c9b1ae84cbbdd660cfc83f0d3c877545cf58",
    (
        "bpt6k2206225_p0015.alto.xml",
        "drift",
    ): "1d24c1dc5880ed18685b784407321a60f1e5e5f1358bab4217e624c4aa22a192",
    (
        "bpt6k2324031_p0002.alto.xml",
        "identity",
    ): "36e02bfebccb9aa3024111161a0d08f4f884d0d471d3c1f89b0adb0eb7cea258",
    (
        "bpt6k2324031_p0002.alto.xml",
        "scripted",
    ): "d708078ed8e475b650719b5c63c73c57047279acf718e5d484259046e71949a8",
    (
        "bpt6k2324031_p0002.alto.xml",
        "probe",
    ): "2c5b31d13211bea49aa3e4d7bba1ec57e1c821808c065454029b7fd379c8d840",
    (
        "bpt6k2324031_p0002.alto.xml",
        "drift",
    ): "3ef7a9d9d8b6f4bbdd8946833edd0940127bf53636315f514c92fa9216413c19",
    (
        "bpt6k6478860m_p0009.alto.xml",
        "identity",
    ): "deafbcec70ea6ab1e5b60301ee4f876d515452e1f60e26bde27f6ae659f4afe1",
    (
        "bpt6k6478860m_p0009.alto.xml",
        "scripted",
    ): "223f545decda875718064479f9627f45b642916f2b03851b5221690eac9a6ffb",
    (
        "bpt6k6478860m_p0009.alto.xml",
        "probe",
    ): "c0c70efcf14cc05aba68e82684b7fe4d8d783c98c58770630d7c420b0ceeba2b",
    (
        "bpt6k6478860m_p0009.alto.xml",
        "drift",
    ): "574fe95de8808e4f7373cbcd0e4d95d0233a78a6ee2b9edbd138f3dd5c6158c3",
}


class _SilentObserver:
    """Le pipeline exige un observateur ; ce test n'observe rien."""

    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        pass


def _scripted(index: int, text: str) -> str:
    """La correction scriptée de ``test_byte_parity_corpus.py``, verbatim.

    Reproduite plutôt qu'importée : ce module épingle des octets, et une
    fonction partagée qui changerait déplacerait quinze empreintes sans que
    la cause soit lisible ici.
    """
    words = text.split()
    if not words:
        return text
    if index % 7 == 0:
        return text + " zz"  # +1 mot → chemin lent
    if index % 3 == 0 and "e" in words[0]:
        return " ".join([words[0].replace("e", "3", 1)] + words[1:])
    return text


def _rewrite_directly(path: Path, scenario: str) -> bytes:
    doc = build_document_manifest([(path, path.name)])
    index = 0
    for page in doc.pages:
        for lm in page.lines:
            lm.corrected_text = (
                lm.ocr_text if scenario == "identity" else _scripted(index, lm.ocr_text)
            )
            index += 1
    adapter = adapter_for_format(doc.source_format)
    return adapter.rewrite_file(path, doc.pages, "test", "mock").xml_bytes


def _run_probe(path: Path, rules: list[SubstitutionRule] | None = None) -> Any:
    """Le pipeline entier sur ``path``, producteur déterministe."""
    doc = build_document_manifest([(path, path.name)])
    pipeline = CorrectionPipeline(
        producer=RulesProducer(rules if rules is not None else _PROBE_RULES),
        observer=_SilentObserver(),
        retry_policy=RetryPolicy.deterministic(),
    )
    return asyncio.run(
        pipeline.run(document_manifest=doc, source_files={path.name: path})
    )


@pytest.mark.parametrize(("name", "scenario"), sorted(_GOLDEN))
def test_the_delivered_bytes_are_pinned(name: str, scenario: str) -> None:
    path = _FIXTURES[name]
    if scenario in ("probe", "drift"):
        rules = _PROBE_RULES if scenario == "probe" else _DRIFT_RULES
        xml_bytes = _run_probe(path, rules).corrected_files[path.name]
    else:
        xml_bytes = _rewrite_directly(path, scenario)
    digest = hashlib.sha256(xml_bytes).hexdigest()
    assert digest == _GOLDEN[(name, scenario)], (
        f"{name}/{scenario} : les octets livrés ont bougé. Classer le diff "
        f"par TextLine avant toute chose ; pendant la vague RS, une empreinte "
        f"qui bouge sur une étape de simplification est un échec de l'étape."
    )


def test_every_fixture_of_the_repository_is_under_a_digest() -> None:
    """Un golden qui couvre un échantillon se lit comme un golden complet.

    Le défaut que cette assertion ferme est celui qu'elle a trouvé : onze des
    quinze documents du dépôt n'étaient sous aucune empreinte, et rien ne le
    disait.
    """
    on_disk = {p.name for p in EXAMPLES.rglob("*.xml")}
    on_disk |= {p.name for p in (TESTS / "external_corpus" / "pinned").glob("*.xml")}
    pinned = {name for name, _ in _GOLDEN}
    assert on_disk == pinned, (
        f"documents non épinglés : {sorted(on_disk - pinned)} ; "
        f"empreintes orphelines : {sorted(pinned - on_disk)}"
    )
    for name in pinned:
        scenarios = {s for n, s in _GOLDEN if n == name}
        assert scenarios == {"identity", "scripted", "probe", "drift"}, name


def test_the_probe_reaches_the_refusal_paths_it_claims_to() -> None:
    """Une sonde qui ne fait que le chemin nominal n'est pas un filet.

    Trois propriétés, chacune mesurée à l'écriture, chacune tombant si le
    scénario ``probe`` cesse d'exercer ce que sa docstring annonce : des
    corrections partout, des replis de paire de césure, et des ops refusées
    par les gardes d'édition.
    """
    corrected_by_fixture: dict[str, int] = {}
    hyphen_fallbacks = 0
    edit_rejections = 0
    for name, path in _FIXTURES.items():
        result = _run_probe(path)
        corrected_by_fixture[name] = sum(
            1 for d in result.decisions.decisions if d.final_text != d.source_text
        )
        hyphen_fallbacks += result.fallback_reasons.get("hyphen_pair_fallback", 0)
        edit_rejections += len(result.report.edit_rejections or [])

    silent = [n for n, c in corrected_by_fixture.items() if c == 0]
    assert not silent, (
        f"la sonde ne corrige rien sur {silent} : sur ces fixtures l'empreinte "
        f"`probe` ne vaut pas mieux qu'un run d'identité"
    )
    assert hyphen_fallbacks >= 10, (
        f"{hyphen_fallbacks} replis de paire de césure ; 10 mesurés à "
        f"l'écriture. En dessous, la sonde a cessé d'exercer la réconciliation."
    )
    assert edit_rejections >= 5, (
        f"{edit_rejections} ops refusées par les gardes d'édition ; 5 mesurées "
        f"à l'écriture. En dessous, E1-E5 n'est plus traversé."
    )


def test_a_producer_that_proposes_garbage_delivers_the_source() -> None:
    """La promesse « au doute, repli sur la source », en octets.

    Sous ``drift``, chaque ligne reçoit une proposition qui ne ressemble plus
    à rien. Les trois étages doivent refuser, et ce qui est livré doit être
    ce que la source disait. Les deux assertions sont différentes et il faut
    les deux : la première dit que les gardes ont vu passer la dérive, la
    seconde qu'elles l'ont arrêtée AVANT les octets.
    """
    path = _FIXTURES["bpt6k6478860m_p0009.alto.xml"]
    result = _run_probe(path, _DRIFT_RULES)

    reasons = result.fallback_reasons
    assert reasons.get("too_different_from_source", 0) >= 30, (
        f"l'étage C n'a refusé que {reasons.get('too_different_from_source', 0)} "
        f"lignes ; 32 mesurées à l'écriture"
    )
    assert all(d.final_text == d.source_text for d in result.decisions.decisions), (
        "une proposition illisible a survécu jusqu'à la décision"
    )


def test_the_declared_encoding_does_not_change_a_single_byte() -> None:
    """Deux fois le même document, l'un déclaré ISO-8859-1 alors qu'il est en
    UTF-8. La bibliothèque lit les octets pour ce qu'ils SONT et le déclare
    sur ``source_encodings`` ; le fichier livré doit être identique au bit
    près, sinon la déclaration mensongère aurait changé le texte.
    """
    a = _rewrite_directly(_FIXTURES["bnf-alto-prod-bpt6k5406037v-f40.xml"], "identity")
    b = _rewrite_directly(_FIXTURES["bnf-alto-prod-latin1-control.xml"], "identity")
    assert a == b
