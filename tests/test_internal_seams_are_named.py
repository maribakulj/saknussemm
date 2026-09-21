"""Which internals the suite is allowed to reach, and why each one.

`RM-05b` recorded "277 private-symbol imports from tests/" as debt. Measured
here rather than repeated: **64 imports, 38 symbols, 32 files**, and most of
them are not debt at all. The count was never the problem. The problem is
that nothing said WHICH internals are load-bearing, so when `S1` renames one,
the breakage is ambiguous — was the test too intimate, or did an invariant
just lose its net?

This map answers that, per symbol, in four categories:

``surface``
    Not an internal. The public-API snapshot test needs the lazy map to
    check the lazy map, and ``__version__`` is a dunder.

``alias``
    A PUBLIC function wearing an underscore. ``formats/_xml.py`` exports
    ``detect_namespace``; both format packages re-export it as
    ``_detect_namespace`` by local convention and list it in their own
    ``__all__``. Twelve of the sixty-four imports are this one name. The
    underscore is a naming artifact, not a boundary.

``value``
    A function of its arguments (or a constant). The test calls it and
    reads what it returns, or what it wrote on an object the TEST owns —
    an ``lxml`` element it built, a list of lines it built. Reaching it
    directly is a unit test, not a trespass: routing the same assertion
    through the façade would need a whole document and would assert less.

``run-state``
    A pass that writes the RUN's state — the per-line traces, the decision
    order. These are load-bearing by construction, and the plan already
    says why: the public suite "checks the FINAL state of a run, not its
    dependence on pass order" (`RM-05a`). Rename one and a test must break;
    that is the point of it.

**The classification is verified, not declared.** A ``run-state`` entry has
to carry ``traces``, ``workspace`` or ``order`` in its real signature, read
from ``src/``, and a ``value`` entry has to carry none of them; an ``alias``
entry has to genuinely be an aliased import in the module it is imported
from. Mislabelling fails here. Two entries are classes rather than
functions (``_FinalizeOrder``, ``_RetryDecision``) and carry no signature to
check — they are named with a reason and nothing more, which is the honest
limit of this test.

What this file deliberately does NOT do is shrink the number. There is no
bucket of gratuitous imports to remove: the audit's premise was wrong, and
the useful artefact is a bounded, named list.
"""

from __future__ import annotations

import ast
import collections
from pathlib import Path

from tests._paths import SRC, TESTS

#: An argument name that only a pass over a live run receives.
_RUN_STATE_ARGS = {"traces", "workspace", "order"}

