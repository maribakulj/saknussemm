"""Tests for alto/rewriter.py"""

from __future__ import annotations

from pathlib import Path

from saknussemm.formats.alto.parser import parse_alto_file

# Private rewriter helpers — pulled from saknussemm directly since the
# backend re-export shim no longer surfaces privates.
from saknussemm.formats.alto.rewriter import (
    _compute_geometry,
    _tokenize,
    rewrite_alto_file,
)
from lxml import etree

from saknussemm.core.schemas import (
    BlockManifest,
    Coords,
    HyphenRole,
    LineManifest,
    PageManifest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NS_V3 = "http://www.loc.gov/standards/alto/ns-v3#"


def _ns(local: str) -> str:
    return f"{{{NS_V3}}}{local}"


def make_line(
    line_id: str,
    ocr_text: str,
    corrected_text: str | None = None,
    hyphen_role: HyphenRole = HyphenRole.NONE,
    hyphen_pair_line_id: str | None = None,
    hyphen_subs_content: str | None = None,
    hyphen_source_explicit: bool = False,
) -> LineManifest:
    return LineManifest(
        line_id=line_id,
        page_id="P1",
        block_id="TB1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=10, vpos=20, width=400, height=30),
        ocr_text=ocr_text,
        corrected_text=corrected_text,
        hyphen_role=hyphen_role,
        hyphen_pair_line_id=hyphen_pair_line_id,
        hyphen_subs_content=hyphen_subs_content,
        hyphen_source_explicit=hyphen_source_explicit,
    )


def make_alto_xml(lines_xml: str, with_description: bool = False) -> str:
    desc = (
        """  <Description>
    <Processing ID="P1">
    </Processing>
  </Description>"""
        if with_description
        else ""
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<alto xmlns="{NS_V3}">\n'
        f"  {desc}\n"
        f"  <Layout>\n"
        f'    <Page ID="P1" WIDTH="2480" HEIGHT="3508">\n'
        f'      <PrintSpace HPOS="0" VPOS="0" WIDTH="2480" HEIGHT="3508">\n'
        f'        <TextBlock ID="TB1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="60">\n'
        f"          {lines_xml}\n"
        f"        </TextBlock>\n"
        f"      </PrintSpace>\n"
        f"    </Page>\n"
        f"  </Layout>\n"
        f"</alto>"
    )


def write_and_rewrite(
    tmp_path: Path,
    lines_xml: str,
    manifests: list[LineManifest],
    with_description: bool = False,
) -> etree._Element:
    xml_path = tmp_path / "test.xml"
    xml_path.write_text(make_alto_xml(lines_xml, with_description), encoding="utf-8")

    page = PageManifest(
        page_id="P1",
        source_file="test.xml",
        page_index=0,
        page_width=2480,
        page_height=3508,
        blocks=[
            BlockManifest(
                block_id="TB1",
                page_id="P1",
                block_order=0,
                coords=Coords(hpos=10, vpos=20, width=400, height=60),
                line_ids=[m.line_id for m in manifests],
            )
        ],
        lines=manifests,
    )

    _res = rewrite_alto_file(xml_path, [page], "openai", "gpt-4o")
    result_bytes = _res.xml_bytes
    return etree.fromstring(result_bytes)


# ---------------------------------------------------------------------------
# Unit tests: _tokenize and _compute_geometry
# ---------------------------------------------------------------------------


def test_normal_line_tokenize():
    tokens = _tokenize("hello world")
    assert tokens == ["hello", " ", "world"]


def test_tokenize_multiple_spaces():
    tokens = _tokenize("a  b")
    assert tokens == ["a", "  ", "b"]


def test_geometry_sum_equals_width():
    tokens = _tokenize("hello world foo")
    geo = _compute_geometry(0, 300, tokens)
    assert sum(w for _, _, w in geo) == 300


def test_geometry_sum_single_word():
    geo = _compute_geometry(0, 100, ["hello"])
    assert sum(w for _, _, w in geo) == 100


def test_geometry_sum_many_tokens():
    tokens = _tokenize("one two three four five six seven")
    geo = _compute_geometry(50, 500, tokens)
    assert sum(w for _, _, w in geo) == 500


# ---------------------------------------------------------------------------
# Path 1 — UNTOUCHED: unchanged line is XML-identical
# ---------------------------------------------------------------------------


def test_unchanged_line_preserves_all_string_attributes(tmp_path):
    """When text is unchanged, ALL attributes on String elements are preserved."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="Hello" HPOS="10" VPOS="20" WIDTH="180" HEIGHT="30"
          WC="0.95" CC="09999" STYLEREFS="font1"/>
  <SP WIDTH="10" HPOS="190" VPOS="20"/>
  <String ID="S2" CONTENT="world" HPOS="200" VPOS="20" WIDTH="200" HEIGHT="30"
          WC="0.87" CC="99999"/>
</TextLine>"""
    lm = make_line("TL1", "Hello world")  # no corrected_text → uses ocr_text
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    strings = root.findall(f".//{_ns('String')}")
    assert len(strings) == 2

    # First String: every attribute preserved
    s1 = strings[0]
    assert s1.get("ID") == "S1"
    assert s1.get("CONTENT") == "Hello"
    assert s1.get("HPOS") == "10"
    assert s1.get("VPOS") == "20"
    assert s1.get("WIDTH") == "180"
    assert s1.get("HEIGHT") == "30"
    assert s1.get("WC") == "0.95"
    assert s1.get("CC") == "09999"
    assert s1.get("STYLEREFS") == "font1"

    # Second String
    s2 = strings[1]
    assert s2.get("ID") == "S2"
    assert s2.get("CONTENT") == "world"
    assert s2.get("WC") == "0.87"
    assert s2.get("CC") == "99999"


def test_unchanged_line_preserves_sp_attributes(tmp_path):
    """Unchanged line: SP elements are fully preserved."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="Bon" HPOS="10" VPOS="20" WIDTH="150" HEIGHT="30"/>
  <SP WIDTH="12" HPOS="160" VPOS="22"/>
  <String ID="S2" CONTENT="jour" HPOS="172" VPOS="20" WIDTH="200" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "Bon jour")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    sps = root.findall(f".//{_ns('SP')}")
    assert len(sps) == 1
    assert sps[0].get("WIDTH") == "12"
    assert sps[0].get("HPOS") == "160"
    assert sps[0].get("VPOS") == "22"


def test_unchanged_line_preserves_hyp_element(tmp_path):
    """Unchanged PART1 line: HYP element and its attributes are fully preserved."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="por-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          SUBS_TYPE="HypPart1" SUBS_CONTENT="porte"/>
  <HYP CONTENT="-" HPOS="110" VPOS="20" WIDTH="16" HEIGHT="30"/>
</TextLine>"""
    lm = make_line(
        "TL1",
        "por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="porte",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    tl = root.find(f".//{_ns('TextLine')}")
    hyps = tl.findall(_ns("HYP"))
    assert len(hyps) == 1
    assert hyps[0].get("CONTENT") == "-"
    assert hyps[0].get("HPOS") == "110"
    assert hyps[0].get("WIDTH") == "16"

    # SUBS preserved on the String too
    s = tl.find(_ns("String"))
    assert s.get("SUBS_TYPE") == "HypPart1"
    assert s.get("SUBS_CONTENT") == "porte"


def test_unchanged_line_string_count_unchanged(tmp_path):
    """Unchanged line: number of String/SP/HYP children is unchanged."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="un" HPOS="10" VPOS="20" WIDTH="50" HEIGHT="30"/>
  <SP WIDTH="8" HPOS="60" VPOS="20"/>
  <String ID="S2" CONTENT="deux" HPOS="68" VPOS="20" WIDTH="90" HEIGHT="30"/>
  <SP WIDTH="8" HPOS="158" VPOS="20"/>
  <String ID="S3" CONTENT="trois" HPOS="166" VPOS="20" WIDTH="100" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "un deux trois")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    assert len(root.findall(f".//{_ns('String')}")) == 3
    assert len(root.findall(f".//{_ns('SP')}")) == 2


