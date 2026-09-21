"""The orchestrator may only shrink, and no function is born oversized —
or born with fifteen parameters.

``core/pipeline.py`` was split into named components slice by slice, with
nothing but a line count in a plan document to say whether it was
progressing — so a slice that moved code *and* grew the file, or one that
lifted a stage out but left a 200-line function behind, would have read
exactly like a slice that worked. This module is the mechanical answer.

Five rules:

  1. **The orchestrator's budget is a ratchet.** ``_MODULE_BUDGET`` may be
     lowered when a slice lands and never raised. The 800-line target is
     reached; the ratchet is what keeps it reached, since the way an
     orchestrator regrows is one convenient method at a time.
  2. **A function over 100 lines must be named**, anywhere in the package.
     This is the rule that stops a split from laundering the problem:
     moving a 150-line method into a new module is not a split if it is
     still 150 lines when it lands.
  3. **A function taking more than 8 arguments must be named**, same scope.
  4. **A named function may only shrink** — in lines and in arguments.
  5. **Once it reaches a target its entry must go**, otherwise the list
     stops describing the remaining debt.

Two things changed here on 2026-08-06 (`RM-02`, `RM-10` in ``docs/PLAN.md``),
because the instrument was measuring the wrong thing over the wrong ground.

**Length alone rewards the defect it is supposed to prevent** (`RM-02`). A
gate on lines and nothing else is satisfied by pushing state out of a
function and into its signature, and that is what happened: the `S2` split
landed ``PageDriver._descend_granularity`` at 12 arguments and
``_attempt_chunk`` at 11, both comfortably under 100 lines. The histogram
tells the story on its own — fourteen functions in the 80-99 band and a
wall at 100. Nothing was wrong with the target; it was simply alone.
``_PARAMETER_TARGET`` is the second half, and the two are meant to be read
together: a function that satisfies one by violating the other has not
improved.

**The scan stopped at ``core/``** (`RM-10`). ``formats/`` was never looked
at, so the longest function in the package — ``_rebuild_line``, 203 lines,
on the path that writes the delivered file — was governed by nothing at
all, while the module that had already been cleaned up was governed
twice. The scan now covers ``src/saknussemm`` entire. The six ``formats/``
entries below are inscribed at their measured size; **inscribing is not a
plan to cut them.** ``formats/alto/rewriter.py`` is explicitly off-limits
until the byte-parity corpus is wider (`docs/PLAN.md`, § `RM`).

**Ce que `RS-4.2` a changé, le 2026-08-25.** Le plafond de longueur et celui
d'arité mesuraient bien, et demandaient mal. Une entrée coûtait un chiffre,
donc la porte n'a jamais demandé d'argument : elle demandait de découper — ce
qui a produit `PageWorkspace`, un objet à trois champs et zéro méthode dont
la docstring dit qu'il est né du plafond d'arité — ou d'inscrire, en silence.

Trois corrections, aucune qui relâche le cliquet :

1. **chaque entrée porte sa raison**, et une raison de moins de 40
   caractères est refusée. On peut garder une fonction longue ; il faut dire
   ce que la découper coûterait, et la phrase se relit. C'est la règle que
   `test_internal_seams_are_named` applique déjà aux symboles privés.
2. **les six entrées `formats/` quittent la table des dettes** pour
   `_MEASURED_NOT_A_DEBT`. La vague qui les avait inscrites écrivait déjà
   « inscribing is not a plan to cut them » ; les garder au même endroit que
   les dettes faisait lire la liste comme une file d'attente.
3. **six plafonds descendent à leur valeur mesurée** — ils avaient jusqu'à
   dix lignes de mou, ce que `test_budget_stays_ahead_of_the_file` interdit
   déjà au budget de module et que rien n'interdisait aux fonctions.

Ce qui NE change pas : `_MODULE_BUDGET` reste bloquant sur `core/pipeline.py`,
une entrée ne peut que rétrécir, et une entrée qui atteint la cible s'en va.

Keys are ``path/to/module.py::QualifiedName``. Both halves matter. The
path, because ``formats/alto/parser.py`` and ``formats/page/parser.py``
are two different files with functions of the same name. The qualified
name, because the previous key was the bare function name and silently
kept only the LAST definition of it in a file — ``core/confidence.py``
and ``core/quality.py`` each declare ``score_line`` / ``needs_correction``
twice (protocol, then implementation) and one of each pair was invisible
to this test.

A key names where a function lives TODAY. When a slice moves one, the key
moves with it — that is not a reset, and the pinned numbers may still only
go down. The lists are the debt, stated; they are not a queue anyone
should work through by default.
"""

