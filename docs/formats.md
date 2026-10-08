# Formats — ALTO and PAGE

Both format backends produce the **same `DocumentManifest`** (§6.3): the
pure core (planner, guards, hyphenation reconciler, edit protocol) never
knows which format it is correcting. Each backend owns its parser, its
rewriter and a `FormatAdapter` binding for the pipeline's format seam.

Security is format-independent: every `etree.parse`/`fromstring` call in
`formats/**` goes through the hardened `make_safe_parser()`
(`resolve_entities=False`, `no_network=True`, `load_dtd=False`,
`dtd_validation=False`) — enforced by an AST contract test, not by
convention.

## ALTO (`saknussemm.formats.alto`)

Versions 2/3/4 (namespace auto-detected). Line text is reconstructed from
`String`/`SP`/`HYP` children; hyphenation uses the explicit
`SUBS_TYPE`/`SUBS_CONTENT`/`HYP` markup when present, a conservative
trailing-dash heuristic otherwise.

The rewriter is 4-path, most-conservative-first:

| Path | When | What changes |
|---|---|---|
| UNTOUCHED | text + SUBS unchanged | nothing |
| SUBS_ONLY | text same, SUBS stale | `SUBS_*` attributes only |
| FAST | word count unchanged, no suspected boundary movement | `CONTENT` per String; stale `WC`/`CC` and Glyph children removed from changed words |
| SLOW | word count changed or boundary movement suspected | line rebuilt: semantic attributes transferred by token alignment, word boxes estimated between surviving anchors with a proportional fallback, `VPOS`/`HEIGHT` inherited, `WC`/`CC` never recycled |

The TextLine's own geometry is **never** modified. Word-level geometry
after a slow-path rebuild is a documented approximation.

A slow-path rebuild cannot re-attach a `String`'s non-whitelisted semantic
attributes (`TAGREFS` links to structural tags, `language`, vendor
attributes) to re-segmented words without guessing, so it drops them — but,
like PAGE's word granularity, the loss is **counted, not hidden**: each
dropped attribute surfaces on `CorrectionReport.format_losses` as
`<attr>_dropped` (e.g. `tagrefs_dropped`), per line and aggregate. `WC`/`CC`
(invalidated by the text change) are counted per affected line under
`confidence_invalidated`; recomputed geometry is not a loss counter.
Removed Glyph elements are counted under `glyph_elements_removed`.
Unchanged words on the fast path keep their glyphs.
If removing an element would leave a previously resolved XML reference
dangling, the ALTO rewriter raises `ProjectionError`; the pipeline withholds
the file. It does not guess a replacement target for reading-order links.

Both formats suspect a boundary move when editing adjacent words together
costs fewer character edits than keeping their separate slots. This catches
`le stcmps` → `les temps`, including its OCR typo. It remains a text-only
heuristic: ambiguous edits can have equal costs, and geometry is not proven
correct by retaining the fast path or by reporting text fidelity `exact`.

## PAGE (`saknussemm.formats.page`)

PRImA PAGE — the native format of Transkribus and eScriptorium; dated
namespaces (2013-07-15 … 2019-07-15+) auto-detected. Normative rules
P1–P7 (spec §6.2):

- **P1 — polygons are read-only.** `Coords@points` is preserved verbatim
  on `Coords.polygon`; the enclosing bbox is derived for the planner.
  There is **no** geometric slow path.
- **P2/P3 — canonical text.** The minimal-`@index` line `TextEquiv`
  (absent index ≡ 0), else the space-joined `Word` Unicode. On rewrite
  the canonical `TextEquiv` is updated (Unicode + `PlainText`), its stale
  `@conf` dropped, alternative `TextEquiv` removed.
- **P4 — words.** Count unchanged and no suspected boundary movement → each
  `Word` updated in place, its `Coords` kept. Count changed or boundaries
  suspect → the `Word` children are removed and the
  text lives at line level; the lost granularity is **counted**, not
  hidden (`words_dropped`). A changed Word loses its stale Glyph children
  (`glyph_elements_removed`). A changed line invalidates the aggregate
  `TextEquiv` readings of its ancestor TextRegions
  (`region_textequiv_dropped`), without inventing a concatenation order.
  `LossPolicy(strict=True)` refuses a correction requiring Word removal.
  It also refuses a changed line with Word markup if the parser's private
  Word readings are unavailable (for example after manifest JSON round-trip);
  reload the XML to restore that evidence. Identity runs remain untouched.
- **P5 — heuristic hyphenation.** Repertoire `-` `¬` (U+00AC) `⸗`
  (U+2E17) `­` (U+00AD), alpha-before-hyphen required; always
  `hyphen_source_explicit=False` (conservative reconciliation, no
  invented SUBS). The source hyphen character is preserved on rewrite —
  a producer cannot normalise `¬` → `-`.
- **P6 — `custom` microformat.** Structural groups (`readingOrder`,
  `structure`) survive verbatim; offset-anchored groups (`textStyle`,
  tags with `offset`/`length`) are dropped once the text changes, and
  counted (`custom_offset_stripped`).
- **P7 — provenance.** `MetadataItem type="processingStep"` on 2019+
  schemas, `Metadata/Comments` fallback earlier. No wall-clock timestamp
  ⇒ deterministic output.

PAGE-specific losses surface on `CorrectionReport.format_losses`.

## Provenance (§11)

Every corrected file records the pass: provider/model labels, the library
version and the run's `config_fingerprint()` — a stable hash over the five
policies that can change the delivered bytes (`RetryPolicy`, `GuardConfig`, `ChunkPlannerConfig`, `PairingPolicy` and `LossPolicy`). A consumer holding
the same policy objects can recompute and verify it. `ConfidencePolicy`
and `RoutingPolicy` are frozen policies too, but stay outside the composite
while they cannot alter output: a fingerprint that moved without the output
moving would be unreadable as evidence. ALTO 2/3 records a
`postProcessingStep` inside `OCRProcessing`. ALTO 4 appends a new
`Processing` with a unique `ID` and direct `processingStepDescription` /
`processingSoftware` children. Existing processing records are preserved.
PAGE uses the P7 slots.

## Corpus

`examples/` carries the non-regression corpus: BnF ALTO
(`sample.xml`, `X0000002.xml`, byte-parity golden hashes) and
`examples/page/` (OCR17plus triplets — the same page as PAGE raw, PAGE
corrected and ALTO 4 — plus NewsEye columnar press; provenance and
licences in `examples/page/PROVENANCE.md`).
