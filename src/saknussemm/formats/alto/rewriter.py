from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from saknussemm.core._norm import clean_content, nfc
from saknussemm.core._parse import parse_int_tolerant
from saknussemm.core.alignment import align_tokens
from saknussemm.core.identity import ensure_unique_identities
from saknussemm.core.losses import (
    COUNTS_INVALIDATION,
    INVALIDATION_COUNTER,
)
from saknussemm.formats.alto.losses import (
    ALIGNMENT_SCOPED,
    INVALIDATED_ATTRIBUTES,
    is_unconditional_loss,
)
from saknussemm.core.pairing import HYPHEN_CHARS, forward_break_is_explicit
from saknussemm.errors import DuplicateIdError
from saknussemm.formats.alto._ns import (
    _detect_namespace,
    _int_attr,
    _tag,
    make_safe_parser,
)
from saknussemm.formats._xml import read_source_tree_classified
from saknussemm.formats.alto._text import reconstruct_textline
from saknussemm.core.protocols import (
    LineGeometryRequest,
    RewriteResult,
    TokenBox,
    WordGeometryResolver,
)
from saknussemm.core.schemas import HyphenRole, LineManifest, PageManifest

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class RewriterMetrics:
    """Counts of lines per rewriter path."""

    untouched: int = 0
    subs_only: int = 0
    fast_path: int = 0
    slow_path: int = 0

    @property
    def total_processed(self) -> int:
        return self.subs_only + self.fast_path + self.slow_path

    @property
    def total_lines(self) -> int:
        return self.untouched + self.subs_only + self.fast_path + self.slow_path


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------


#: Whitespace that ALTO renders as an ``<SP>`` — that is, whitespace where a
#: line may BREAK. A no-break space is deliberately excluded: U+00A0, U+202F
#: (French typography's space before ``%``, ``;``, ``!``, ``?``, ``:``) and
#: U+2007 exist precisely to say "do not break here", and ``<SP>`` carries no
#: content, so routing one through an SP element replaces it with an ordinary
#: space and destroys the only thing it was there to express. Splitting on
#: breaking whitespace only keeps it inside its ``String``'s CONTENT, where it
#: survives the round-trip verbatim.
#:
#: The set: U+00A0 NO-BREAK SPACE, U+202F NARROW NO-BREAK SPACE, U+2007 FIGURE
#: SPACE. Spelled as escapes on purpose: they are indistinguishable from an
#: ordinary space in a source listing, and a reviewer has to be able to see
#: which ones are in here.
_NO_BREAK_SPACES = "\u00a0\u202f\u2007"
_BREAKING_WS = re.compile(rf"[^\S{_NO_BREAK_SPACES}]+")
#: Same class, capturing — ``re.split`` keeps the separators only when the
#: pattern has a group, and the rewriter needs them to emit its ``<SP>``s.
_BREAKING_WS_SPLIT = re.compile(rf"([^\S{_NO_BREAK_SPACES}]+)")


def _tokenize(text: str) -> list[str]:
    """Split text into alternating word/space tokens, dropping empty strings.

    "Space token" means BREAKING whitespace — see :data:`_BREAKING_WS`. A
    word token may therefore contain a no-break space, which is what makes
    ``M.\u00a0Dupont`` one String rather than two joined by a lossy ``<SP>``.
    """
    return [t for t in _BREAKING_WS_SPLIT.split(text) if t]


def _is_space_token(token: str) -> bool:
    """True when ``token`` is the whitespace BETWEEN two words — an ``<SP>``.

    Not ``token.strip() == ""``: :meth:`str.strip` treats a no-break space as
    whitespace, so a lone U+00A0 token would classify as a separator and be
    written back as an ordinary space — the very substitution this module
    stopped making.
    """
    return _BREAKING_WS.fullmatch(token) is not None


# ---------------------------------------------------------------------------
# Geometry (slow-path only)
# ---------------------------------------------------------------------------


def _compute_geometry(
    hpos: int,
    width: int,
    tokens: list[str],
) -> list[tuple[str, int, int]]:
    """
    Return list of (token, token_hpos, token_width) for every token.

    Widths are proportional to a per-token *weight*: a word weighs its
    character count, a run of spaces weighs 0.6x its character count
    (spaces render narrower than glyphs).

    The space weight enters the TOTAL as well as each token's share. With
    ``unit`` computed against the full character count while each space is
    drawn at 0.6, the accumulated shortfall of every space lands on the
    LAST token and inflates it. Consistent on both sides, the rounding
    error is spread across all tokens by cumulative rounding, and the final
    token only ever absorbs the residual.

    **Weights are integers, in tenths of a character**, and that is not a
    micro-optimisation. Summed as floats, ``0.6`` per space makes the total
    depend on the interpreter: CPython 3.12 gave ``sum()`` Neumaier
    compensated summation, so the same seventeen tokens weigh
    ``48.80000000000001`` on 3.11 and ``48.8`` on 3.12 — and one ``<SP>``
    of one real line comes out a pixel wider on one of them. Token geometry
    that depends on the Python version is not reproducible, and this
    function writes the geometry of the delivered file.

    Each boundary is then rounded from ONE exact division
    (``width * cumulative_weight / total_weight``) rather than from an
    accumulating float, so nothing depends on the order or the algorithm of
    a summation.
    """
    if not tokens:
        return []

    def _weight(t: str) -> int:
        """The token's weight in TENTHS of a character — 6 per space
        character, 10 per glyph. Integers so the total is exact."""
        return len(t) * 6 if _is_space_token(t) else len(t) * 10

    weights = [_weight(t) for t in tokens]
    total_weight = sum(weights)
    if total_weight == 0:
        per = width // len(tokens)
        return [(t, hpos + i * per, per) for i, t in enumerate(tokens)]

    # Cumulative rounding: round each boundary of the running weight and
    # take successive differences. Every token lands on the floor or ceil
    # of its ideal share and the widths sum EXACTLY to ``width``.
    widths: list[int] = []
    cumulative = 0
    prev_rounded = 0
    for w in weights:
        cumulative += w
        rounded = round(width * cumulative / total_weight)
        widths.append(rounded - prev_rounded)
        prev_rounded = rounded

    # Defensive min-1 floor for degenerate lines. Raise every sub-1 width
    # to 1, then repay the deficit from the widest donors (each clamped to
    # 1) until the exact-sum invariant is restored. When ``width`` is
    # smaller than the token count the invariant is mathematically
    # unsatisfiable with all-≥1 widths; the min-1 floor wins and the sum
    # settles at ``len(tokens)`` — the only honest outcome, and pinned by
    # test_compute_geometry. Real ALTO never reaches this branch.
    if min(widths) < 1:
        deficit = 0
        for i, w in enumerate(widths):
            if w < 1:
                deficit += 1 - w
                widths[i] = 1
        while deficit > 0:
            donor = max(range(len(widths)), key=lambda i: widths[i])
            if widths[donor] <= 1:
                break  # all at the floor — sum > width, unavoidable
            take = min(deficit, widths[donor] - 1)
            widths[donor] -= take
            deficit -= take

    result: list[tuple[str, int, int]] = []
    cursor = hpos
    for t, w in zip(tokens, widths):
        result.append((t, cursor, w))
        cursor += w
    return result