from __future__ import annotations

import ast

import pytest

from tests._paths import SRC

SRC = SRC
PIPELINE = SRC / "core" / "pipeline.py"

#: The target the plan sets for the orchestrator, in lines.
_MODULE_TARGET = 800

#: Today's ceiling for the orchestrator. Lower it as slices land; never raise.
_MODULE_BUDGET = 580

#: The longest a function may be once the split is finished.
_FUNCTION_TARGET = 100

#: The most arguments a function may take. ``self``/``cls`` do not count —
#: the question is how much a CALLER has to assemble, and a bound receiver
#: is not part of that.
_PARAMETER_TARGET = 8

#: Chaque entrée porte son plafond ET la raison de sa longueur. Le nombre
#: seul était la faille de l'instrument : ajouter une fonction de 110 lignes
#: à la liste ne coûtait qu'un chiffre, donc le plafond ne demandait jamais
#: d'argument — il demandait de découper, ou d'inscrire. `RS-4.2` remplace
#: l'inégalité par la règle que le dépôt applique déjà à ses coutures
#: internes : on peut garder une fonction longue, il faut dire pourquoi.
#:
#: Sémantique inchangée par ailleurs : une entrée peut RÉTRÉCIR, jamais
#: grandir, et une entrée qui atteint la cible s'en va.
_OVERSIZED: dict[str, tuple[int, str]] = {
    "core/editing.py::_apply_line_ops": (
        104,
        "applique les ops d'une ligne et rend le verdict E1-E5. Chaque garde "
        "est une branche nommée et l'ordre dans lequel elles refusent EST le "
        "contrat ; les sortir une à une déplacerait cet ordre dans la liste "
        "des appels, où il ne se lit plus",
    ),
    "core/editing.py::apply_edit_script": (
        101,
        "la boucle par ligne au-dessus de la précédente. Sa longueur est "
        "celle de la table de refus qu'elle assemble, pas d'un enchaînement "
        "de décisions",
    ),
    "core/hyphenation.py::enrich_chunk_lines": (
        101,
        "construit le LineContext que le producteur voit : un champ par "
        "ligne de code, presque aucune branche. Découper reviendrait à "
        "répartir une structure de données entre deux fonctions",
    ),
    "core/hyphenation.py::reconcile_hyphen_pair": (
        110,
        "résolution de partenaire de césure. La règle permanente du plan "
        "interdit d'y toucher tant que l'unité n'est pas le stockage de "
        "référence — un découpage ici produirait la formulation "
        "supplémentaire que ce travail existe pour retirer",
    ),
    "core/pairing.py::link_hyphen_pairs": (
        119,
        "même raison que la précédente, côté établissement des liens",
    ),
    "core/validator.py::validate_llm_response": (
        142,
        "les contrôles structurels d'une réponse, dans l'ordre exact où ils "
        "doivent tomber pour que le message d'erreur nomme la bonne cause. "
        "Le découpage déplacerait cet ordre dans les appels",
    ),
}

#: Mesuré, et délibérément pas une dette.
#:
#: La vague qui a élargi le scan à ``formats/`` a inscrit ces six entrées à
#: leur taille mesurée en écrivant que « inscribing is not a plan to cut
#: them ». Les garder dans la même table que les dettes faisait lire la
#: liste comme une file d'attente ; elles ont la leur.
#:
#: La condition qui les protégeait — « hors-limites tant que le corpus
#: byte-parity n'est pas plus large » — est LEVÉE depuis `RS-1.1` : les
#: quinze documents du dépôt sont sous empreinte sur quatre scénarios. Les
#: couper reste une décision du plan et non un effet de bord de cette
#: vague, qui l'écrit au § « Ce que cette vague ne fait pas ».
_MEASURED_NOT_A_DEBT: dict[str, tuple[int, str]] = {
    "formats/alto/parser.py::_parse_alto_file": (
        146,
        "un parseur de format : sa longueur est celle du format, et chaque "
        "branche correspond à une variante ALTO réelle",
    ),
    "formats/alto/parser.py::_parse_textline_hyphen_info": (
        105,
        "la détection de césure explicite et heuristique sur une TextLine ; "
        "les cas sont ceux du corpus, pas ceux d'une abstraction",
    ),
    "formats/alto/rewriter.py::_rebuild_line": (
        # 193 -> 197 le 2026-09-22, et c'est une CAPACITE, pas une dérive :
        # la fonction reçoit le résolveur de géométrie et l'appelle. Mesuré
        # avant de le décider — sur trois corpus, la géométrie proportionnelle
        # place 63 à 84 % des frontières de mots dans le vrai blanc, un
        # résolveur qui lit les pixels en place 99,7 %. Le garde existe pour
        # arrêter la dérive, pas pour interdire ce que la feuille de route
        # demande ; relever une épingle reste une décision de mainteneur, et
        # celle-ci a été prise explicitement.
        197,
        "la plus longue du paquet, et le seul code qui décide de la "
        "géométrie des tokens livrés. Chaque branche porte un cas réel "
        "documenté ; c'est aussi le seul endroit où une erreur corrompt le "
        "fichier au lieu de le dégrader",
    ),
    "formats/alto/rewriter.py::rewrite_alto_file": (
        # 158 -> 165 le 2026-09-22 : le paramètre `word_geometry` et son
        # passage à `_rebuild_line`. `page_image` a été RETIRÉ de la surface
        # après coup — un résolveur qui lit les pixels porte sa propre source
        # d'image, donc le faire voyager ici gonflait la signature pour rien.
        165,
        "la boucle qui choisit un des quatre chemins de réécriture par "
        "ligne et tient la comptabilité des pertes",
    ),
    "formats/page/parser.py::_parse_page_file": (
        125,
        "même nature que le parseur ALTO, sur les trois millésimes PAGE",
    ),
    "formats/page/rewriter.py::rewrite_page_file": (
        117,
        "même nature que le rewriter ALTO, sur un format qui porte sa "
        "granularité mot dans des éléments Word",
    ),
}

