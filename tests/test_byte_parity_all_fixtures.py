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
    ): "bc4b78ddb606baf74cd031e1502a32e0effe555e1ce80326ced38691014df488",
    (
        "sample.xml",
        "drift",
    ): "e283b7c29f7a6c5e4cbf1dda7222cbe3705cb1e5e938e1e9ff75d1ad59c43411",
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
    ): "14f01f377e059392a4f8abd2bf89b5a4ce19410a34478114318add0dabbe1b72",
    (
        "X0000002.xml",
        "drift",
    ): "3e3338c8a9643f90568d0246edfabfb312708879ef6d8e2e61a3be9a7da37ffa",
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
    ): "aa39bf9f41c56266ae6d96a6239caec241377869ddd3e3cfabdb19547f523904",
    (
        "bnf-alto-prod-bpt6k5406037v-f40.xml",
        "drift",
    ): "db66a2bfe416de94c8533f020395308598e73c3b0ba8c08ba9ac77ea303fa689",
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
    ): "aa39bf9f41c56266ae6d96a6239caec241377869ddd3e3cfabdb19547f523904",
    (
        "bnf-alto-prod-latin1-control.xml",
        "drift",
    ): "db66a2bfe416de94c8533f020395308598e73c3b0ba8c08ba9ac77ea303fa689",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "identity",
    ): "e8097c054562deb8e7c86c501f4a43bdf9ded32c8c008c3c80f1125118ab2e05",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "scripted",
    ): "18024cb1abbd063ea8db7f7bae87de15b783683eead02243377a8850cd0119cb",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "probe",
    ): "283d69986ebacf4f54c5451166c241cad66684cf356c66bd10a42cc56271c10f",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "drift",
    ): "7e8b6860d3def6d5cd5bb5882d0874b95e3a226cfbc8728ebbbbeedd52472d49",
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
    ): "b2e56be863fd1613ac927a36de3177db8c4c50d0f90cc7e278d96bdb142c404e",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_corrected.xml",
        "drift",
    ): "af278477054cd518901532c28d6bd8000ff7168a55b96dc71334f502f16e7428",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        "identity",
    ): "afcf40824bc272d78b4b41fee75d76874ee92ee4fa63316581983b049f869a9a",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        "scripted",
    ): "44a315b2ed7f1573b4c96661ca7629a739bdea80840e6336f39015e0037f1e9f",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        "probe",
    ): "440e64e65ca4f691990f54773b3e7f96ca2831d2275a486ac14ea297f337ca52",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        "drift",
    ): "b87af7672359786edb36afac881982a36d7fa0ab3f677cef30bbe3ae7e9b4ccb",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "identity",
    ): "30a654cf8d9a242bd514d02befc357d118c38ec026dee7939603ade13f26d335",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "scripted",
    ): "8dfcf1450bf8f2502c98207addf966b0643e61605b5ac6ae8c9711de7750ae14",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "probe",
    ): "2717e24643db47fb68e40d264ee141924b7310ea3d4f3fa957ccbc573d498fa4",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "drift",
    ): "c2ef84ec56fe25423f77866097cf7c1cce2dd7faad3b931fb8bcd6e69e5a02e5",
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
    ): "a43bfd57a9cc6ad3cfc26922b3e975c5a314fb94aa4bee17d50272dd710778da",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_corrected.xml",
        "drift",
    ): "1962c7ff5d8ad66f7f6442abb8902716b7793277ea7254f083e41526b00ce3d3",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        "identity",
    ): "4b38b1e1ecdcc1e29ec68056115e8a1ab234414a2da3c8d05efe08bd1d7e7c7d",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        "scripted",
    ): "279b32b0abeaedd28bd7110a4d7484d37ece2e73d300ac13055172d91ab80fc8",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        "probe",
    ): "e273026f06525e927aff04de69d9800e0865467d8700da74260890027ac91764",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        "drift",
    ): "bba699cf36c5f92097c30a2ffaf4180fc0145cb9d7763705b542df62ecd04a5d",
    (
        "0250199004.xml",
        "identity",
    ): "6aa03461ec43921e35e3b9549c0f4c905137a7c050453d0fb2e649f3e6a87c68",
    (
        "0250199004.xml",
        "scripted",
    ): "b1fddb64dfdcedd87a1f808de2dd9a8b75d6320880c83d21ab3b3530ead06a01",
    (
        "0250199004.xml",
        "probe",
    ): "2a31190edddd2ce4e64adf635be2af1f749b86fe515e8ba4d1c5e2e3aa648e99",
    (
        "0250199004.xml",
        "drift",
    ): "cb6181b9ac38eddff94639be0ea94108f99a302dbf59cc9773b95779f96d7901",
    (
        "0253902003.xml",
        "identity",
    ): "5ce0e9f5d144e5b392f6bbf3cdf1cd692d85e37d9282f843bf9c0e27c11134b0",
    (
        "0253902003.xml",
        "scripted",
    ): "cad3ded0776a4415b9dca945ca9a866de066321a5ed86b49f6a45a998e61eb5a",
    (
        "0253902003.xml",
        "probe",
    ): "f28531d31d08feb66352696293b0d44200bb373ba50f6c325eb4406d4c43420a",
    (
        "0253902003.xml",
        "drift",
    ): "51e09b0401530943682592bf8ebe57c3a8b96f50b030006583fbafecd917e723",
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
    ): "786ed9629c10daf5386d99bef03ffcbda66e7bd0e7034bdcecf6e70f169ace43",
    (
        "bpt6k2206225_p0015.alto.xml",
        "drift",
    ): "850a59d007fe1f27930b9f58975737bf335b3bb2e60eea0ef45741e583d2da6c",
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
    ): "7898ad7b96a3370f866db9022642f7a84cf0e696205c33ac5db097d850b0fb03",
    (
        "bpt6k2324031_p0002.alto.xml",
        "drift",
    ): "2f6a96e4d0a328070b91cd5d4f267d24271ae4416aa7a4a7bc2044f439a71149",
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
    ): "a3174249e708fc0dc0b19fbf115a28be14a4b43d98bd6715172c3076e8cd367a",
    (
        "bpt6k6478860m_p0009.alto.xml",
        "drift",
    ): "79458c995e133af4687f30800bc24387abe1c733d9009dfb33ca73d9fe8e0510",
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