def _geometry_is_usable(
    boxes: tuple[TokenBox, ...],
    tokens: list[str],
    hpos: int,
    width: int,
) -> bool:
    """Whether a resolver's answer may be written into the tree.

    A resolver is a third party -- eventually one carrying a neural model --
    and the guarantee that saknussemm never emits an ALTO whose boxes
    contradict its text belongs to the engine, not to whoever plugs in. So
    the answer is checked rather than trusted, on the four properties the
    rewriter itself would otherwise have to assume:

    - one box per token, in order, each carrying its own token's text;
    - every width strictly positive (a zero-width String is not a box);
    - left-to-right monotonic, boxes not overlapping;
    - the whole run inside the line box it was given.

    A failure is not an error. It means the line falls back to
    ``_compute_geometry``, which is what would have drawn it anyway, and
    the run continues -- a resolver that cannot answer a hard line must
    degrade to the incumbent, never take the page down with it.
    """
    if len(boxes) != len(tokens):
        return False
    if any(b.text != t for b, t in zip(boxes, tokens)):
        return False
    if any(b.width <= 0 for b in boxes):
        return False
    if any(b.hpos + b.width > a.hpos for a, b in zip(boxes[1:], boxes)):
        return False
    return boxes[0].hpos >= hpos and boxes[-1].hpos + boxes[-1].width <= hpos + width


def _resolve_geometry(
    resolver: WordGeometryResolver | None,
    manifest: LineManifest,
    hpos: int,
    vpos: int,
    width: int,
    height: int,
    tokens: list[str],
    image: object | None,
) -> list[tuple[str, int, int]]:
    """The resolver's geometry when it is usable, the proportional one else.

    Every failure mode collapses to the same outcome on purpose: no
    resolver, a resolver that raises, and a resolver that answers something
    unusable all produce exactly the bytes saknussemm produces today. That
    is what makes this seam safe to add before anything fills it -- and what
    makes ``word_geometry=None`` byte-identical to the version without the
    parameter.
    """
    if resolver is not None:
        try:
            boxes = resolver.resolve(
                LineGeometryRequest(
                    hpos=hpos,
                    width=width,
                    tokens=tuple(tokens),
                    line_id=manifest.line_id,
                    vpos=vpos,
                    height=height,
                    image=image,
                )
            )
        except Exception:
            boxes = ()
        if _geometry_is_usable(boxes, tokens, hpos, width):
            return [(b.text, b.hpos, b.width) for b in boxes]

    return _compute_geometry(hpos, width, tokens)


# ---------------------------------------------------------------------------
# Element accessors (non-destructive)
# ---------------------------------------------------------------------------


def _attrib_dict(el: etree._Element) -> dict[str, str]:
    """Snapshot an element's attributes as a plain ``dict[str, str]``.

    lxml types ``_Attrib`` keys/values as ``str | bytes``; ALTO attributes
    are always text, so we coerce to ``str`` — this also satisfies
    ``mypy --strict`` where ``dict(el.attrib)`` does not.
    """
    return {str(k): str(v) for k, v in el.attrib.items()}


def _get_string_children(el: etree._Element, ns: str) -> list[etree._Element]:
    tag = _tag("String", ns)
    return [c for c in el if c.tag == tag]


def _get_sp_children(el: etree._Element, ns: str) -> list[etree._Element]:
    tag = _tag("SP", ns)
    return [c for c in el if c.tag == tag]


def _get_hyp_children(el: etree._Element, ns: str) -> list[etree._Element]:
    tag = _tag("HYP", ns)
    return [c for c in el if c.tag == tag]


# ---------------------------------------------------------------------------
# Text comparison
# ---------------------------------------------------------------------------


def _canonical_line_text(el: etree._Element, ns: str) -> str:
    """The parser's logical line text, derived here rather than assumed.

    ``parser._build_ocr_text`` is ``reconstruct_textline(...)`` plus a
    carriage-return strip plus a strip, and two places in this module need
    to compare against exactly that. Spelling it once is the point: the
    comparison below once used the raw, un-stripped reconstruction, so a
    line reconstructing with a trailing space — a trailing ``<SP/>`` — never
    matched its own ``ocr_text``, was needlessly rewritten, and made the
    UNTOUCHED metric under-count.
    """
    return reconstruct_textline(el, ns).replace("\r", "").strip()


def _line_text_unchanged(el: etree._Element, corrected: str, ns: str) -> bool:
    """Spec F4 — compare canonical forms on both sides."""
    return _canonical_line_text(el, ns) == nfc(corrected).replace("\r", "").strip()


# ---------------------------------------------------------------------------
# SUBS attribute logic (centralized — the ONLY place SUBS is written)
# ---------------------------------------------------------------------------


def _desired_subs(
    manifest: LineManifest,
) -> tuple[str | None, str | None]:
    """Return (wanted_subs_type, wanted_subs_content) for the primary role.

    For PART1: backward subs on last String.
    For PART2: backward subs on first String.
    For BOTH: backward subs on first String (forward handled separately).
    """
    if manifest.hyphen_role == HyphenRole.PART1:
        if manifest.hyphen_source_explicit and manifest.hyphen_subs_content:
            return "HypPart1", manifest.hyphen_subs_content
    elif manifest.hyphen_role == HyphenRole.PART2:
        if manifest.hyphen_source_explicit and manifest.hyphen_subs_content:
            return "HypPart2", manifest.hyphen_subs_content
    elif manifest.hyphen_role == HyphenRole.BOTH:
        # Backward (PART2 side) on first String
        if manifest.hyphen_source_explicit and manifest.hyphen_subs_content:
            return "HypPart2", manifest.hyphen_subs_content
    return None, None


def _desired_forward_subs(
    manifest: LineManifest,
) -> tuple[str | None, str | None]:
    """Return (wanted_subs_type, wanted_subs_content) for the forward/PART1 role.

    Only applies to BOTH lines.
    """
    if manifest.hyphen_role != HyphenRole.BOTH:
        return None, None
    if manifest.hyphen_forward_explicit and manifest.hyphen_forward_subs_content:
        return "HypPart1", manifest.hyphen_forward_subs_content
    return None, None


def _subs_target(
    el: etree._Element,
    manifest: LineManifest,
    ns: str,
) -> etree._Element | None:
    """Return the String element that should carry backward SUBS attributes."""
    strings = _get_string_children(el, ns)
    if not strings:
        return None
    if manifest.hyphen_role == HyphenRole.PART1:
        return strings[-1]
    if manifest.hyphen_role == HyphenRole.PART2:
        return strings[0]
    if manifest.hyphen_role == HyphenRole.BOTH:
        return strings[0]  # backward (PART2) subs on first String
    return None


def _forward_subs_target(
    el: etree._Element,
    manifest: LineManifest,
    ns: str,
) -> etree._Element | None:
    """Return the String that carries a BOTH line's forward (HypPart1)
    subs, or None when no distinct element exists for them.

    Shared by ``_apply_subs`` AND ``_subs_need_update`` so the
    writer and the change-detection predicate agree. When the line has a
    single String, ``strings[-1]`` IS the element carrying the BACKWARD
    (HypPart2) subs. Writing the forward HypPart1 onto it would clobber
    the continuation marker, flipping HypPart2→HypPart1 and destroying
    the "continues from the previous line" signal (and breaking
    byte-parity on an identity correction). The trailing HYP element
    already marks the forward hyphen, so forward SUBS only live on a
    DISTINCT last String — and the predicate must not demand them
    elsewhere (pre-fix it did, so a byte-correct single-String BOTH line
    was misrouted to SUBS-ONLY on every run, never UNTOUCHED).
    """
    if manifest.hyphen_role != HyphenRole.BOTH:
        return None
    strings = _get_string_children(el, ns)
    if not strings:
        return None
    last = strings[-1]
    if last is _subs_target(el, manifest, ns):
        return None
    return last