#: Même forme, pour les signatures. Chaque entrée dit pourquoi la fonction
#: assemble depuis autant de sources.
_OVERPARAMETERISED: dict[str, tuple[int, str]] = {
    "core/attempt.py::_attempt_chunk": (
        11,
        "assemble depuis plusieurs origines — le chunk, le producteur, deux "
        "politiques, l'observateur, les index — au lieu de faire suivre un "
        "état. `RM-03` a lié les trois index qui pouvaient l'être ; ce qui "
        "reste vient d'endroits différents",
    ),
    "core/driver.py::PageDriver._descend_granularity": (
        10,
        "même nature, plus la bourse partagée que la descente doit "
        "transmettre explicitement pour que le sous-chunk dépense au même "
        "endroit",
    ),
    "core/driver.py::PageDriver._handle_chunk_failure": (
        9,
        "l'aiguillage entre descente et repli ; il lui faut ce que les deux "
        "branches consomment",
    ),
    "core/report.py::_build_correction_report": (
        11,
        "assemble le rapport depuis six sources indépendantes ; leur faire "
        "un objet commun reviendrait à créer le sac que `ADR-011` a retiré",
    ),
    "formats/alto/rewriter.py::_emit_string": (
        11,
        "émet un élément String avec sa géométrie recalculée ; les "
        "paramètres sont les attributs ALTO qu'il écrit",
    ),
    "producers/vision.py::VisionEditProducer.__init__": (
        11,
        "surface de configuration d'un producteur, comme celle du pipeline",
    ),
    "producers/llm_edit.py::LLMEditProducer.__init__": (
        9,
        "même nature : le client, les identifiants et le contrat de prompt",
    ),
}

#: Toutes les entrées de longueur, dettes et mesures confondues — ce que la
#: porte « aucune fonction non nommée » consulte.
#: Mesuré, et délibérément pas une dette — la moitié arité de
#: `_MEASURED_NOT_A_DEBT`, et pour la même raison.
#:
#: `RS-5.1` a mesuré l'entrée `CorrectionPipeline.__init__` et **retiré sa
#: cible** : les paramètres restants sont des coutures d'injection
#: publiques, et les retirer serait un changement de surface, pas une
#: réduction. La raison inscrite dans la table des dettes disait pourtant
#: encore « `RS-5` doit les sortir » — elle décrivait un travail que le
#: plan avait déjà déclaré ne pas être un travail, et une table qui garde
#: une entrée dont la raison est périmée cesse de dire ce qui reste.
#:
#: Ce que le plafond continue de faire ici, et ce n'est pas rien : ajouter
#: une couture reste un acte visible en revue, chiffré, avec sa raison.
#: Ce qu'il cesse de faire, c'est de se lire comme une file d'attente.
_ARITY_NOT_A_DEBT: dict[str, tuple[int, str]] = {
    "core/pipeline.py::CorrectionPipeline.__init__": (
        15,
        "surface de CONFIGURATION, pas du threading : chaque paramètre est "
        "une couture d'injection publique (§15), et les retirer serait un "
        "changement de surface publique — mesuré par `RS-5.1`, qui a retiré "
        "la cible « ≤ 9 » pour cette raison. Le quinzième est "
        "`review_policy`, dont le défaut n'est pas inerte",
    ),
    "core/pipeline.py::CorrectionPipeline.for_provider": (
        9,
        "les paramètres que ce constructeur POSSÈDE — l'appel vendeur et le "
        "contrat de prompt — le reste passant par **pipeline_kwargs",
    ),
}