#: ``module path -> (category, why this one)``.
_SEAMS: dict[str, tuple[str, str]] = {
    # -- surface: the instruments of the tests that check the surface -------
    "saknussemm.__version__": ("surface", "a dunder; the provenance test reads it"),
    "saknussemm._LAZY": (
        "surface",
        "the PEP 562 lazy map — the public-API snapshot test checks that every "
        "lazy key is in __all__, which needs the map",
    ),
    # -- alias: public names wearing an underscore --------------------------
    "saknussemm.formats.alto._ns._detect_namespace": (
        "alias",
        "formats._xml.detect_namespace, re-exported under an underscore and "
        "listed in this module's own __all__",
    ),
    "saknussemm.formats.alto.parser._detect_namespace": (
        "alias",
        "the same name again, imported through the parser that re-exports it",
    ),
    "saknussemm.formats.page._ns._detect_namespace": (
        "alias",
        "the PAGE half of the same re-export",
    ),
    # -- run-state: passes that write what a run says about itself ----------
    "saknussemm.core.attempt._failure_family": (
        "classifier",
        "the one line where a failure's FAMILY survives into the message a "
        "report carries. Transport and malformed output both end as "
        "`all_attempts_exhausted`, and they mean opposite things: measured "
        "2026-08-18, sustained 429s took a page from 67% corrected to 37% and "
        "every one was reported as the model failing. Tested directly because "
        "the public seam can only show the two labels once each, and the "
        "mapping itself is what must not drift",
    ),
    "saknussemm.core.acceptance._FinalizeOrder": (
        "run-state",
        "the pass order itself — the object `RM-05a` exists to pin",
    ),
    "saknussemm.core.acceptance._apply_line_acceptance": (
        "run-state",
        "writes a line's decision and its fallback reason",
    ),
    "saknussemm.core.acceptance._apply_unit_reverts": (
        "run-state",
        "reverts a whole hyphen unit; the invariant is what it does to the "
        "MEMBERS the caller did not name",
    ),
    "saknussemm.core.acceptance._global_adjacency_pass": (
        "run-state",
        "one of the ordered finalise passes; running it out of order changes "
        "the delivered text",
    ),
    "saknussemm.core.acceptance._loss_policy_pass": (
        "run-state",
        "the pass whose position decides whether a correction it rejects was "
        "already written",
    ),
    "saknussemm.core.finalize._preserve_break_chars": (
        "run-state",
        "rewrites corrected_text after the decision; the pass order test needs "
        "to run it alone",
    ),
    "saknussemm.core.outcome._extend_to_units": (
        "run-state",
        "closes a chunk outcome over cross-page members via the workspace",
    ),
    "saknussemm.core.outcome._fall_back_to_source": (
        "run-state",
        "one of the seven sites that used to write a fallback reason; the "
        "precedence test pins each",
    ),
    "saknussemm.core.reconcile._refresh_pair_traces": (
        "run-state",
        "three branches, each writing a different reason onto a pair's traces",
    ),
    "saknussemm.core.rendering._render_outputs": (
        "run-state",
        "the render step reads traces and decisions; the channel test asserts "
        "which of the two it believes",
    ),
    # -- value: functions of their arguments --------------------------------
    "saknussemm.core.batching._split_for_image_cap": (
        "value",
        "returns the chunk/producer pairs; the test asserts no unit is split",
    ),
    "saknussemm.core.hyphenation._part1_text_migrated": (
        "value",
        "a predicate over two strings and a config",
    ),
    "saknussemm.core.hyphenation._part2_boundary_word_diverged": (
        "value",
        "a predicate over two strings and a config",
    ),
    "saknussemm.core.planner._unit_reach": (
        "value",
        "returns how far a unit reaches from a position — an integer, and the "
        "window walk's whole correctness",
    ),
    "saknussemm.core.indexing._cross_page_partners": (
        "value",
        "page + index in, the partners this page must borrow out. Read "
        "directly because it is one of the two remaining sites that resolve "
        "a partner off the pointer fields instead of asking the primitives, "
        "and comparing the two derivations is the only net it has — the byte "
        "goldens do not see it (every fixture is one page at a time)",
    ),
    "saknussemm.core.reconcile._build_hyphen_pairs": (
        "value",
        "lines in, the bidirectional pair map the VALIDATOR consults. Same "
        "reason as the entry above: it replays the role→slot map by hand, and "
        "neutralising it moves no byte because it feeds a guard rather than a "
        "transformation",
    ),
    "saknussemm.core.reconcile._units_visible_on_page": (
        "value",
        "the batcher's projection of the same derivation; `RM-08` proposed "
        "merging it with _page_local_units, and the test that closed the "
        "item needs both to show they disagree",
    ),
    "saknussemm.core.reconcile._page_local_units": (
        "value",
        "the router's projection: the units WHOLLY on this page. `RM-08` "
        "asked for a merge with its neighbour; measured, they disagree on a "
        "chain that leaves the page, and the item closed on that",
    ),
    "saknussemm.core.retry._RetryDecision": ("value", "the returned decision type"),
    "saknussemm.core.retry._classify_retry": (
        "value",
        "exception in, decision out — the retry policy's whole logic",
    ),
    "saknussemm.core.validator._validate_hyphen_integrity": (
        "value",
        "a predicate by exception over dicts the test builds",
    ),
    "saknussemm.formats.alto._ns._int_attr": (
        "value",
        "reads one attribute tolerantly; the robustness tests pin every "
        "unparseable shape",
    ),
    "saknussemm.formats.alto._text._DEDUP_MARKS": (
        "value",
        "the mark repertoire the reconstruction de-duplicates, as data",
    ),
    "saknussemm.formats.alto.parser._build_ocr_text": (
        "value",
        "element in, text out — the reconstruction parity test compares it "
        "against the rewriter's",
    ),
    "saknussemm.formats.alto._ns._tag": (
        "value",
        "namespace-qualifies an element name. Counting String children of a "
        "line needs it, and the loss-accounting file counts them to tell an "
        "attribute that dropped off a surviving element from an element that "
        "was merged away — two questions one attribute count conflates",
    ),
    "saknussemm.formats.alto.rewriter._apply_subs": (
        "value",
        "writes onto an lxml element the TEST built; the fixed-point test "
        "needs both halves of the pair",
    ),
    "saknussemm.formats.alto.rewriter._compute_geometry": (
        "value",
        "tokens in, widths out — asserting the exact sum is only possible here",
    ),
    "saknussemm.formats.alto.rewriter._geometry_is_usable": (
        "value",
        "boxes in, a verdict out. It is the guard that lets a THIRD PARTY "
        "hand geometry to the slow path at all, so each refusal needs a test "
        "that fails when its branch is removed — and a run only exposes "
        "whether the fallback was taken, never which property refused",
    ),
    "saknussemm.formats.alto.rewriter._is_space_token": ("value", "a predicate"),
    "saknussemm.formats.alto.rewriter._rebuild_line": (
        "value",
        "rebuilds an element the test built; `RM-10` measures this function "
        "and forbids cutting it, so the tests are its only description",
    ),
    "saknussemm.formats.alto.rewriter._resolve_geometry": (
        "value",
        "a resolver and a line in, token boxes out. Its whole promise is that "
        "no resolver, one that raises and one that answers something unusable "
        "all produce the SAME bytes as before the seam existed — three "
        "indistinguishable paths, which is exactly what no run output can "
        "tell apart",
    ),
    "saknussemm.formats.alto.rewriter._subs_need_update": (
        "value",
        "the route predicate; its agreement with _apply_subs is a fixed point "
        "no run output exposes",
    ),
    "saknussemm.formats.alto.rewriter._tokenize": ("value", "text in, tokens out"),
    "saknussemm.formats.alto.rewriter._word_boundary_moved": (
        "value",
        "two word lists in, a verdict out. The run only exposes which path was "
        "taken, so the boundary cases — and the counter-example proving the "
        "obvious guard would have passed — are only statable here",
    ),
    "saknussemm.formats.page._ns._namespace_year": (
        "value",
        "namespace in, schema year out",
    ),
    "saknussemm.formats.page.parser._assign_hyphen_roles": (
        "value",
        "assigns roles onto lines the TEST built — no run, no traces",
    ),
    "saknussemm.formats.page.parser._regions_in_reading_order": (
        "value",
        "returns the ordered regions; the conservative fallback to document "
        "order is invisible from outside",
    ),
    "saknussemm.formats.validation._schema_for": (
        "value",
        "namespace in, compiled schema out",
    ),
}