def _subs_need_update(
    el: etree._Element,
    manifest: LineManifest,
    ns: str,
) -> bool:
    """Return True if the XML SUBS state differs from the desired state."""
    if manifest.hyphen_role == HyphenRole.NONE:
        return False

    # Check backward subs
    want_type, want_content = _desired_subs(manifest)
    target = _subs_target(el, manifest, ns)
    if target is None:
        if want_type is not None:
            return True
    elif (
        target.get("SUBS_TYPE") != want_type
        or target.get("SUBS_CONTENT") != want_content
    ):
        return True

    # Check forward subs for BOTH lines — only on the distinct last
    # String _apply_subs would actually write (see
    # _forward_subs_target).
    last = _forward_subs_target(el, manifest, ns)
    if last is not None:
        fw_type, fw_content = _desired_forward_subs(manifest)
        if last.get("SUBS_TYPE") != fw_type or last.get("SUBS_CONTENT") != fw_content:
            return True

    return False


def _set_subs_on_element(
    target: etree._Element,
    want_type: str | None,
    want_content: str | None,
) -> None:
    """Set or remove SUBS_TYPE/SUBS_CONTENT on a single element."""
    if want_type and want_content:
        target.set("SUBS_TYPE", want_type)
        target.set("SUBS_CONTENT", want_content)
    else:
        for attr in ("SUBS_TYPE", "SUBS_CONTENT"):
            if attr in target.attrib:
                del target.attrib[attr]


def _apply_subs(
    el: etree._Element,
    manifest: LineManifest,
    ns: str,
) -> None:
    """Set or remove SUBS_TYPE/SUBS_CONTENT on the correct String element(s)."""
    # Backward subs
    target = _subs_target(el, manifest, ns)
    if target is not None:
        want_type, want_content = _desired_subs(manifest)
        _set_subs_on_element(target, want_type, want_content)

    # Forward subs for BOTH lines — only on a DISTINCT last String
    # (guard shared with _subs_need_update, see
    # _forward_subs_target for the single-String rationale).
    last = _forward_subs_target(el, manifest, ns)
    if last is not None:
        fw_type, fw_content = _desired_forward_subs(manifest)
        _set_subs_on_element(last, fw_type, fw_content)


# ---------------------------------------------------------------------------
# Fast path: in-place CONTENT update (word count unchanged)
# ---------------------------------------------------------------------------


# Attributes the slow-path rebuild either RECYCLES (ID/STYLEREFS/STYLE, §6.1
# whitelist) or drops for a justified reason: WC/CC describe the old glyph
# string (F2) and HPOS/VPOS/WIDTH/HEIGHT are recomputed/inherited. Anything
# ELSE on a source String (TAGREFS links to structural tags, ``language``,
# vendor attributes) is NOT invalidated by a spelling fix — the rebuild still
# cannot re-attach it to a re-segmented word without guessing, so it is
# dropped, but it must be REPORTED, not lost silently ("lossless" was a lie).
#: The two attributes the rewriter re-establishes from the line's HYPHEN
#: state, and only from that. ALTO's ``SUBS_TYPE`` has three values, and the
#: third — ``Abbreviation`` — has nothing to do with hyphenation, so nothing
#: re-establishes it.
_SUBS_ATTRIBUTES = ("SUBS_TYPE", "SUBS_CONTENT")


def _semantic_attr_losses(
    orig_string_attribs: list[dict[str, str]], manifest: LineManifest
) -> dict[str, int]:
    """Count the attributes a slow-path rebuild really loses.

    ``SUBS_*`` is counted here rather than trusted to the matrix, because the
    matrix classifies it REWRITTEN on the strength of ``_apply_subs`` running
    on every write path — and ``_apply_subs`` writes **at most one String's
    worth**, from the line's hyphen state. Measured 2026-08-17 with a
    ``<String CONTENT="Dr" SUBS_TYPE="Abbreviation" SUBS_CONTENT="Docteur"/>``:
    the identity and fast paths keep it, the slow path **destroys it**, and
    ``losses`` was ``None`` — an attribute gone and the report saying nothing,
    which is the `R*` promise inverted.

    So the count is *occurrences in the source minus the one the rebuild will
    write back*, rather than a per-line role test: a PART1 line can carry an
    abbreviation on a different String, and re-establishing the hyphen SUBS
    does nothing for it.

    "Really" is defined by :mod:`saknussemm.formats.alto.losses`, the versioned
    matrix, and not by a second list kept here — a second list is how this
    counter came to claim 229 dropped SUBS_CONTENT on a file that kept
    every one of them (R1). The matrix says which attributes are
    STRUCTURAL (they follow the tokens and cannot be lost), which are
    re-established, and which disappearances the report carries.

    Keyed ``<attr>_dropped`` (namespace stripped, lower-cased) to match the
    PAGE rewriter's loss vocabulary, e.g. ``TAGREFS`` → ``tagrefs_dropped``.
    """
    losses: dict[str, int] = {}
    wanted = {
        subs_type
        for subs_type, _content in (
            _desired_subs(manifest),
            _desired_forward_subs(manifest),
        )
        if subs_type
    }
    for attribs in orig_string_attribs:
        by_local = {
            key.rsplit("}", 1)[-1].upper(): value for key, value in attribs.items()
        }
        # A SUBS this line will not write back. `_apply_subs` re-establishes
        # SUBS from the hyphen state alone, so the honest test is whether the
        # SOURCE value is one this line actually wants — which the manifest
        # knows, and which needs no guess about the rebuilt shape.
        if by_local.get("SUBS_TYPE") not in (None, *wanted):
            for local in _SUBS_ATTRIBUTES:
                if local in by_local:
                    key = f"{local.lower()}_dropped"
                    losses[key] = losses.get(key, 0) + 1
        for key in attribs:
            local = key.rsplit("}", 1)[-1]
            if local.upper() in _SUBS_ATTRIBUTES:
                continue
            if not is_unconditional_loss(local):
                continue
            loss_key = f"{local.lower()}_dropped"
            losses[loss_key] = losses.get(loss_key, 0) + 1
    return losses


def _confidence_attr_count(el: etree._Element, ns: str) -> int:
    """How many INVALIDATED attributes (``WC``/``CC``) this line's Strings
    still carry.

    Measured, not inferred from the path taken: the fast path removes them
    only from Strings whose CONTENT actually changed, so a line can keep
    some and lose others, and "did the line take a write path" is not the
    same question as "did this line lose confidence".
    """
    count = 0
    for string_el in _get_string_children(el, ns):
        for attr in string_el.attrib:
            name = attr.decode() if isinstance(attr, bytes) else str(attr)
            if name.rsplit("}", 1)[-1].upper() in INVALIDATED_ATTRIBUTES:
                count += 1
    return count