_ALL_OVERPARAMETERISED: dict[str, tuple[int, str]] = {
    **_OVERPARAMETERISED,
    **_ARITY_NOT_A_DEBT,
}

_ALL_OVERSIZED: dict[str, tuple[int, str]] = {**_OVERSIZED, **_MEASURED_NOT_A_DEBT}


def _definitions() -> dict[str, tuple[int, int]]:
    """Every function in the package → ``(lines, arguments)``.

    Keyed ``path/to/module.py::QualifiedName``, where the qualification is
    the chain of enclosing CLASSES. Functions nested inside another function
    are not reported at all: their lines are already counted in the
    enclosing definition, and counting both would double-charge a closure.
    """
    found: dict[str, tuple[int, int]] = {}

    def visit(body: list[ast.stmt], rel: str, prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, rel, f"{prefix}{node.name}.")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = node.args
                names = [
                    a.arg
                    for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)
                    if a.arg not in ("self", "cls")
                ]
                lines = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                found[f"{rel}::{prefix}{node.name}"] = (lines, len(names))
                # Deliberately no descent: anything below is nested.

    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visit(tree.body, path.relative_to(SRC).as_posix(), "")
    return found


def _function_lengths() -> dict[str, int]:
    return {key: lines for key, (lines, _args) in _definitions().items()}


def _function_arities() -> dict[str, int]:
    return {key: args for key, (_lines, args) in _definitions().items()}


def test_the_scan_sees_the_whole_package() -> None:
    """A gate that stopped at ``core/`` left the longest function in the
    package ungoverned (`RM-10`). Pin the scope so it cannot narrow again."""
    keys = _definitions()
    assert any(k.startswith("core/") for k in keys)
    assert any(k.startswith("formats/alto/") for k in keys)
    assert any(k.startswith("formats/page/") for k in keys)
    assert any(k.startswith("integrations/") for k in keys)
    assert any(k.startswith("producers/") for k in keys)


def test_keys_are_unique_per_definition() -> None:
    """The previous key was the bare function name and silently dropped
    every same-named sibling in a file. Two pairs were invisible."""
    definitions = _definitions()
    for key in (
        "core/confidence.py::ConfidenceScorer.score_line",
        "core/confidence.py::HeuristicScorer.score_line",
        "core/quality.py::QEScorer.needs_correction",
        "core/quality.py::HeuristicQEScorer.needs_correction",
    ):
        assert key in definitions, f"{key} is not being measured"


def test_orchestrator_budget_is_a_ratchet() -> None:
    actual = len(PIPELINE.read_text(encoding="utf-8").splitlines())
    assert actual <= _MODULE_BUDGET, (
        f"core/pipeline.py grew to {actual} lines, over its {_MODULE_BUDGET}-line "
        "budget. The budget only goes down: lift a stage out into its own "
        "module rather than raising it."
    )


def test_budget_stays_ahead_of_the_file() -> None:
    """A budget left far above the file it guards guards nothing."""
    actual = len(PIPELINE.read_text(encoding="utf-8").splitlines())
    if actual > _MODULE_TARGET:
        assert _MODULE_BUDGET - actual <= 50, (
            f"core/pipeline.py is {actual} lines but the budget is "
            f"{_MODULE_BUDGET} — lower _MODULE_BUDGET to match what the last "
            "slice actually achieved, so the next slice inherits the gain."
        )


def test_no_unnamed_function_exceeds_the_target() -> None:
    over = {
        key: size
        for key, size in _function_lengths().items()
        if size > _FUNCTION_TARGET and key not in _ALL_OVERSIZED
    }
    assert not over, (
        f"{over} exceed the {_FUNCTION_TARGET}-line target and are not on the "
        "known-oversized list. Moving a long function into a new module is "
        "not a split — break it up where it lands."
    )


def test_no_unnamed_function_exceeds_the_parameter_target() -> None:
    over = {
        key: count
        for key, count in _function_arities().items()
        if count > _PARAMETER_TARGET and key not in _ALL_OVERPARAMETERISED
    }
    assert not over, (
        f"{over} take more than {_PARAMETER_TARGET} arguments and are not on "
        "the known-overparameterised list. Splitting a function by handing "
        "its state to the halves is not a split — the state moved, the "
        "coupling did not."
    )


