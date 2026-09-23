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
    ): "063fb36595536afcfb36a2138e9923c4d5dd227a3e4034f06fa2042b7ab2c8ef",
    (
        "sample.xml",
        "probe",
    ): "1658f804a3b895b51707a8ce03f4b07315d4160d7d494b1269957e415b2d5845",
    (
        "sample.xml",
        "drift",
    ): "2387187c586548b424604f2b088e8df905a3ae8ec879d60264bc23094289c68f",
    (
        "X0000002.xml",
        "identity",
    ): "6b29f2269127f5ec9af15b6196e2e4c2ef48db4bf804aa616c2e0477f4db102a",
    (
        "X0000002.xml",
        "scripted",
    ): "d5b35e71ae41f6a8d8960cd180b88ce808a867d184cb92b984ee8e91a2764701",
    (
        "X0000002.xml",
        "probe",
    ): "25f46fec9b8b053aab46f8e0218cd61029a53324389f3ec1086fb828f71d3fe7",
    (
        "X0000002.xml",
        "drift",
    ): "ecfbae97aec3837bc7b1bd26ea75daee5d4947dfa47276ac0e06cb793d6ae7e6",
    (
        "bnf-alto-prod-bpt6k5406037v-f40.xml",
        "identity",
    ): "c260bcfcad4a909dfae9e1161f9766df8b72ef3eba61dfab95a59546f2486401",
    (
        "bnf-alto-prod-bpt6k5406037v-f40.xml",
        "scripted",
    ): "d52018aa8f985cb88007c5393fc8fe770078652ddae427d6e914f1aa8d60f326",
    (
        "bnf-alto-prod-bpt6k5406037v-f40.xml",
        "probe",
    ): "5da7368cb7f97d904f3c2835f46a76f2e4dc05551c734e70607a1338288bc701",
    (
        "bnf-alto-prod-bpt6k5406037v-f40.xml",
        "drift",
    ): "3255e61607cd1b8fb289223c138ca898ba9cf7279a072e2d2628063834f86232",
    (
        "bnf-alto-prod-latin1-control.xml",
        "identity",
    ): "c260bcfcad4a909dfae9e1161f9766df8b72ef3eba61dfab95a59546f2486401",
    (
        "bnf-alto-prod-latin1-control.xml",
        "scripted",
    ): "d52018aa8f985cb88007c5393fc8fe770078652ddae427d6e914f1aa8d60f326",
    (
        "bnf-alto-prod-latin1-control.xml",
        "probe",
    ): "5da7368cb7f97d904f3c2835f46a76f2e4dc05551c734e70607a1338288bc701",
    (
        "bnf-alto-prod-latin1-control.xml",
        "drift",
    ): "3255e61607cd1b8fb289223c138ca898ba9cf7279a072e2d2628063834f86232",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "identity",
    ): "e8097c054562deb8e7c86c501f4a43bdf9ded32c8c008c3c80f1125118ab2e05",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "scripted",
    ): "21acc1235178245ba98c2d2f5dd682946f950acee4898da35f4b566cf3463293",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "probe",
    ): "259c7b8196429c891e2a9a65cf0189a5135228b9cf3c0d1e3502200f7e6ff9d0",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml",
        "drift",
    ): "7588e991555122fd175bb26e7fdc20fedbdd4df8fb0991eed54b628ecdcfe516",
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
    ): "1ed3dae104cc057991433fcb76aaaff2d6fe4b2fbe2de1a5251ca95473749270",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_corrected.xml",
        "drift",
    ): "55d9e7ef6f76c58d91ffbfc0bf89ea9d9a5804f351b203b823c169c67d86c333",
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
    ): "5c5f85aba380d5a3c085735de0d7c60f1d5012bfa9c66d4334271fa5a070a0e9",
    (
        "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        "drift",
    ): "4b032f0006abd84d372520c19d739287980713c47faba68f292d18042fe1e41a",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "identity",
    ): "30a654cf8d9a242bd514d02befc357d118c38ec026dee7939603ade13f26d335",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "scripted",
    ): "9bcb4e309f66ce0b398e18c56b868249dccc10e7999014cd816d04241fa8c163",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "probe",
    ): "b45552bc6d56bc7cd8df37e89bc116f258a2281255bfbcbec75e8b926fdb075e",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_alto4.xml",
        "drift",
    ): "b65d3077ebbd86fdd29bcd0e1958b89e1cc234827899a2f585ab0c2fe6067428",
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
    ): "bccaf83568a6b7d4e0d001ef0281543da49ec9b5cc3e31d92219b255fdfd69e2",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_corrected.xml",
        "drift",
    ): "d34370d1fba09270a1f31966912f3c4bab41e974f726c6415ba2a6a5793dd6be",
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
    ): "7a004ccdd9db83ab19c6544274625ac6522599e73c1301a556a4e1a8fe0652d3",
    (
        "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        "drift",
    ): "976b96725d052d4dbdd089afbf9ba11ee312e78b0d13bd0e75137f291f8731bc",
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
    ): "ab794f4e4ef5b04e89228afc30ad836907b63822aa37906118e6d91cfd2bf4a9",
    (
        "0250199004.xml",
        "drift",
    ): "be0cb958dbe3b914647d1a03a251c93ebf8c55356bf952709d73c5eb7c9fba39",
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
    ): "53dffbe06202c5d151a80586b78ca732710444e1339c99a1087248a6dd27706f",
    (
        "0253902003.xml",
        "drift",
    ): "d13f0000638749eb3570c9bdaeb4f06c073e75bdda9257f5644897c8c2ad6695",
    (
        "bpt6k2206225_p0015.alto.xml",
        "identity",
    ): "9bbec99d79cd50fbb1acf8419ab99a84dcfced34212e07eb1cf6a50d9e482b52",
    (
        "bpt6k2206225_p0015.alto.xml",
        "scripted",
    ): "91c2708922a5575133736f7ad2cce78ee5f2679dea78982a76e339ea685faa26",
    (
        "bpt6k2206225_p0015.alto.xml",
        "probe",
    ): "fb587b249489a8f916a04d3f93eb6f952084864c533769b509cee459739dab08",
    (
        "bpt6k2206225_p0015.alto.xml",
        "drift",
    ): "749b8df1447ffac9af6c553ab635392fa7634e424ea621582870d5e7586999cc",
    (
        "bpt6k2324031_p0002.alto.xml",
        "identity",
    ): "36e02bfebccb9aa3024111161a0d08f4f884d0d471d3c1f89b0adb0eb7cea258",
    (
        "bpt6k2324031_p0002.alto.xml",
        "scripted",
    ): "61504f606340e6602033e3a50a21047186d7fb7a26c0c4871d6a4a696422d81b",
    (
        "bpt6k2324031_p0002.alto.xml",
        "probe",
    ): "f98ad16cb972a7a2ad69bde6dda255f075027f1c2f3cbaca89238c1d9b7bc758",
    (
        "bpt6k2324031_p0002.alto.xml",
        "drift",
    ): "b2965baf1c6d03c638dea8fc2149e0c51e804b61390bb0c69de7b742a791b2df",
    (
        "bpt6k6478860m_p0009.alto.xml",
        "identity",
    ): "deafbcec70ea6ab1e5b60301ee4f876d515452e1f60e26bde27f6ae659f4afe1",
    (
        "bpt6k6478860m_p0009.alto.xml",
        "scripted",
    ): "31222eec045ac2a1732b7d2b4fb9de757d72d8b462a9dd9925dbcf7598a8f875",
    (
        "bpt6k6478860m_p0009.alto.xml",
        "probe",
    ): "788140e83c1594fabe2b5d10122b03b222b9e49f761837f5288ea1431c3ef84b",
    (
        "bpt6k6478860m_p0009.alto.xml",
        "drift",
    ): "9c12c4d3c07ba7a7e9f6712c77aaccde3e77009ca10131766ac35dce1f6ca429",
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