def _confidence_loss(before: int, el: etree._Element, ns: str) -> dict[str, int]:
    """One line's invalidation loss — ``1`` if it lost any, not how many.

    The unit is the decision (R4, :data:`INVALIDATION_UNIT`): an archive
    acts on "this line's OCR confidence is gone", and how many Strings that
    line happened to hold is not a fact about the correction.
    """
    if not COUNTS_INVALIDATION or before == 0:
        return {}
    if _confidence_attr_count(el, ns) >= before:
        return {}
    return {INVALIDATION_COUNTER: 1}


def _add_alignment_scoped_losses(
    losses: dict[str, int],
    orig_string_attribs: list[dict[str, str]],
    matched_sources: set[int],
) -> None:
    """Count the :data:`ALIGNMENT_SCOPED` attributes of every source String
    the token alignment could not match.

    These are the attributes whose loss is CONDITIONAL — ``STYLE`` and
    ``STYLEREFS`` ride along when their String is matched to a target token
    and go when it is not — so the unconditional per-String pass leaves them
    alone (see :func:`saknussemm.formats.alto.losses.is_unconditional_loss`) and this
    one owns them.

    Called from two places on purpose. The rebuild has a second exit: a
    correction that empties the line returns before any alignment happens,
    because there are no target tokens to align against. Nothing matched
    means every style went — 56 lines of the repo's ALTO corpora carry these
    attributes — and that exit counted none of them (R2). Two exits, one
    accounting function; a second inline copy is how R1 happened.
    """
    for idx, attribs in enumerate(orig_string_attribs):
        if idx in matched_sources:
            continue
        for key in sorted(ALIGNMENT_SCOPED):
            if key in attribs:
                loss_key = f"{key.lower()}_dropped"
                losses[loss_key] = losses.get(loss_key, 0) + 1


def _drop_structural_break_hyphen(text: str) -> str:
    """Remove ONE trailing break hyphen from an explicit PART1 line's text.

    The hyphen is represented structurally by the line's ``<HYP>`` element,
    so it must not also live in the last ``String``'s CONTENT. Accepts the
    full ALTO/PAGE hyphen repertoire (``-`` ``¬`` ``⸗`` soft-hyphen), mirroring
    ``reconcile_hyphen_pair``'s trailing-hyphen gate. A line with no trailing
    hyphen is returned unchanged (defensive — the reconciler guarantees an
    explicit PART1 correction ends in one, but the rewriter never assumes it).
    """
    stripped = text.rstrip()
    if stripped.endswith(HYPHEN_CHARS):
        return stripped[:-1]
    return text