@pytest.mark.parametrize("key", sorted(_ALL_OVERSIZED))
def test_known_oversized_functions_only_shrink(key: str) -> None:
    lengths = _function_lengths()
    ceiling, _reason = _ALL_OVERSIZED[key]
    assert key in lengths, (
        f"{key} no longer exists — drop it from its table, the entry is the "
        "debt, not the function."
    )
    assert lengths[key] <= ceiling, (
        f"{key} grew to {lengths[key]} lines, over its pinned {ceiling}. "
        "Known-oversized functions may only shrink."
    )


@pytest.mark.parametrize("key", sorted(_ALL_OVERPARAMETERISED))
def test_known_overparameterised_functions_only_shrink(key: str) -> None:
    arities = _function_arities()
    assert key in arities, (
        f"{key} no longer exists — drop it from its table, the entry "
        "is the debt, not the function."
    )
    ceiling, _reason = _ALL_OVERPARAMETERISED[key]
    assert arities[key] <= ceiling, (
        f"{key} grew to {arities[key]} arguments, over its pinned "
        f"{ceiling}. Known-overparameterised functions may only shrink."
    )


def test_every_inscribed_entry_carries_a_reason() -> None:
    """Le nombre seul était la faille de l'instrument.

    Inscrire une fonction de 110 lignes ne coûtait qu'un chiffre. Le plafond
    ne demandait donc jamais d'argument : il demandait de découper — ce qui a
    poussé à sortir de l'état dans les signatures jusqu'à ce qu'un second
    plafond arrive — ou d'inscrire, en silence.

    Une raison écrite change ce que la porte demande. On peut garder une
    fonction longue ; il faut dire pourquoi, et la phrase se relit.

    Le seuil de 40 caractères n'est pas une mesure de qualité : il refuse
    « historique », « à voir », « TODO » — la classe d'entrée qui satisfait
    la règle sans rien dire.
    """
    thin: dict[str, str] = {}
    for table in (
        _OVERSIZED,
        _MEASURED_NOT_A_DEBT,
        _OVERPARAMETERISED,
        _ARITY_NOT_A_DEBT,
    ):
        for key, (_ceiling, reason) in table.items():
            if len(reason.strip()) < 40:
                thin[key] = reason
    assert not thin, (
        f"{thin} : une entrée sans raison lisible est un plafond qui ne "
        f"demande rien. Écrire ce que le découpage coûterait, ou découper."
    )


def test_the_two_length_tables_do_not_overlap() -> None:
    """Une dette et une mesure ne peuvent pas être la même entrée.

    Sans cette assertion, déplacer une fonction de `_OVERSIZED` vers
    `_MEASURED_NOT_A_DEBT` sans retirer l'ancienne ligne la sortirait
    silencieusement de la liste des dettes tout en la gardant plafonnée
    deux fois — et la table cesserait de dire ce qui reste à faire.
    """
    for debts, measured, names in (
        (_OVERSIZED, _MEASURED_NOT_A_DEBT, "longueur"),
        (_OVERPARAMETERISED, _ARITY_NOT_A_DEBT, "arité"),
    ):
        both = sorted(set(debts) & set(measured))
        assert not both, (
            f"{both} figurent dans les deux tables d'{names}. La première "
            f"est ce qu'on prévoit de réduire, la seconde ce qu'on a mesuré "
            f"et décidé de garder — une entrée est l'un ou l'autre."
        )


def test_finished_functions_are_not_still_listed() -> None:
    """Once a function reaches the target, its entry must go — otherwise the
    list stops describing the remaining debt."""
    lengths = _function_lengths()
    done = {
        key: lengths[key]
        for key in _ALL_OVERSIZED
        if key in lengths and lengths[key] <= _FUNCTION_TARGET
    }
    assert not done, (
        f"{done} are within the {_FUNCTION_TARGET}-line target — remove them "
        "from their table so the list still shows what is left."
    )


def test_finished_signatures_are_not_still_listed() -> None:
    """Same rule for arguments: an entry that reached the target stops being
    debt and starts being noise."""
    arities = _function_arities()
    done = {
        key: arities[key]
        for key in _OVERPARAMETERISED
        if key in arities and arities[key] <= _PARAMETER_TARGET
    }
    assert not done, (
        f"{done} are within the {_PARAMETER_TARGET}-argument target — remove "
        "them from _OVERPARAMETERISED so the list still shows what is left."
    )
