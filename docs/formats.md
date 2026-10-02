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
| FAST | word count unchanged | `CONTENT` per String; stale `WC`/`CC` dropped (F2) |
| SLOW | word count changed | line rebuilt: `ID`/`STYLEREFS`/`STYLE` recycled positionally, `HPOS`/`WIDTH` recomputed (cumulative rounding, F6), `VPOS`/`HEIGHT` inherited, `WC`/`CC`/`SUBS_*` never recycled |

The TextLine's own geometry is **never** modified. Word-level geometry
after a slow-path rebuild is a documented approximation.

A slow-path rebuild cannot re-attach a `String`'s non-whitelisted semantic
attributes (`TAGREFS` links to structural tags, `language`, vendor
attributes) to re-segmented words without guessing, so it drops them — but,
like PAGE's word granularity, the loss is **counted, not hidden**: each
dropped attribute surfaces on `CorrectionReport.format_losses` as
`<attr>_dropped` (e.g. `tagrefs_dropped`), per line and aggregate. `WC`/`CC`
(genuinely invalidated by the text change) and recomputed geometry are not
losses. The fast/untouched paths edit in place and preserve these
attributes.

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
- **P4 — words.** Count unchanged → each `Word` updated in place, its
  `Coords` kept. Count changed → the `Word`s the correction left alone are
  kept as they are, and the run it changed gets new `Word`s whose polygon
  is **cut out of a polygon of the source** (a split word is its own
  polygon cut by a vertical line; a merge or an inserted word takes the
  line's polygon between two abscissae). When no word can be kept — or a
  polygon cannot be read, or the words do not run left to right — the
  `Word` children are removed and the text lives at line level. Every
  source `Word` removed is **counted**, not hidden (`words_dropped`).
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
moving would be unreadable as evidence. ALTO records the pass in whichever container the source
carries: a `postProcessingStep` inside an existing `<OCRProcessing>` (what
real ABBYY/Tesseract/Gallica exports use), or a `processingStep` under the
ALTO 4.0 generic `<Processing>`. PAGE uses the P7 slots.

## Corpus

`examples/` carries the non-regression corpus: BnF ALTO
(`sample.xml`, `X0000002.xml`, byte-parity golden hashes) and
`examples/page/` (OCR17plus triplets — the same page as PAGE raw, PAGE
corrected and ALTO 4 — plus NewsEye columnar press; provenance and
licences in `examples/page/PROVENANCE.md`).