def _word_boundary_moved(originals: list[str], words: list[str]) -> bool:
    """Whether pairing word *i* with String *i* would attach the wrong box.

    An equal word count is what makes the fast path *possible*; it is not
    what makes it *correct*. A correction can keep the count and move the
    boundary — ``au`` + ``jourdhui`` becomes ``aujourd`` + ``hui`` — and
    then the positional ``zip`` writes seven characters into the box drawn
    for two. Measured on that line before this guard existed: 8.6 units
    per character against 273, and the report said ``EXACT``, because the
    reconstructed text does equal the decision. The fidelity check reads
    text; it is blind to which box a word landed in.

    Two signals, both cheap, because the fast path exists to be cheap:

    - **The letters are the same and the split is not.** Then the boundary
      definitively moved: there is no other way to reach the same
      concatenation with different words. Exact, no threshold, and no
      false positive by construction.
    - **A word changed length beyond what a correction plausibly does.**
      The tolerance is half the original word, floor 1, so ``0`` → ``o``,
      ``|||`` → ``Ill`` and ``Frauce`` → ``France`` all stay on the fast
      path while a two-character word becoming seven does not.

    A word-repertoire note on the first signal: it is deliberately the
    weaker-looking one, and it is the one that carries the case above.
    ``au``/``jourdhui`` shares ``a`` and ``u`` with ``aujourd``, so a
    "share at least one character" rule — the obvious first idea, and the
    one this guard was first written as — **passes** the very line it was
    meant to catch. Verified before this code was written.

    Returning ``True`` refuses no correction: the caller falls back to the
    slow path, which aligns tokens instead of assuming positions. The cost
    is recomputed geometry on that line, which is what the slow path is
    for.
    """
    if originals == words:
        return False
    if "".join(originals) == "".join(words):
        return True
    return any(
        abs(len(word) - len(original)) > max(1, len(original) // 2)
        for original, word in zip(originals, words)
    )


def _update_content_in_place(
    el: etree._Element,
    corrected: str,
    ns: str,
) -> bool:
    """
    When word count matches, update only CONTENT on existing String elements.

    Returns True on success. ALL other attributes (ID, HPOS, VPOS, WIDTH,
    HEIGHT, WC, CC, STYLEREFS, etc.) and SP/HYP elements stay untouched.

    An equal word count is necessary and **not sufficient**: see
    :func:`_word_boundary_moved`. The check runs before anything is
    mutated, so a refusal leaves the element exactly as it was found —
    this function is called for its side effects and the caller retries on
    the slow path.
    """
    orig_strings = _get_string_children(el, ns)
    words = [t for t in _tokenize(corrected) if not _is_space_token(t)]
    if len(words) != len(orig_strings):
        return False
    cleaned = [clean_content(word) for word in words]
    if _word_boundary_moved([s.get("CONTENT", "") for s in orig_strings], cleaned):
        return False
    for string_el, word in zip(orig_strings, words):
        new_content = clean_content(word)
        changed = string_el.get("CONTENT") != new_content
        string_el.set("CONTENT", new_content)
        # Spec F2 — a changed CONTENT invalidates the OCR confidences: WC
        # (word confidence) and CC (per-character confidences) describe the
        # OLD glyph string and CC's length no longer matches the new CONTENT.
        # Drop them on any String whose CONTENT actually changes; a String
        # left byte-identical keeps its confidences untouched.
        if changed:
            for attr in ("WC", "CC"):
                if attr in string_el.attrib:
                    del string_el.attrib[attr]
    return True


# ---------------------------------------------------------------------------
# Internal: clear existing String/SP/HYP children
# ---------------------------------------------------------------------------


def _clear_line(el: etree._Element, ns: str) -> None:
    """Remove String/SP/HYP children.  TextLine attributes are untouched."""
    tags = {_tag("String", ns), _tag("SP", ns), _tag("HYP", ns)}
    for c in [c for c in el if c.tag in tags]:
        el.remove(c)


# ---------------------------------------------------------------------------
# Slow path: rebuild when word count changed
# ---------------------------------------------------------------------------


def _emit_sp(
    el: etree._Element,
    ns: str,
    orig_sp_attribs: list[dict[str, str]],
    sp_n: int,
    tok_hpos: int,
    tok_width: int,
    vpos: int,
) -> None:
    """Append a fresh SP child with RECOMPUTED geometry.

    §6.1 — SP geometry must agree with the recomputed String geometry
    around it: recycling an original SP's HPOS/WIDTH verbatim would make
    the interleaved SP/String layout contradict itself. SPs are pure
    spacing — they carry no confidences and no identity worth recycling —
    so their geometry is always derived from the same
    ``_compute_geometry`` pass as the Strings around them. ``orig_sp_attribs`` is still received
    so any non-geometric attribute an exotic producer set (none in the
    ALTO corpus at hand) survives; the geometric trio is overwritten.
    """
    sp = etree.SubElement(el, _tag("SP", ns))
    if sp_n < len(orig_sp_attribs):
        for k, v in orig_sp_attribs[sp_n].items():
            if k not in ("HPOS", "VPOS", "WIDTH", "HEIGHT"):
                sp.set(k, v)
    sp.set("WIDTH", str(tok_width))
    sp.set("HPOS", str(tok_hpos))
    sp.set("VPOS", str(vpos))


def _emit_string(
    el: etree._Element,
    ns: str,
    recycled: dict[str, str] | None,
    str_n: int,
    line_id: str,
    token: str,
    tok_hpos: int,
    tok_width: int,
    vpos: int,
    height: int,
    used_ids: set[str],
) -> None:
    """Append a fresh String child for the slow-path rebuild.

    Spec F2 / §6.1 — the slow path recycles ONLY identity and styling from
    the original String: ``ID``, ``STYLEREFS``, and ``STYLE``.
    ``recycled`` is the attribute dict of the source String the token
    ALIGNMENT matched to this new token (identity follows the
    word it corresponds to, never whatever sat at the same position), or
    ``None`` for an inserted token — which gets a generated ID instead
    (deduplicated against every ID already used on the line).
    ``HPOS``/``WIDTH`` are recomputed, ``VPOS``/``HEIGHT`` are
    inherited from the line, and ``WC``/``CC``/``SUBS_*`` are **never**
    recycled: the confidences describe the old glyph string (and ``CC``'s
    length would no longer match the new ``CONTENT``), and SUBS attributes
    are written separately by ``_apply_subs``. Pre-F2 the reuse branch
    copied every original attribute except SUBS, carrying stale
    ``WC``/``CC`` onto the rebuilt String.

    ``STYLE`` (inline bold/italics/…) is part of the §6.1 whitelist
    (ratified 2026-07-07): the §6.1 doctrine
    targets data INVALIDATED by the text change, and styling —
    like ``STYLEREFS``, its reference-based twin — is not. Dropping it
    destroyed real formatting on the non-regression corpus (45 of the 47
    styled Strings in X0000002, mostly press headlines whose garbled OCR
    makes a slow-path word-count change the LIKELY correction, not an
    edge case).
    """
    s = etree.SubElement(el, _tag("String", ns))
    if recycled is not None:
        for k in ("ID", "STYLEREFS", "STYLE"):
            if k in recycled:
                s.set(k, recycled[k])
    if s.get("ID") is None:
        base = f"{line_id}_STR_{str_n:04d}"
        candidate = base
        suffix = 2
        while candidate in used_ids:
            candidate = f"{base}_{suffix}"
            suffix += 1
        s.set("ID", candidate)
    used_ids.add(s.get("ID", ""))
    s.set("CONTENT", clean_content(token))
    s.set("HPOS", str(tok_hpos))
    s.set("VPOS", str(vpos))
    s.set("WIDTH", str(tok_width))
    s.set("HEIGHT", str(height))


_HYP_GEOM_ATTRS = frozenset({"HPOS", "VPOS", "WIDTH", "HEIGHT"})


def _append_trailing_hyp(
    el: etree._Element,
    ns: str,
    orig_hyp_attribs: dict[str, str],
    hpos: int,
    vpos: int,
    width: int,
    height: int,
) -> None:
    """Append a HYP child to an explicit PART1-like TextLine.

    Non-geometry attributes (CONTENT, ID, STYLEREFS, …) carry over from an
    original HYP when present; a synthesised HYP defaults to ``-`` content.
    Geometry is ALWAYS the reserved end-of-line slot supplied by the
    caller — the original HYP's stale HPOS/WIDTH must NOT be copied
    verbatim, or the rebuilt children would sum past the line WIDTH and the
    HYP would overlap the last String.
    """
    hyp = etree.SubElement(el, _tag("HYP", ns))
    content_set = False
    for k, v in orig_hyp_attribs.items():
        if k in _HYP_GEOM_ATTRS:
            continue
        hyp.set(k, v)
        if k == "CONTENT":
            content_set = True
    if not content_set:
        hyp.set("CONTENT", "-")
    hyp.set("HPOS", str(hpos))
    hyp.set("VPOS", str(vpos))
    hyp.set("WIDTH", str(width))
    hyp.set("HEIGHT", str(height))


def _write_text_for(manifest: LineManifest, corrected: str) -> tuple[str, bool]:
    """What to WRITE for a line, and whether a break space goes with it.

    An EXPLICIT PART1 line carries its end-of-line hyphen structurally, in
    the ``<HYP>`` element (the rewrite paths re-emit it). If the LLM returned
    the fragment WITH a trailing hyphen (``"préve-"``, natural at a word
    break), storing it in the String CONTENT too would double the hyphen, so
    it is dropped here — for the write text only, and only after the caller's
    change detection has compared the full reconstructed line (String + HYP),
    so an identity correction still classifies UNTOUCHED. A HEURISTIC PART1
    (no HYP/SUBS markup) has no structural hyphen and keeps its trailing dash
    in CONTENT — untouched by this branch.

    The second return value exists because this is the ONLY place that sees
    the text on both sides of that drop, and therefore the only one that can
    tell a space BEFORE the mark from a space after it. See
    :func:`_reserve_break_space` for what the distinction costs when it is
    lost.
    """
    if manifest.hyphen_role in (
        HyphenRole.PART1,
        HyphenRole.BOTH,
    ) and forward_break_is_explicit(manifest):
        write_text = _drop_structural_break_hyphen(corrected)
        return write_text, write_text != write_text.rstrip()
    return corrected, False


def _reserve_break_slot(
    orig_hyp_attribs: dict[str, str], width: int, space_before_break: bool
) -> tuple[int, int]:
    """Split a PART1-like line's WIDTH into ``(hyp_slot, text)``.

    Reserve the ORIGINAL HYP's real width when one was present, so the
    rebuilt String/SP widths plus the HYP width sum EXACTLY to the line
    WIDTH. The old 4% estimate combined with copying the original HYP's
    verbatim WIDTH made the children sum to width + original_hyp_width and
    overlapped the last String. Fall back to the 4% estimate only when
    synthesising a HYP (explicit line with no HYP element).

    Parse via the shared tolerant policy: HYP attributes are never
    pre-parsed by ``_int_attr`` upstream, and a bare ``int(float(...))``
    would let ``WIDTH="1e999"`` escape as an uncaught OverflowError.
    Unusable → 0 → 4% estimate.

    Two units is the floor when a break space is wanted, since
    :func:`_reserve_break_space` splits this slot rather than adding to it.
    """
    orig_hyp_w = parse_int_tolerant(orig_hyp_attribs.get("WIDTH"), 0)
    hyp_width = orig_hyp_w if orig_hyp_w > 0 else max(1, round(width * 0.04))
    if space_before_break:
        hyp_width = max(hyp_width, 2)
    hyp_width = min(hyp_width, max(1, width - 1))  # keep room for text
    return hyp_width, max(1, width - hyp_width)


def _reserve_break_space(
    el: etree._Element,
    ns: str,
    orig_sp_attribs: list[dict[str, str]],
    sp_n: int,
    hpos: int,
    slot_width: int,
    vpos: int,
    *,
    wanted: bool,
) -> tuple[int, int]:
    """Emit the space that stands between the last word and the break mark.

    Returns what is left of the slot for the ``<HYP>``: ``(hpos, width)``,
    unchanged when no space is wanted.

    **Why the caller decides, and not this code.** The mark is gone by the
    time a line is rebuilt — :func:`_drop_structural_break_hyphen` removed
    it, because ``<HYP>`` carries it structurally — and with it went the
    only thing that told two opposite spaces apart:

    ================  ============================  =================
    decision          where the space is            after the drop
    ================  ============================  =================
    ``'deux mots- '`` AFTER the mark, so noise      ``'deux mots'``
    ``'et d -'``      BEFORE it, so the source's    ``'et d '``
    ================  ============================  =================

    Downstream both merely "end in whitespace". Reading the text here to
    decide would also re-emit the noise, moving the geometry for an edge
    space that means nothing — so the answer travels from the one place that
    sees the text on both sides of the drop.

    **Why the width comes out of the HYP's slot.** Taking it from anywhere
    else would shift every token on the line, which is the objection that
    kept the defect open for two days. Carved from the slot, nothing else
    moves and the children still tile the line exactly. Below two units
    there is nothing to split and the space is dropped — the line then
    fails the projection invariant, as it did before, rather than being
    delivered with overlapping children.
    """
    if not wanted or slot_width < 2:
        return hpos, slot_width
    sp_width = max(1, slot_width // 3)
    _emit_sp(el, ns, orig_sp_attribs, sp_n, hpos, sp_width, vpos)
    return hpos + sp_width, slot_width - sp_width


def _rebuild_line(
    el: etree._Element,
    corrected: str,
    manifest: LineManifest,
    ns: str,
    *,
    space_before_break: bool = False,
    word_geometry: WordGeometryResolver | None = None,
    image: object | None = None,
) -> tuple[dict[str, int], bool]:
    """Slow-path rebuild for any TextLine (normal, PART1, BOTH, PART2).


    Behaviour by ``manifest.hyphen_role``:
      - PART1 / BOTH: reserve 4% of total width for a trailing HYP
        element, rebuilt with the original HYP attributes when present
        or synthesised at end-of-text otherwise.
      - PART2: full text width; never carries a trailing HYP.
      - NONE: full text width; any stray HYPs on the source element are
        deep-copied and restored verbatim after the rebuild (defensive —
        production ALTO rarely has HYPs on non-hyphenated lines).

    Returns the ``<attr>_dropped`` loss counts for the semantic String
    attributes this rebuild could not carry over (empty when none) — the
    caller aggregates them into the run's loss report.
    """
    # Trim leading/trailing whitespace before tokenizing: the validator
    # accepts corrected text with edge whitespace, and an edge SP token
    # would land the trailing HYP ON TOP of the SP's HPOS range (overlap,
    # children no longer tiling the line) since last_word_hpos/width
    # track only String tokens.
    # Trimming matches the fast path, where split() drops edge
    # whitespace implicitly.
    corrected = corrected.strip()

    # Only an EXPLICITLY hyphenated PART1/BOTH line carries a HYP element.
    # A heuristically-detected PART1 (trailing dash in CONTENT, no HYP /
    # SUBS_TYPE markup) must NOT get a synthesised <HYP CONTENT="-">: that
    # would invent explicit markup the source never had (conservative-
    # heuristic violation) and append a phantom trailing hyphen to the
    # output text. Such a line is rebuilt like a plain line — its trailing
    # dash stays inside the String CONTENT.
    is_part1_like = (
        manifest.hyphen_role in (HyphenRole.PART1, HyphenRole.BOTH)
        and manifest.hyphen_source_explicit
    )
    is_normal = not is_part1_like and manifest.hyphen_role in (
        HyphenRole.NONE,
        HyphenRole.PART1,
        HyphenRole.BOTH,
    )

    orig_string_attribs = [_attrib_dict(s) for s in _get_string_children(el, ns)]
    orig_sp_attribs = [_attrib_dict(s) for s in _get_sp_children(el, ns)]
    # Semantic attributes (TAGREFS, language, vendor) the rebuild will drop:
    # reported, never silently lost. Computed from the source Strings before
    # they are cleared; the emitted Strings only carry the §6.1 whitelist.
    losses = _semantic_attr_losses(orig_string_attribs, manifest)

    # identity follows the token ALIGNMENT, not the
    # position: an inserted word must not shift every following word onto
    # the wrong source ID/STYLE (positional recycling attached text to the
    # wrong word identity). Alignment over the ORIGINAL CONTENTs vs the
    # corrected word tokens; a source String the alignment could not match
    # loses its STYLE/STYLEREFS — counted, never silently (`*_dropped`),
    # and a suspected word reorder is surfaced as `word_order_suspected`
    # (flagged, never acted on — lines never merge, words never move).
    orig_contents = [attribs.get("CONTENT", "") for attribs in orig_string_attribs]

    if is_part1_like:
        orig_hyps = _get_hyp_children(el, ns)
        orig_hyp_attribs: dict[str, str] = (
            _attrib_dict(orig_hyps[0]) if orig_hyps else {}
        )
        saved_hyp: list[etree._Element] = []
    elif is_normal:
        orig_hyp_attribs = {}
        saved_hyp = [copy.deepcopy(c) for c in el if c.tag == _tag("HYP", ns)]
    else:  # PART2
        orig_hyp_attribs = {}
        saved_hyp = []
        # R3 — a PART2 line is a word's continuation: it does not end
        # mid-word, so it has no forward break to render and _clear_line
        # removes any <HYP> it carried. The removal is right; being silent
        # about it was not. What goes is the ELEMENT — its geometry and its
        # standing as markup — not the mark: a non-terminal HYP's character
        # is already part of the reconstructed text and survives inside a
        # rebuilt String's CONTENT. Hence "elements_removed" rather than a
        # `*_dropped` key, which in this vocabulary claims a String
        # attribute and would be read as a phantom by the differential
        # invariant.
        #
        # Narrow, and narrower than the plan assumed: a PART2 line whose
        # HYP is line-TERMINAL is classified BOTH by the parser (the
        # trailing mark is a forward break), so this branch is reached only
        # via a non-terminal HYP — which ALTO does not define — or a
        # hand-built manifest. 0 of the 1711 ALTO lines in examples/ and
        # corpus/ have the shape.
        removed_hyps = sum(1 for child in el if child.tag == _tag("HYP", ns))
        if removed_hyps:
            losses["hyp_elements_removed"] = removed_hyps

    _clear_line(el, ns)

    hpos = _int_attr(el, "HPOS")
    vpos = _int_attr(el, "VPOS")
    width = _int_attr(el, "WIDTH")
    height = _int_attr(el, "HEIGHT")

    if is_part1_like:
        hyp_width, text_width = _reserve_break_slot(
            orig_hyp_attribs, width, space_before_break
        )
    else:
        hyp_width = 0
        text_width = width

    tokens = _tokenize(corrected)
    if not tokens:
        # R2 — nothing is written, so nothing aligned: every source String's
        # alignment-scoped attributes are lost. This exit used to skip the
        # accounting entirely.
        _add_alignment_scoped_losses(losses, orig_string_attribs, set())
        if is_part1_like:
            _append_trailing_hyp(
                el, ns, orig_hyp_attribs, hpos + text_width, vpos, hyp_width, height
            )
        else:
            for h in saved_hyp:
                el.append(h)
        return losses, False

    word_tokens = [t for t in tokens if not _is_space_token(t)]
    alignment = align_tokens(orig_contents, word_tokens)
    matched_sources = {
        p.source_index
        for p in alignment.pairs
        if p.source_index is not None and p.target_index is not None
    }
    _add_alignment_scoped_losses(losses, orig_string_attribs, matched_sources)
    # Pre-seed with every ID that WILL be recycled, so a generated ID for
    # an early inserted token can never collide with a later recycled one.
    used_ids: set[str] = {
        orig_string_attribs[i]["ID"]
        for i in matched_sources
        if "ID" in orig_string_attribs[i]
    }

    geo = _resolve_geometry(
        word_geometry, manifest, hpos, vpos, text_width, height, tokens, image
    )
    str_n = sp_n = 0
    last_word_hpos = hpos
    last_word_width = hyp_width

    for token, tok_hpos, tok_width in geo:
        if _is_space_token(token):
            _emit_sp(el, ns, orig_sp_attribs, sp_n, tok_hpos, tok_width, vpos)
            sp_n += 1
        else:
            source_index = alignment.source_for_target(str_n)
            _emit_string(
                el,
                ns,
                orig_string_attribs[source_index] if source_index is not None else None,
                str_n,
                manifest.line_id,
                token,
                tok_hpos,
                tok_width,
                vpos,
                height,
                used_ids,
            )
            last_word_hpos = tok_hpos
            last_word_width = tok_width
            str_n += 1

    if is_part1_like:
        break_hpos, break_width = _reserve_break_space(
            el,
            ns,
            orig_sp_attribs,
            sp_n,
            last_word_hpos + last_word_width,
            hyp_width,
            vpos,
            wanted=space_before_break,
        )
        _append_trailing_hyp(
            el, ns, orig_hyp_attribs, break_hpos, vpos, break_width, height
        )
    else:
        for h in saved_hyp:
            el.append(h)

    return losses, alignment.move_suspected


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def rewrite_alto_file(
    xml_path: Path,
    page_manifests: list[PageManifest],
    provider: str,
    model: str,
    *,
    lib_version: str | None = None,
    config_fingerprint: str | None = None,
    word_geometry: WordGeometryResolver | None = None,
) -> RewriteResult:
    """
    Rewrite an ALTO XML file with corrected text from page_manifests.

    Follows a 4-path strategy:
      Path 1 — UNTOUCHED:  text same + SUBS same → skip entirely
      Path 2 — SUBS-ONLY:  text same + SUBS changed → in-place SUBS update
      Path 3 — FAST PATH:  text changed + word count same → in-place CONTENT + SUBS
      Path 4 — SLOW PATH:  word count changed → rebuild line + SUBS

    Returns a :class:`RewriteResult` (bytes, metrics, per-line rewriter
    paths, final texts, losses).
    """
    # Hardened parser — see saknussemm.formats.alto._ns.make_safe_parser docstring
    # for the rationale. Using lxml's default here would expose every
    # rewrite to entity-amplification DoS via crafted ALTO uploads.
    tree = read_source_tree_classified(xml_path)
    root = tree.getroot()
    ns = _detect_namespace(root)
    metrics = RewriterMetrics()
    line_paths: dict[str, str] = {}
    losses: dict[str, int] = {}
    losses_by_line: dict[str, dict[str, int]] = {}
    word_order_suspected: set[str] = set()

    def record(line_id: str, line_losses: dict[str, int]) -> None:
        """Attribute a line's losses (ADR-012) and roll them into the run
        aggregate. One site, so the two can never disagree."""
        if not line_losses:
            return
        losses_by_line[line_id] = {
            **losses_by_line.get(line_id, {}),
            **line_losses,
        }
        for key, value in line_losses.items():
            losses[key] = losses.get(key, 0) + value

    # ADR-007 — a bare line_id keys every correction-to-element
    # association below. A duplicate (in the manifests OR on the XML
    # elements) would silently apply one line's correction to another
    # physical line, so both sides fail loudly instead. Parsers enforce
    # the same invariant up front; this guards direct calls with
    # hand-built manifests via the canonical shared check.
    ensure_unique_identities(page_manifests, xml_path.name)
    line_by_id: dict[str, LineManifest] = {
        lm.line_id: lm for page in page_manifests for lm in page.lines
    }

    seen_element_ids: set[str] = set()
    textline_tag = _tag("TextLine", ns)
    for tl_el in root.iter(textline_tag):
        line_id = tl_el.get("ID")
        if line_id not in line_by_id:
            continue
        if line_id in seen_element_ids:
            raise DuplicateIdError(
                f"duplicate TextLine ID {line_id!r} in {xml_path.name!r} — "
                "two physical lines would receive the same correction (ADR-007)."
            )
        seen_element_ids.add(line_id)
        lm = line_by_id[line_id]

        corrected = lm.corrected_text if lm.corrected_text is not None else lm.ocr_text
        text_changed = not _line_text_unchanged(tl_el, corrected, ns)
        subs_changed = _subs_need_update(tl_el, lm, ns)
        # Read BEFORE any path touches the tree, so what is reported is what
        # actually left the line rather than what the chosen path is assumed
        # to remove (R4).
        conf_before = _confidence_attr_count(tl_el, ns)

        # --- Path 1: UNTOUCHED ---
        if not text_changed and not subs_changed:
            metrics.untouched += 1
            line_paths[line_id] = "untouched"
            continue

        # --- Path 2: SUBS-ONLY ---
        if not text_changed:
            _apply_subs(tl_el, lm, ns)
            metrics.subs_only += 1
            line_paths[line_id] = "subs_only"
            record(line_id, _confidence_loss(conf_before, tl_el, ns))
            continue

        # An EXPLICIT PART1 line carries its end-of-line hyphen structurally,
        # in the <HYP> element (the rewrite paths re-emit it). If the LLM
        # returned the fragment WITH a trailing hyphen ("préve-", natural at a
        # word break), storing it in the String CONTENT too would double the
        # hyphen. Drop it here for the write text only — AFTER the change
        # detection above, which must compare the full reconstructed line
        # (String + HYP) so an identity correction still classifies UNTOUCHED.
        # A HEURISTIC PART1 (no HYP/SUBS markup) has no structural hyphen and
        # keeps its trailing dash in CONTENT — untouched by this branch.
        write_text, break_space = _write_text_for(lm, corrected)

        # --- Path 3: FAST PATH (word count same) ---
        if _update_content_in_place(tl_el, write_text, ns):
            _apply_subs(tl_el, lm, ns)
            metrics.fast_path += 1
            line_paths[line_id] = "fast_path"
            record(line_id, _confidence_loss(conf_before, tl_el, ns))
            continue

        # --- Path 4: SLOW PATH (word count changed) ---
        line_losses, move_suspected = _rebuild_line(
            tl_el,
            write_text,
            lm,
            ns,
            space_before_break=break_space,
            word_geometry=word_geometry,
        )
        _apply_subs(tl_el, lm, ns)
        metrics.slow_path += 1
        line_paths[line_id] = "slow_path"
        record(line_id, {**line_losses, **_confidence_loss(conf_before, tl_el, ns)})
        # R5 — a suspected reorder is a DIAGNOSTIC, not a loss: nothing left
        # the markup, the alignment simply could not vouch for the order it
        # was handed. It rode in the loss dict, so `sum(format_losses)`
        # counted a non-loss — R1's disease with a different attribute. It
        # travels on its own channel now.
        if move_suspected:
            word_order_suspected.add(line_id)

    _add_processing_entry(root, ns, provider, model, lib_version, config_fingerprint)
    # pretty_print=False: avoid gratuitously reformatting the entire XML
    # (whitespace between elements) when the user only changed CONTENT on a
    # handful of lines. Users comparing source vs. output should see only
    # real diffs.
    xml_bytes = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=False
    )
    # ADR-011 — the output texts are read off the very tree the bytes
    # were just serialized from: the projection invariant verifies them
    # without a second full parse of the output. A slow-path rebuild drops
    # semantic String attributes it cannot re-attach to re-segmented words
    # (TAGREFS, language, vendor); those are COUNTED in ``losses`` rather
    # than lost silently — the fast/untouched paths preserve them and report
    # nothing.
    return RewriteResult(
        xml_bytes=xml_bytes,
        metrics=metrics,
        rewriter_paths=line_paths,
        texts=_extract_texts_from_root(root, ns, set(line_by_id)),
        # L8 — the same lines read with the mark collapse OFF. Where the two
        # differ, the file spells a break mark its own way and the decision
        # spells it in normal form: real, invisible to a comparison of two
        # collapsed strings, and until now reported as `exact`.
        texts_verbatim=_extract_texts_from_root(
            root, ns, set(line_by_id), verbatim=True
        ),
        losses=losses,
        losses_by_line=losses_by_line,
        word_order_suspected=frozenset(word_order_suspected),
    )


def _extract_texts_from_root(
    root: etree._Element, ns: str, line_ids: set[str], *, verbatim: bool = False
) -> dict[str, str]:
    """Per-line text of an ALTO tree, via the shared
    ``reconstruct_textline`` helper — so the text seen here matches both
    the parser's ocr_text and the rewriter's UNTOUCHED-detection
    comparison.

    ``verbatim=True`` returns the same walk with the mark collapse OFF —
    what the file's characters say rather than the logical reading of them
    (L8). Used only to grade projection fidelity; never as anyone's text."""
    textline_tag = _tag("TextLine", ns)
    result: dict[str, str] = {}
    for tl_el in root.iter(textline_tag):
        line_id = tl_el.get("ID")
        if line_id in line_ids:
            if line_id in result:
                # ADR-007 — a repeated ID would silently collapse two
                # physical lines into one trace entry.
                raise DuplicateIdError(
                    f"duplicate TextLine ID {line_id!r} in rewritten ALTO — "
                    "output-text extraction would be ambiguous (ADR-007)."
                )
            result[line_id] = reconstruct_textline(tl_el, ns, verbatim=verbatim)
    return result


def extract_output_texts(xml_bytes: bytes, line_ids: set[str]) -> dict[str, str]:
    """Re-extract text from rewritten ALTO XML for the given line IDs.

    The pipeline no longer calls this (the rewrite returns its texts on
    the :class:`RewriteResult`); it remains for round-trip checks over
    arbitrary ALTO bytes.
    """
    # Hardened parser — see saknussemm.formats.alto._ns.make_safe_parser. The
    # bytes here are typically the OUTPUT of rewrite_alto_file but the
    # function is documented as accepting arbitrary ALTO bytes, so we
    # treat them as untrusted.
    root = etree.fromstring(xml_bytes, make_safe_parser())
    return _extract_texts_from_root(root, _detect_namespace(root), line_ids)


def _add_processing_entry(
    root: etree._Element,
    ns: str,
    provider: str,
    model: str,
    lib_version: str | None = None,
    config_fingerprint: str | None = None,
) -> None:
    """Record a ``processingStep`` documenting the correction pass (§11).

    Beyond the provider/model already written, the step now carries the
    **library version** and a **configuration fingerprint** (§8.2) so a
    corrected XML says by what and under which policy it was produced. Both
    are optional for backward compatibility; when omitted the historical
    description is emitted verbatim.

    Placement follows the ALTO container actually present:

    - ``<Processing>`` (the ALTO 4.0 generic slot) → append a
      ``<processingStep>`` (historical saknussemm behaviour, unchanged).
    - ``<OCRProcessing>`` (what real ABBYY / Tesseract / Gallica exports
      use) → append a ``<postProcessingStep>`` there. Without this branch
      §11's "every corrected file records the pass" silently failed for
      exactly the files real users bring — none of them carry ``<Processing>``.
    - neither, but a ``<Description>`` exists → create a ``<Processing>`` so
      the pass is still recorded rather than dropped.
    """
    desc = root.find(_tag("Description", ns))
    if desc is None:
        return
    description = _provenance_description(
        provider, model, lib_version, config_fingerprint
    )

    processing = desc.find(_tag("Processing", ns))
    if processing is not None:
        _append_processing_step(processing, ns, description)
        return

    ocr_processings = desc.findall(_tag("OCRProcessing", ns))
    if ocr_processings:
        _append_post_processing_step(ocr_processings[-1], ns, description, lib_version)
        return

    _append_processing_step(
        etree.SubElement(desc, _tag("Processing", ns)), ns, description
    )


def _provenance_description(
    provider: str,
    model: str,
    lib_version: str | None,
    config_fingerprint: str | None,
) -> str:
    """The human-readable provenance line shared by every ALTO container."""
    provenance = "saknussemm"
    if lib_version:
        provenance += f" {lib_version}"
    if config_fingerprint:
        provenance += f"; config {config_fingerprint}"
    return f"Post-OCR correction via {provider}/{model} ({provenance})"


def _append_processing_step(
    processing: etree._Element, ns: str, description: str
) -> None:
    """Record the pass as a ``<processingStep>`` (ALTO 4.0 ``<Processing>``)."""
    step = etree.SubElement(processing, _tag("processingStep", ns))
    step.set("type", "contentModification")
    step.set("description", description)


def _append_post_processing_step(
    ocr_processing: etree._Element,
    ns: str,
    description: str,
    lib_version: str | None,
) -> None:
    """Record the pass as a ``<postProcessingStep>`` inside ``<OCRProcessing>``.

    ``postProcessingStep`` is the ALTO-standard slot for work done after OCR
    (LoC ``OCRProcessingType``); it is appended after any existing
    pre/ocr/post steps, keeping the source OCR record intact. Child order
    follows ``ProcessingStepType``: description before software.
    """
    step = etree.SubElement(ocr_processing, _tag("postProcessingStep", ns))
    desc_el = etree.SubElement(step, _tag("processingStepDescription", ns))
    desc_el.text = description
    software = etree.SubElement(step, _tag("processingSoftware", ns))
    name_el = etree.SubElement(software, _tag("softwareName", ns))
    name_el.text = "saknussemm"
    if lib_version:
        version_el = etree.SubElement(software, _tag("softwareVersion", ns))
        version_el.text = lib_version


# --- public surface ---
__all__ = [
    "RewriterMetrics",
    "rewrite_alto_file",
    "extract_output_texts",
]