def _test_modules() -> list[Path]:
    return sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts)


def _private_imports() -> dict[str, set[str]]:
    """``module.symbol`` -> the test files importing it."""
    found: dict[str, set[str]] = collections.defaultdict(set)
    for path in _test_modules():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a broken test file fails elsewhere
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module or not node.module.startswith("saknussemm"):
                continue
            for alias in node.names:
                if alias.name.startswith("_"):
                    key = f"{node.module}.{alias.name}"
                    found[key].add(str(path.relative_to(TESTS)))
    return found


def _module_file(dotted: str) -> Path:
    relative = dotted[len("saknussemm") :].strip(".").replace(".", "/")
    candidate = SRC / f"{relative}.py" if relative else SRC / "__init__.py"
    return candidate if candidate.exists() else SRC / relative / "__init__.py"


def _definition(dotted_symbol: str) -> ast.stmt | None:
    module, _, name = dotted_symbol.rpartition(".")
    path = _module_file(module)
    if not path.exists():
        return None
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    return node
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return node
    return None


def test_every_private_import_is_named() -> None:
    unlisted = sorted(set(_private_imports()) - set(_SEAMS))
    assert not unlisted, (
        f"test module(s) reach internals nobody classified: {unlisted}. Add "
        "each one with its category and the reason it is not reachable from "
        "the public surface — a private import is fine, an unexplained one is "
        "how a rename becomes ambiguous."
    )


