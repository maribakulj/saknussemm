"""Ask an LLM for a whole page at once, and put the answer back on its lines.

The engine's two modes differ in **who holds line identity**:

============  ==========================  ========  ========  ======
mode          identity held by            calls     tokens    cost
============  ==========================  ========  ========  ======
line-keyed    the JSON contract, per line   ~2 000    5.49 M   $1.11
page-aligned  the alignment, after the      **28**  **0.39 M** **$0.14**
              fact
============  ==========================  ========  ========  ======

Measured on the 24 592-line Gallica corpus. The saving is not cleverness: the
line-keyed envelope carries ``prev_text`` and ``next_text`` with every line,
so each line's text travels three times, and the JSON around it weighs 7.9×
the text itself.

**Everything this producer gives up is paid in one place.** The answer has no
line ids, so the mapping is recovered by
:func:`~saknussemm.core.page_alignment.align_page_lines`, whose docstring
holds the measurements and the refusals. This module's job is to not undo any
of them:

- A line the alignment will not vouch for produces **no op**, so it keeps its
  OCR text. Hence ``requires_full_coverage = False`` — an uncovered line here
  is an expected outcome (1.6% on the worst real page), not a degraded
  response to retry. Declaring ``True`` would fail every page over lines the
  engine already knows how to leave alone.
- A response of the wrong shape, or an alignment that ran out of corridor, is
  a **malformed response**: raised, retryable, counted. Not silently turned
  into zero edits, which would report a clean run that corrected nothing.
"""

from __future__ import annotations

from typing import Any, Literal

from saknussemm.core.editing import EditScript, ReplaceLine, ReplaceSpan
from saknussemm.core.page_alignment import (
    DEFAULT_LINE_BAND,
    align_page_lines,
    reproject_page_lines,
)
from saknussemm.core.protocols import (
    ProducerMetadata,
    ProducerOptions,
    StructuredCompletionClient,
)
from saknussemm.core.schemas import CorrectionRequest, ModelCapabilities, Usage
from saknussemm.errors import ProposalValidationError
from saknussemm.integrations.llm import prompt_schema_fingerprint
from saknussemm.integrations.page import (
    PAGE_BREAKS_KEY,
    PAGE_OUTPUT_JSON_SCHEMA,
    PAGE_SYSTEM_PROMPT,
    page_lines_from_response,
)


class PageLLMEditProducer:
    """Wrap a :class:`StructuredCompletionClient` as a page-aligned producer."""

    wants_geometry: bool = False
    wants_image: bool = False
    #: An unmatched line is an expected, named outcome — it keeps its OCR
    #: text, like every line the engine cannot vouch for. Declaring full
    #: coverage would turn the 1.6% the alignment declines to settle into a
    #: validator error and fail whole pages over it.
    requires_full_coverage: bool = False

    def __init__(
        self,
        provider: StructuredCompletionClient,
        api_key: str,
        model: str,
        *,
        system_prompt: str | None = None,
        output_schema: dict[str, Any] | None = None,
        line_band: int = DEFAULT_LINE_BAND,
        line_matching: Literal["jaccard", "characters"] = "jaccard",
        capabilities: ModelCapabilities | None = None,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._model = model
        self._line_band = line_band
        #: How line identity is recovered. ``"jaccard"`` matches a returned
        #: line to a source line by token overlap and REFUSES without
        #: evidence; ``"characters"`` re-cuts the returned stream on the
        #: source boundaries and never refuses. The second corrects better
        #: (3.7% against 6.4% distance to ground truth — the measurement is
        #: in :func:`~saknussemm.core.page_alignment.reproject_page_lines`)
        #: but assumes an in-order stream — and NOTHING in it verifies that
        #: assumption. It places every returned character somewhere, so a
        #: stream that is not the page's lines (a model that transcribed a
        #: column crop instead of correcting the list) is cut onto the
        #: source boundaries anyway: measured at 46 % character error and
        #: 201 lines carrying another line's text on 5 111 lines of 1930s
        #: press, against 11 % untouched. Never run it without the
        #: page-scope neighbour margin, ``GuardConfig(attachment_scope=
        #: "page")``, which took those 201 to one — and that one was a
        #: garbled ground truth, not a mis-attachment.
        #:
        #: The default stays ``"jaccard"``: the measurement covers nine
        #: pages, and changing shipped behaviour is a maintainer's call, not
        #: a consequence of nine pages.
        self._line_matching = line_matching
        self._system_prompt = (
            PAGE_SYSTEM_PROMPT if system_prompt is None else system_prompt
        )
        self._output_schema = (
            PAGE_OUTPUT_JSON_SCHEMA if output_schema is None else output_schema
        )
        self.capabilities = capabilities or ModelCapabilities(
            text=True, vision=False, structured_output=True
        )
        self.metadata = ProducerMetadata(
            name="page-llm",
            implementation=model,
            configuration_fingerprint=prompt_schema_fingerprint(
                self._system_prompt, self._output_schema
            ),
        )

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]:
        source_lines = [line.ocr_text for line in payload.lines]
        # Which lines end on half a word. Without it the model completes the
        # broken word on the first line and the validator refuses the whole
        # page — measured as the mode's leading failure before this existed.
        breaks = [
            index
            for index, line in enumerate(payload.lines)
            if line.hyphenation_role in ("HypPart1", "HypBoth")
        ]
        # The compact envelope IS the mode: bare strings, no ids, no
        # neighbour copies. Sending `payload.model_dump()` here would send
        # every line's text three times and give back the $1.11 this
        # producer exists to avoid.
        raw, usage = await self._provider.complete_structured(
            api_key=self._api_key,
            model=self._model,
            system_prompt=self._system_prompt,
            user_payload={"lines": source_lines, PAGE_BREAKS_KEY: breaks},
            json_schema=self._output_schema,
            temperature=options.temperature,
        )
        returned = page_lines_from_response(raw)
        if returned is None:
            raise ProposalValidationError(
                "page response is not {'lines': [str, …]} — with position as "
                "the only identity channel, a salvaged partial list would "
                "shift every line after the gap"
            )

        if self._line_matching == "characters":
            texts = reproject_page_lines(source_lines, returned)
            ops: list[ReplaceLine | ReplaceSpan] = [
                ReplaceLine(line_id=line.line_id, text=text)
                for line, text in zip(payload.lines, texts, strict=True)
                if text and text != line.ocr_text
            ]
            return EditScript(ops=ops), usage

        alignment = align_page_lines(source_lines, returned, band=self._line_band)
        if alignment.band_exhausted:
            raise ProposalValidationError(
                "the returned page could not be aligned within its band: the "
                "model reordered or dropped enough that position no longer "
                "identifies a line. Refused rather than approximated."
            )

        ops = [
            ReplaceLine(line_id=line.line_id, text=returned[target])
            for line, target in zip(payload.lines, alignment.matched, strict=True)
            if target is not None and returned[target] != line.ocr_text
        ]
        return EditScript(ops=ops), usage


__all__ = ["PageLLMEditProducer"]