# ---------------------------------------------------------------------------
# Path 2 — SUBS-ONLY: text unchanged, only SUBS attributes updated
# ---------------------------------------------------------------------------


def test_subs_only_update_sets_subs(tmp_path):
    """Text unchanged but subs_content is newly set → only SUBS attributes change."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="por-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"/>
  <HYP CONTENT="-" HPOS="110" VPOS="20" WIDTH="16" HEIGHT="30"/>
</TextLine>"""
    # Text is "por-" (matches XML), but subs_content now set
    lm = make_line(
        "TL1",
        "por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="porte",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    s = root.find(f".//{_ns('String')}")
    assert s.get("SUBS_TYPE") == "HypPart1"
    assert s.get("SUBS_CONTENT") == "porte"
    # All other attributes untouched
    assert s.get("ID") == "S1"
    assert s.get("HPOS") == "10"
    assert s.get("WIDTH") == "100"
    # HYP preserved
    hyps = root.findall(f".//{_ns('HYP')}")
    assert len(hyps) == 1
    assert hyps[0].get("HPOS") == "110"


def test_subs_only_update_removes_stale_subs(tmp_path):
    """Text unchanged but subs_content was neutralised → SUBS attributes removed."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="por-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          SUBS_TYPE="HypPart1" SUBS_CONTENT="porte"/>
  <HYP CONTENT="-" HPOS="110" VPOS="20" WIDTH="16" HEIGHT="30"/>
</TextLine>"""
    # Text unchanged, but subs_content is now None (pair incoherent)
    lm = make_line(
        "TL1",
        "por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content=None,
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    s = root.find(f".//{_ns('String')}")
    assert s.get("SUBS_TYPE") is None, "Stale SUBS_TYPE must be removed"
    assert s.get("SUBS_CONTENT") is None, "Stale SUBS_CONTENT must be removed"
    # ID and geometry untouched
    assert s.get("ID") == "S1"
    assert s.get("HPOS") == "10"


# ---------------------------------------------------------------------------
# Path 3 — FAST PATH: text changed, same word count, in-place update
# ---------------------------------------------------------------------------


def test_fast_path_only_content_changes(tmp_path):
    """Fast path: CONTENT changes; ID/geometry/STYLEREFS kept, WC/CC dropped.

    Spec F2 — a changed CONTENT invalidates the OCR confidences, so WC
    (word confidence) and CC (per-character confidences) are stripped from
    every String whose CONTENT actually changes.
    """
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="Helo" HPOS="10" VPOS="20" WIDTH="180" HEIGHT="30"
          WC="0.72" CC="0900" STYLEREFS="font1"/>
  <SP WIDTH="10" HPOS="190" VPOS="20"/>
  <String ID="S2" CONTENT="wrld" HPOS="200" VPOS="20" WIDTH="200" HEIGHT="30"
          WC="0.65" CC="9090"/>
</TextLine>"""
    lm = make_line("TL1", "Helo wrld", corrected_text="Hello world")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    strings = root.findall(f".//{_ns('String')}")
    assert len(strings) == 2

    # CONTENT updated
    assert strings[0].get("CONTENT") == "Hello"
    assert strings[1].get("CONTENT") == "world"

    # Identity + geometry + style preserved
    assert strings[0].get("ID") == "S1"
    assert strings[0].get("HPOS") == "10"
    assert strings[0].get("VPOS") == "20"
    assert strings[0].get("WIDTH") == "180"
    assert strings[0].get("HEIGHT") == "30"
    assert strings[0].get("STYLEREFS") == "font1"
    assert strings[1].get("ID") == "S2"
    assert strings[1].get("HPOS") == "200"

    # F2 — confidences dropped on both changed Strings
    assert strings[0].get("WC") is None
    assert strings[0].get("CC") is None
    assert strings[1].get("WC") is None
    assert strings[1].get("CC") is None

    # SP preserved
    sps = root.findall(f".//{_ns('SP')}")
    assert len(sps) == 1
    assert sps[0].get("WIDTH") == "10"


def test_fast_path_soft_hyphen_stripped(tmp_path):
    """Fast path: U+00AD soft hyphen stripped from CONTENT."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="n\u00e9ces-" HPOS="10" VPOS="20" WIDTH="200" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "n\u00e9ces-", corrected_text="n\u00e9ces\u00ad")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    for s in root.findall(f".//{_ns('String')}"):
        assert "\u00ad" not in (s.get("CONTENT") or "")


def test_fast_path_preserves_wc(tmp_path):
    """Fast path: WC confidence scores preserved."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="Bon" HPOS="10" VPOS="20" WIDTH="150" HEIGHT="30" WC="0.95"/>
  <SP WIDTH="10" HPOS="160" VPOS="20"/>
  <String ID="S2" CONTENT="jour" HPOS="170" VPOS="20" WIDTH="200" HEIGHT="30" WC="0.87"/>
</TextLine>"""
    lm = make_line("TL1", "Bon jour", corrected_text="Bon jour")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    strings = root.findall(f".//{_ns('String')}")
    assert strings[0].get("WC") == "0.95"
    assert strings[1].get("WC") == "0.87"


def test_fast_path_preserves_string_ids(tmp_path):
    """Fast path: original String IDs are preserved."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="word_001" CONTENT="Hello" HPOS="10" VPOS="20" WIDTH="180" HEIGHT="30"/>
  <SP WIDTH="10" HPOS="190" VPOS="20"/>
  <String ID="word_002" CONTENT="world" HPOS="200" VPOS="20" WIDTH="200" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "Hello world", corrected_text="Hello world")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    strings = root.findall(f".//{_ns('String')}")
    assert strings[0].get("ID") == "word_001"
    assert strings[1].get("ID") == "word_002"


# ---------------------------------------------------------------------------
# Path 3 + SUBS: fast path with hyphenation
# ---------------------------------------------------------------------------


def test_fast_path_part1_subs_applied(tmp_path):
    """Fast path PART1: SUBS_TYPE/SUBS_CONTENT applied to last String."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="tra-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          SUBS_TYPE="HypPart1" SUBS_CONTENT="travail"/>
  <HYP CONTENT="-"/>
</TextLine>"""
    lm = make_line(
        "TL1",
        "tra-",
        corrected_text="tra-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="travail",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    s = root.findall(f".//{_ns('String')}")[-1]
    assert s.get("SUBS_TYPE") == "HypPart1"
    assert s.get("SUBS_CONTENT") == "travail"


def test_fast_path_part2_subs_applied(tmp_path):
    """Fast path PART2: SUBS_TYPE/SUBS_CONTENT applied to first String."""
    lines_xml = """\
<TextLine ID="TL2" HPOS="10" VPOS="55" WIDTH="400" HEIGHT="30">
  <String ID="S2" CONTENT="vail" HPOS="10" VPOS="55" WIDTH="80" HEIGHT="30"
          SUBS_TYPE="HypPart2" SUBS_CONTENT="travail"/>
</TextLine>"""
    lm = make_line(
        "TL2",
        "vail",
        corrected_text="vail",
        hyphen_role=HyphenRole.PART2,
        hyphen_subs_content="travail",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    s = root.findall(f".//{_ns('String')}")[0]
    assert s.get("SUBS_TYPE") == "HypPart2"
    assert s.get("SUBS_CONTENT") == "travail"


def test_fast_path_no_subs_when_neutralised(tmp_path):
    """Fast path: when subs_content is None, no SUBS attributes on any String."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="boule-" HPOS="10" VPOS="20" WIDTH="120" HEIGHT="30"/>
</TextLine>"""
    lm = make_line(
        "TL1",
        "boule-",
        corrected_text="boule-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content=None,
        hyphen_source_explicit=False,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    for s in root.findall(f".//{_ns('String')}"):
        assert s.get("SUBS_TYPE") is None
        assert s.get("SUBS_CONTENT") is None


def test_fast_path_subs_not_on_wrong_token(tmp_path):
    """Fast path PART2: SUBS must be on first String only, not second."""
    lines_xml = """\
<TextLine ID="TL2" HPOS="10" VPOS="55" WIDTH="400" HEIGHT="30">
  <String ID="S2a" CONTENT="te" HPOS="10" VPOS="55" WIDTH="60" HEIGHT="30"
          SUBS_TYPE="HypPart2" SUBS_CONTENT="porte"/>
  <SP WIDTH="10" HPOS="70" VPOS="55"/>
  <String ID="S2b" CONTENT="ouverte" HPOS="80" VPOS="55" WIDTH="200" HEIGHT="30"/>
</TextLine>"""
    lm = make_line(
        "TL2",
        "te ouverte",
        corrected_text="te ouverte",
        hyphen_role=HyphenRole.PART2,
        hyphen_subs_content="porte",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    strings = root.findall(f".//{_ns('String')}")
    assert strings[0].get("SUBS_TYPE") == "HypPart2"
    assert strings[0].get("SUBS_CONTENT") == "porte"
    # Second String must NOT have SUBS
    assert strings[1].get("SUBS_TYPE") is None
    assert strings[1].get("SUBS_CONTENT") is None


# ---------------------------------------------------------------------------
# Path 4 — SLOW PATH: word count changed, rebuild
# ---------------------------------------------------------------------------


def test_slow_path_preserves_original_attributes(tmp_path):
    """Slow path: recycles ONLY ID + STYLEREFS; WC/CC never recycled.

    Spec F2 / §6.1: the rebuild reuses
    ``ID`` and ``STYLEREFS`` by token ALIGNMENT (identity follows the
    word the source token corresponds to — here ``old`` is closer to
    ``world`` than to ``hello`` by character evidence), recomputes
    ``HPOS``/``WIDTH``, inherits ``VPOS``/``HEIGHT`` from the line, and
    never carries the stale ``WC``/``CC`` confidences (CC's length would
    no longer match the rebuilt CONTENT).
    """
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="old" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          WC="0.95" CC="999" STYLEREFS="font1"/>
</TextLine>"""
    # Word count changes: 1 → 2 (slow path)
    lm = make_line("TL1", "old", corrected_text="hello world")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    strings = root.findall(f".//{_ns('String')}")
    assert len(strings) == 2

    # The alignment matches 'old' to 'world' (sim 0.6 vs 0.2 for
    # 'hello'), so S1's identity + STYLEREFS land THERE — positional
    # recycling would have glued them onto 'hello'.
    s1 = strings[1]
    assert s1.get("ID") == "S1"
    assert s1.get("CONTENT") == "world"
    assert s1.get("VPOS") == "20"
    assert s1.get("HEIGHT") == "30"
    assert s1.get("STYLEREFS") == "font1"
    # F2 — stale confidences never recycled
    assert s1.get("WC") is None
    assert s1.get("CC") is None

    # The unmatched new word gets a generated ID and no styling.
    s2 = strings[0]
    assert s2.get("ID") == "TL1_STR_0000"
    assert s2.get("CONTENT") == "hello"
    assert s2.get("STYLEREFS") is None


def test_slow_path_does_not_copy_stale_subs(tmp_path):
    """Slow path: SUBS_TYPE/SUBS_CONTENT from original String must NOT be blindly copied."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="por-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          SUBS_TYPE="HypPart1" SUBS_CONTENT="porte"/>
  <HYP CONTENT="-" HPOS="110" VPOS="20" WIDTH="16" HEIGHT="30"/>
</TextLine>"""
    # Word count changes: 1 → 2 (slow path)
    # subs_content is None (neutralised) — no SUBS should appear
    lm = make_line(
        "TL1",
        "por-",
        corrected_text="por- extra",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content=None,
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    for s in root.findall(f".//{_ns('String')}"):
        assert s.get("SUBS_TYPE") is None, (
            f"Stale SUBS_TYPE must not be copied (found on {s.get('ID')})"
        )
        assert s.get("SUBS_CONTENT") is None, (
            f"Stale SUBS_CONTENT must not be copied (found on {s.get('ID')})"
        )


def test_slow_path_part1_preserves_hyp(tmp_path):
    """Slow path PART1: the HYP element keeps its CONTENT and real WIDTH,
    but its geometry is REPOSITIONED to the end of the rebuilt line so the
    child widths sum exactly to the line WIDTH and the HYP does not overlap
    the last String (Audit P2 — the old code copied the HYP's stale HPOS/
    WIDTH verbatim while laying the Strings over a 4% estimate, so the
    children summed past WIDTH and the hyphen overlapped the last String)."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="por-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"/>
  <HYP CONTENT="-" HPOS="110" VPOS="20" WIDTH="16" HEIGHT="30"/>
</TextLine>"""
    # 1 word → 2 words (slow path)
    lm = make_line(
        "TL1",
        "por-",
        corrected_text="Il por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="porte",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")

    hyps = tl.findall(_ns("HYP"))
    assert len(hyps) == 1
    hyp = hyps[0]
    assert hyp.get("CONTENT") == "-"
    # The original HYP's real WIDTH is preserved (reserved for the hyphen).
    assert hyp.get("WIDTH") == "16"
    line_hpos, line_width = 10, 400
    hyp_hpos, hyp_width = int(hyp.get("HPOS")), int(hyp.get("WIDTH"))
    # The HYP sits flush at the line's right edge — children sum to WIDTH.
    assert hyp_hpos + hyp_width == line_hpos + line_width
    # No String overlaps the HYP: every String ends at or before the HYP.
    for s in tl.findall(_ns("String")):
        assert int(s.get("HPOS")) + int(s.get("WIDTH")) <= hyp_hpos


def test_single_string_both_keeps_backward_subs(tmp_path):
    """Audit P2 — a BOTH line with a single String must keep its backward
    HypPart2 marker. The forward HypPart1 write must NOT clobber the same
    element (the trailing HYP already marks the forward hyphen); flipping it
    would destroy the "continues from the previous line" signal."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="nau" SUBS_TYPE="HypPart2" SUBS_CONTENT="konau" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"/>
  <HYP CONTENT="-" HPOS="110" VPOS="20" WIDTH="16" HEIGHT="30"/>
</TextLine>"""
    lm = LineManifest(
        line_id="TL1",
        page_id="P1",
        block_id="TB1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=10, vpos=20, width=400, height=30),
        ocr_text="nau",
        corrected_text="nau",  # identity → SUBS-only path
        hyphen_role=HyphenRole.BOTH,
        hyphen_source_explicit=True,
        hyphen_subs_content="konau",
        hyphen_forward_explicit=True,
        hyphen_forward_subs_content="naukel",
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")
    strings = tl.findall(_ns("String"))
    assert len(strings) == 1
    # The single String keeps its backward HypPart2 — NOT flipped to HypPart1.
    assert strings[0].get("SUBS_TYPE") == "HypPart2"
    assert strings[0].get("SUBS_CONTENT") == "konau"


def test_heuristic_part1_slow_path_no_synthesized_hyp(tmp_path):
    """Audit P1 — a heuristically-detected PART1 (trailing dash, no HYP /
    SUBS markup) must NOT gain a synthesised <HYP> on the slow path, nor a
    phantom trailing hyphen in the output: the trailing dash stays inside
    the String CONTENT (conservative-heuristic invariant)."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="worthy-" HPOS="10" VPOS="20" WIDTH="200" HEIGHT="30"/>
</TextLine>"""
    lm = make_line(
        "TL1",
        "worthy-",
        corrected_text="worthy- more",  # 1 word → 2 words: slow path
        hyphen_role=HyphenRole.PART1,
        hyphen_source_explicit=False,  # heuristic
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")
    assert tl.findall(_ns("HYP")) == [], "heuristic PART1 must not synthesise a HYP"
    contents = [s.get("CONTENT") for s in tl.findall(_ns("String"))]
    # The dash stays on the token; no phantom hyphen appended.
    assert contents == ["worthy-", "more"]


def test_slow_path_recomputes_sp_geometry(tmp_path):
    """Slow path: SP geometry is RECOMPUTED, coherent with the recomputed
    Strings around it (post-audit §6.1 fix — the old contract recycled the
    stale pre-correction HPOS/WIDTH, contradicting the new String layout)."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="un" HPOS="10" VPOS="20" WIDTH="50" HEIGHT="30"/>
  <SP WIDTH="12" HPOS="60" VPOS="22"/>
  <String ID="S2" CONTENT="deux" HPOS="72" VPOS="20" WIDTH="90" HEIGHT="30"/>
</TextLine>"""
    # 2 words → 3 words (slow path)
    lm = make_line("TL1", "un deux", corrected_text="un deux trois")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])

    tl = root.find(f".//{_ns('TextLine')}[@ID='TL1']")
    cursor = 10  # line HPOS
    for c in tl:
        local = c.tag.rsplit("}", 1)[-1]
        if local not in ("String", "SP"):
            continue
        # Contiguous layout: each child starts where the previous ended.
        assert int(c.get("HPOS")) == cursor, f"{local} not contiguous"
        cursor += int(c.get("WIDTH"))
    sps = root.findall(f".//{_ns('SP')}")
    # VPOS inherited from the line. The SP's HPOS/WIDTH are recomputed, and
    # since the anchored layout keeps the boxes of "un" and "deux" (both
    # untouched by the correction), the recomputed blank between them is
    # exactly the one the source drew: 60..72. What must never come back is
    # a stale SP that contradicts the Strings around it.
    assert sps[0].get("VPOS") == "20"
    assert (sps[0].get("HPOS"), sps[0].get("WIDTH")) == ("60", "12")
    strings = {s.get("CONTENT"): s for s in tl.findall(_ns("String"))}
    assert (strings["un"].get("HPOS"), strings["un"].get("WIDTH")) == ("10", "50")
    assert (strings["deux"].get("HPOS"), strings["deux"].get("WIDTH")) == ("72", "90")
    # the inserted word sits after "deux" at its natural size, not stretched
    # to the end of the line
    assert int(strings["trois"].get("HPOS")) > 162
    assert int(strings["trois"].get("HPOS")) + int(strings["trois"].get("WIDTH")) < 410


# ---------------------------------------------------------------------------
# TextLine invariant preservation
# ---------------------------------------------------------------------------


def test_line_id_preserved(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="Bonjour" HPOS="10" VPOS="20" WIDTH="200" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "Bonjour", corrected_text="Bonjour")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")
    assert tl.get("ID") == "TL1"


def test_coords_preserved(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="test" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "test", corrected_text="corrected text")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")
    assert tl.get("HPOS") == "10"
    assert tl.get("VPOS") == "20"
    assert tl.get("WIDTH") == "400"
    assert tl.get("HEIGHT") == "30"


def test_no_newline_in_content(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="old" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "old", corrected_text="hello world")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    for s in root.findall(f".//{_ns('String')}"):
        assert "\n" not in (s.get("CONTENT") or "")


def test_string_ids_slow_path(tmp_path):
    """Slow path: extra words get generated IDs; existing words reuse
    original — via alignment: 'old' matches 'world', so the
    generated ID goes to 'hello' (target index 0)."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="old" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "old", corrected_text="hello world")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    strings = root.findall(f".//{_ns('String')}")
    ids = [s.get("ID") for s in strings]
    assert "S1" in ids
    assert "TL1_STR_0000" in ids


# ---------------------------------------------------------------------------
# Hyphenation: HYP preservation
# ---------------------------------------------------------------------------


def test_part1_has_hyp_element(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="por-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          SUBS_TYPE="HypPart1" SUBS_CONTENT="porte"/>
  <HYP CONTENT="-"/>
</TextLine>"""
    lm = make_line(
        "TL1",
        "por-",
        corrected_text="por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="porte",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    hyps = root.find(f".//{_ns('TextLine')}").findall(_ns("HYP"))
    assert len(hyps) == 1
    assert hyps[0].get("CONTENT") == "-"


def test_heuristic_hyp_preserved(tmp_path):
    """Heuristic PART1: HYP element is preserved even without explicit subs."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="boule-" HPOS="10" VPOS="20" WIDTH="120" HEIGHT="30"/>
  <HYP CONTENT="-" HPOS="130" VPOS="20" WIDTH="16" HEIGHT="30"/>
</TextLine>"""
    lm = make_line(
        "TL1",
        "boule-",
        corrected_text="boule-",
        hyphen_role=HyphenRole.PART1,
        hyphen_source_explicit=False,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")
    hyps = tl.findall(_ns("HYP"))
    assert len(hyps) == 1
    assert hyps[0].get("CONTENT") == "-"
    assert hyps[0].get("HPOS") == "130"


def test_subs_content_written_when_explicit(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="con-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          SUBS_TYPE="HypPart1" SUBS_CONTENT="construction"/>
  <HYP CONTENT="-"/>
</TextLine>"""
    lm = make_line(
        "TL1",
        "con-",
        corrected_text="con-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="construction",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    last_str = root.findall(f".//{_ns('String')}")[-1]
    assert last_str.get("SUBS_CONTENT") == "construction"


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


def test_round_trip_normal(tmp_path):
    """Parse → rewrite without correction → re-parse → same IDs."""
    xml_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="{NS_V3}">
  <Layout>
    <Page ID="P1" WIDTH="2480" HEIGHT="3508">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="2480" HEIGHT="3508">
        <TextBlock ID="TB1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="60">
          <TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
            <String ID="S1" CONTENT="Bonjour" HPOS="10" VPOS="20" WIDTH="200" HEIGHT="30"/>
            <SP WIDTH="10"/>
            <String ID="S2" CONTENT="monde" HPOS="220" VPOS="20" WIDTH="190" HEIGHT="30"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""
    xml_path = tmp_path / "round.xml"
    xml_path.write_text(xml_content, encoding="utf-8")

    pages, _ = parse_alto_file(xml_path, "round.xml")
    _res = rewrite_alto_file(xml_path, pages, "openai", "gpt-4o")
    result_bytes = _res.xml_bytes
    out_path = tmp_path / "out.xml"
    out_path.write_bytes(result_bytes)
    pages2, _ = parse_alto_file(out_path, "out.xml")

    assert len(pages2) == 1
    assert len(pages2[0].lines) == 1
    assert pages2[0].lines[0].line_id == "TL1"


# ---------------------------------------------------------------------------
# pretty_print=False — output must not gratuitously add inter-element whitespace
# ---------------------------------------------------------------------------


def test_rewriter_does_not_pretty_print(tmp_path):
    """B-004: pretty_print=True used to reformat the entire XML even when
    nothing changed, breaking byte-level diff utility for users."""
    # Compact source (no whitespace between TextLine children).
    xml_content = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<alto xmlns="{NS_V3}"><Layout>'
        f'<Page ID="P1" WIDTH="100" HEIGHT="100">'
        f'<PrintSpace HPOS="0" VPOS="0" WIDTH="100" HEIGHT="100">'
        f'<TextBlock ID="TB1" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="20">'
        f'<TextLine ID="TL1" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="20">'
        f'<String ID="S1" CONTENT="hello" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="20"/>'
        f"</TextLine>"
        f"</TextBlock></PrintSpace></Page></Layout></alto>"
    )
    xml_path = tmp_path / "compact.xml"
    xml_path.write_bytes(xml_content.encode())

    pages, _ = parse_alto_file(xml_path, "compact.xml")
    _res = rewrite_alto_file(xml_path, pages, "test", "model")
    out_bytes = _res.xml_bytes
    metrics = _res.metrics
    assert metrics.untouched == 1
    out = out_bytes.decode()

    # pretty_print=True would inject "\n        " between every child element.
    # Without it, the only newline allowed is the one before the XML declaration end.
    assert "\n  <" not in out, f"Output appears pretty-printed: {out!r}"
    assert "\n    <" not in out, f"Output appears pretty-printed: {out!r}"


# ---------------------------------------------------------------------------
# Unicode NFC equality in _line_text_unchanged (B-014)
# ---------------------------------------------------------------------------


def test_nfd_source_round_trip_marked_untouched(tmp_path):
    """A source containing NFD characters must round-trip as 'untouched'
    when no correction is applied — reconstruct_textline and the
    manifest ocr_text must compare equal after NFC normalization."""
    import unicodedata

    nfd_word = unicodedata.normalize("NFD", "café")
    assert nfd_word != "café"  # sanity

    xml_content = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<alto xmlns="{NS_V3}"><Layout>'
        f'<Page ID="P1" WIDTH="100" HEIGHT="100">'
        f'<PrintSpace HPOS="0" VPOS="0" WIDTH="100" HEIGHT="100">'
        f'<TextBlock ID="TB1" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="20">'
        f'<TextLine ID="TL1" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="20">'
        f'<String ID="S1" CONTENT="{nfd_word}" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="20"/>'
        f"</TextLine>"
        f"</TextBlock></PrintSpace></Page></Layout></alto>"
    )
    xml_path = tmp_path / "nfd.xml"
    xml_path.write_bytes(xml_content.encode())

    pages, _ = parse_alto_file(xml_path, "nfd.xml")
    # Parser stores in NFC
    assert pages[0].lines[0].ocr_text == "café"

    # No corrections — must be untouched
    _res = rewrite_alto_file(xml_path, pages, "test", "model")
    metrics = _res.metrics
    assert metrics.untouched == 1
    assert metrics.fast_path == 0
    assert metrics.slow_path == 0


def test_round_trip_with_hyphen(tmp_path):
    """Parse with explicit hyphen → rewrite → HYP present, IDs intact."""
    xml_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="{NS_V3}">
  <Layout>
    <Page ID="P1" WIDTH="2480" HEIGHT="3508">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="2480" HEIGHT="3508">
        <TextBlock ID="TB1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="80">
          <TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
            <String ID="S1" CONTENT="por-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
                    SUBS_TYPE="HypPart1" SUBS_CONTENT="porte"/>
            <HYP CONTENT="-"/>
          </TextLine>
          <TextLine ID="TL2" HPOS="10" VPOS="55" WIDTH="400" HEIGHT="30">
            <String ID="S2" CONTENT="te" HPOS="10" VPOS="55" WIDTH="60" HEIGHT="30"
                    SUBS_TYPE="HypPart2" SUBS_CONTENT="porte"/>
            <SP WIDTH="10"/>
            <String ID="S3" CONTENT="ouverte" HPOS="80" VPOS="55" WIDTH="200" HEIGHT="30"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""
    xml_path = tmp_path / "hyp.xml"
    xml_path.write_text(xml_content, encoding="utf-8")

    pages, _ = parse_alto_file(xml_path, "hyp.xml")
    _res = rewrite_alto_file(xml_path, pages, "openai", "gpt-4o")
    result_bytes = _res.xml_bytes
    root = etree.fromstring(result_bytes)
    hyp_els = root.findall(f".//{{{NS_V3}}}HYP")
    assert len(hyp_els) >= 1
    assert hyp_els[0].get("CONTENT") == "-"

    tl1 = root.find(f".//{{{NS_V3}}}TextLine[@ID='TL1']")
    assert tl1 is not None
    assert tl1.get("WIDTH") == "400"