def test_the_map_names_nothing_unused() -> None:
    """An entry nobody imports is a permission granted to nobody."""
    imported = set(_private_imports())
    stale = sorted(set(_SEAMS) - imported)
    assert not stale, (
        f"these are named but no longer imported by any test: {stale}. Drop "
        "them — a list that only grows stops describing anything."
    )


def test_every_named_symbol_still_exists() -> None:
    missing = sorted(name for name in _SEAMS if _definition(name) is None)
    assert not missing, (
        f"named symbol(s) with no definition in src/: {missing}. The suite "
        "imports them, so this means the scan lost the module, not that the "
        "import is dead."
    )


def test_the_classification_is_verified_not_declared() -> None:
    """The category has to match the real signature, read from ``src/``.

    A ``run-state`` pass receives the run's audit state; a ``value`` function
    does not. Classifying a pass as a value function to make a list look
    tidier fails here.
    """
    wrong: dict[str, str] = {}
    for name, (category, _reason) in sorted(_SEAMS.items()):
        node = _definition(name)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue  # classes, constants and aliases carry no signature
        args = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
        touches_run_state = bool(args & _RUN_STATE_ARGS)
        if category == "run-state" and not touches_run_state:
            wrong[name] = (
                f"classified run-state but takes none of {sorted(_RUN_STATE_ARGS)}"
            )
        if category == "value" and touches_run_state:
            wrong[name] = (
                f"classified value but takes {sorted(args & _RUN_STATE_ARGS)} — "
                "it writes what the run says about itself"
            )
    assert not wrong, f"the map disagrees with the code: {wrong}"


def _public_origin(dotted_symbol: str, depth: int = 0) -> str | None:
    """Follow re-export hops until a PUBLIC name, or give up.

    One hop is not enough, and the first run of this test proved it:
    ``formats/alto/_ns.py`` renames the public ``detect_namespace`` to
    ``_detect_namespace``, and ``formats/alto/parser.py`` then imports that
    private name unchanged. The chain is two long, and asking only about
    the last link called the second one internal.
    """
    if depth > 4:
        return None
    node = _definition(dotted_symbol)
    if not isinstance(node, ast.ImportFrom) or not node.module:
        return None
    symbol = dotted_symbol.rpartition(".")[2]
    for alias in node.names:
        if (alias.asname or alias.name) != symbol:
            continue
        if not alias.name.startswith("_"):
            return f"{node.module}.{alias.name}"
        return _public_origin(f"{node.module}.{alias.name}", depth + 1)
    return None


def test_an_alias_is_really_an_alias() -> None:
    """``alias`` claims the underscore is cosmetic. That is checkable."""
    wrong = []
    for name, (category, _reason) in sorted(_SEAMS.items()):
        if category != "alias":
            continue
        origin = _public_origin(name)
        if origin is None:
            wrong.append(name)
    assert not wrong, (
        f"'alias' entries that resolve to no public name: {wrong}. If the "
        "symbol really is internal, classify it as value or run-state."
    )


def test_the_aliases_all_come_from_one_place() -> None:
    """And they do: three imports, twelve sites, one public function.

    Worth asserting rather than noting, because it is the single largest
    line item in the whole measurement — nearly a fifth of the private
    imports the audit counted are one namespace helper that was never
    private.
    """
    origins = {
        _public_origin(name)
        for name, (category, _reason) in _SEAMS.items()
        if category == "alias"
    }
    assert origins == {"saknussemm.formats._xml.detect_namespace"}, (
        f"the alias entries no longer share one origin: {sorted(origins)}. "
        "That is fine, but the docstring above says otherwise — update it."
    )


def test_the_scan_reads_the_whole_suite() -> None:
    """Green by vacuity would look exactly like green."""
    modules = _test_modules()
    imports = _private_imports()
    assert len(modules) >= 100, f"only {len(modules)} test modules scanned"
    assert len(imports) >= 30, (
        f"only {len(imports)} private imports found — the suite reached 38 "
        "distinct symbols when this was written, and a collapse means the "
        "scan broke, not that the tests stopped reaching inside"
    )
