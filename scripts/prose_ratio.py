#!/usr/bin/env python3
"""Report the prose/code ratio of ``src/`` — a thermometer, not a gate.

Wave `H` (`docs/PLAN.md`) closes on five propositions, and the fourth is
"the ratio does not rise from one wave to the next". That is a derivative,
not a threshold, and it needs a number somebody can actually read before
and after a slice.

**This script exits 0 whatever it measures.** It is deliberately not wired
into CI and must not become a check. `RS-4.2` recorded what happens when a
measurement is given the power to refuse: the length ceiling asked for a
split rather than a reason, and the split produced `PageWorkspace` — an
object whose whole purpose was to make a number go down. A ratio ceiling
would ask for the same thing, one docstring at a time.

What the categories are for: roughly two thirds of the prose is the API
reference (what a `CorrectionReport` field means, what a guard refuses),
which a publishable library must carry. `RS` measured that cutting it was
a loss, and this split is what lets a reader tell the two apart instead of
reacting to one total.

Usage::

    python scripts/prose_ratio.py                 # src/saknussemm
    python scripts/prose_ratio.py --per-module    # worst offenders first
    python scripts/prose_ratio.py path/to/pkg
"""

from __future__ import annotations

import argparse
import ast
import io
import tokenize
from collections import Counter
from pathlib import Path

#: The three categories that make up the API reference — the prose a
#: consumer reads, as opposed to the prose a maintainer reads.
_API_REFERENCE = ("docstrings de fonction", "docstrings de classe", "champs `#:`")


def _classify(path: Path) -> Counter[str]:
    """Count each line of ``path`` as code, prose (by category), or blank."""
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    kind: list[str] = ["code" if line.strip() else "blank" for line in lines]
    counts: Counter[str] = Counter()

    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            row = tok.start[0] - 1
            # `#:` documents a field on a public model — API reference, not
            # commentary, which is why it is counted apart from `#`.
            kind[row] = "champs `#:`" if tok.string.startswith("#:") else "commentaires"
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass

    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Module):
                label = "docstrings de module"
            elif isinstance(node, ast.ClassDef):
                label = "docstrings de classe"
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                label = "docstrings de fonction"
            else:
                continue
            if ast.get_docstring(node, clean=False) is None:
                continue
            first = node.body[0]
            for row in range(first.lineno - 1, first.end_lineno or first.lineno):
                kind[row] = label

    for label in kind:
        counts[label] += 1
    return counts


def _sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="src/saknussemm", type=Path)
    parser.add_argument(
        "--per-module",
        action="store_true",
        help="list modules by ratio, densest prose first",
    )
    args = parser.parse_args()

    files = _sources(args.root)
    if not files:
        print(f"aucun fichier Python sous {args.root}")
        return 0

    total: Counter[str] = Counter()
    per_module: list[tuple[float, int, int, Path]] = []
    for path in files:
        counts = _classify(path)
        total += counts
        code = counts["code"]
        prose = sum(v for k, v in counts.items() if k not in ("code", "blank"))
        if code:
            per_module.append((prose / code, prose, code, path))

    code = total["code"]
    prose = sum(v for k, v in total.items() if k not in ("code", "blank"))
    api = sum(total[k] for k in _API_REFERENCE)

    print(f"{args.root} — {len(files)} fichiers")
    print(f"  code   {code:6d}")
    print(f"  prose  {prose:6d}   ratio {prose / code:.3f}")
    print(f"  dont référence d'API {api} ({api / prose:.0%} de la prose)")
    print()
    for label in (
        "docstrings de fonction",
        "docstrings de classe",
        "champs `#:`",
        "docstrings de module",
        "commentaires",
    ):
        print(f"    {label:24} {total[label]:5d}")

    if args.per_module:
        print("\n  par module, prose la plus dense d'abord :")
        for ratio, prose_n, code_n, path in sorted(per_module, reverse=True):
            print(f"    {ratio:5.2f}  prose={prose_n:5d} code={code_n:5d}  {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
