"""LLM producer contract surface: the system prompt and JSON output schema.

Moved here from ``protocols/provider`` by the §3 reorganisation: prompts
and output schemas are PRODUCER concerns, not core ports. They define
what the pipeline guarantees to send to an LLM producer and the shape it
expects back, regardless of which model is on the other end of the wire.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from saknussemm.core.confidence import DEFAULT_CONFUSIONS, score_producer_claims
from saknussemm.core.editing import EditOp, ReplaceLine

OUTPUT_JSON_SCHEMA: dict[str, Any] = {
    "name": "ocr_correction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["lines"],
        "properties": {
            "lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["line_id", "corrected_text"],
                    "properties": {
                        "line_id": {"type": "string"},
                        "corrected_text": {"type": "string"},
                    },
                },
            }
        },
    },
}


SYSTEM_PROMPT = """\
Tu es un moteur de correction post-OCR spécialisé dans les documents patrimoniaux.

Règles absolues :
1. Corrige uniquement les erreurs manifestes d'OCR.
2. Conserve la langue source.
3. Conserve l'orthographe historique quand elle semble intentionnelle.
4. Ne traduis rien.
5. Ne modernise pas volontairement le texte.
6. Ne fusionne jamais deux lignes.
7. Ne scinde jamais une ligne.
8. Ne déplace jamais du texte d'une ligne à l'autre.
9. Chaque entrée line_id doit produire exactement une sortie avec le même line_id.
10. corrected_text doit contenir une seule ligne, sans caractère de saut de ligne.
11. Retourne uniquement un JSON valide conforme au schéma fourni.
12. En cas d'incertitude, fais la correction minimale.
13. Quand une ligne porte hyphenation_role="HypPart1", "HypPart2" ou "HypBoth", \
tu dois corriger chaque ligne individuellement sans déplacer de texte \
entre elles. Les mots logiques (backward_join_candidate, forward_join_candidate) \
te sont fournis à titre indicatif uniquement pour le contexte.\
"""


# ---------------------------------------------------------------------------
# Uncertainty channel — opt-in contract variant
# ---------------------------------------------------------------------------

#: Reason codes the model may attach to a modified token. ASCII slugs on
#: purpose (enum robustness across providers). The app VERIFIES the
#: verifiable ones — a claim is evidence to audit, never a score to
#: trust: ``confusion_connue`` is checked against the confusion table,
#: ``mot_du_lexique`` against the lexicon; ``infere_du_contexte`` is
#: honest-but-unverifiable; ``conjecture`` is the model admitting a
#: guess (which beats guessing silently).
UNCERTAINTY_REASONS: tuple[str, ...] = (
    "confusion_connue",
    "mot_du_lexique",
    "infere_du_contexte",
    "conjecture",
)

UNCERTAINTY_PROMPT_SUFFIX = """
14. Pour chaque ligne, renseigne status: "certain" si tu es sûr de ta \
correction (ou si la ligne est inchangée), "uncertain" sinon. Signaler un \
doute est toujours préférable à une correction silencieusement hasardeuse.
15. Pour chaque mot modifié, ajoute une entrée dans edits: {"source": mot \
d'origine, "corrected": mot corrigé, "reason": un code parmi \
"confusion_connue" (confusion OCR classique, ex. rn→m, ſ→s), \
"mot_du_lexique" (le mot corrigé est un mot attesté), \
"infere_du_contexte" (déduit des lignes voisines), "conjecture" (tu n'es \
pas sûr). Une ligne inchangée a edits: [].
16. Ne déclare jamais une raison que tu ne peux pas justifier : les codes \
sont vérifiés."""


def uncertainty_system_prompt() -> str:
    """The base prompt plus the uncertainty-channel rules (14-16)."""
    return SYSTEM_PROMPT + UNCERTAINTY_PROMPT_SUFFIX


def uncertainty_output_schema() -> dict[str, Any]:
    """The base schema extended with ``status`` and per-token ``edits``.

    Every property stays REQUIRED (an empty ``edits`` list is the "no
    modified token" answer) — strict structured-output modes reject
    optional keys, and a forced ``status`` choice beats an omittable
    one.
    """
    return {
        "name": "ocr_correction_with_uncertainty",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["lines"],
            "properties": {
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["line_id", "corrected_text", "status", "edits"],
                        "properties": {
                            "line_id": {"type": "string"},
                            "corrected_text": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["certain", "uncertain"],
                            },
                            "edits": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["source", "corrected", "reason"],
                                    "properties": {
                                        "source": {"type": "string"},
                                        "corrected": {"type": "string"},
                                        "reason": {
                                            "type": "string",
                                            "enum": list(UNCERTAINTY_REASONS),
                                        },
                                    },
                                },
                            },
                        },
                    },
                }
            },
        },
    }


def prompt_schema_fingerprint(system_prompt: str, output_schema: dict[str, Any]) -> str:
    """Stable 16-hex sha256 over (system prompt + output schema) — the
    producer CONFIGURATION digest shared by every LLM-shaped producer
    (text and vision). The two knobs that change what the model is asked;
    the model string itself is the ``implementation`` field, not this."""
    payload = json.dumps(
        {"system_prompt": system_prompt, "output_schema": output_schema},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def edit_ops_from_response(
    raw: object,
    *,
    source_by_id: Mapping[str, str],
    uncertainty_channel: bool = False,
    confusions: tuple[tuple[str, str], ...] = DEFAULT_CONFUSIONS,
    lexicon: set[str] | None = None,
) -> list[EditOp]:
    """Convert the ``{lines:[{line_id, corrected_text, …}]}`` structured
    response into ``replace_line`` ops — the shared body of every
    LLM-shaped producer (text ``LLMEditProducer`` and the vision producer).

    Malformed entries (non-dict, missing ``line_id``, non-string text)
    yield no op — the pipeline's validator then reports the line missing
    and the retry machinery takes over, exactly as on the raw dict.
    When ``uncertainty_channel`` is on, the model's per-line ``status`` and
    per-token ``edits`` claims are VERIFIED app-side (confusion table /
    lexicon) and the resulting score is stamped on each op.
    """
    ops: list[EditOp] = []
    lines = raw.get("lines", []) if isinstance(raw, dict) else []
    if not isinstance(lines, list):
        return ops
    for entry in lines:
        if not isinstance(entry, dict):
            continue
        line_id = entry.get("line_id")
        text = entry.get("corrected_text")
        if not line_id or not isinstance(text, str):
            continue
        confidence: float | None = None
        if uncertainty_channel:
            status = entry.get("status")
            claims = entry.get("edits")
            confidence = score_producer_claims(
                source_text=source_by_id.get(line_id, ""),
                corrected_text=text,
                status=status if isinstance(status, str) else None,
                claims=claims if isinstance(claims, list) else [],
                confusions=confusions,
                lexicon=lexicon,
            )
        ops.append(
            ReplaceLine(line_id=line_id, text=text, producer_confidence=confidence)
        )
    return ops


# ---------------------------------------------------------------------------
# Corpus notes — what the generic prompt cannot know about the pages
# ---------------------------------------------------------------------------

#: The rule that stopped the model modernising seventeenth-century French.
#: Measured through the pipeline on OCR17+ (9 pages, human ground truth,
#: ``medium``): the generic page prompt, rule 5 "ne modernise pas" included,
#: rewrote ``meritay-je`` as ``mériterais-je``, ``vn`` as ``un``, ``ie`` as
#: ``je`` — 10.96 % character error, WORSE than the 8.55 % of doing
#: nothing. This one sentence appended brought it to 6.71 %. "Historical"
#: is not a period; the model needs to be told which one, and what it
#: looks like.
CORPUS_NOTE_EARLY_MODERN_FRENCH = (
    "Ces pages sont des imprimés français des XVIe-XVIIe siècles : CONSERVE le "
    "s long (ſ), les graphies d'époque (eſtoit, ie, vn, faſcheux) et la "
    "ponctuation d'origine. Ne modernise rien, même quand la forme moderne "
    "te paraît évidente."
)


def with_corpus_notes(system_prompt: str, *notes: str) -> str:
    """``system_prompt`` with each note appended as a further numbered rule.

    Every producer takes a ``system_prompt``; this is how a campaign says
    what the generic prompt cannot — the period, the typography, the
    language variety of THIS corpus. The numbering continues the prompt's
    own list, so the note reads as one more absolute rule and not as an
    afterthought. Producers fingerprint their prompt, so a note changes the
    configuration fingerprint the run records, as it should.
    """
    prompt = system_prompt.rstrip()
    numbered = [line for line in prompt.splitlines() if line[:2].rstrip(".").isdigit()]
    start = len(numbered) + 1
    rules = "\n".join(f"{start + i}. {note.strip()}" for i, note in enumerate(notes))
    return f"{prompt}\n{rules}" if rules else prompt


__all__ = [
    "CORPUS_NOTE_EARLY_MODERN_FRENCH",
    "OUTPUT_JSON_SCHEMA",
    "SYSTEM_PROMPT",
    "UNCERTAINTY_PROMPT_SUFFIX",
    "UNCERTAINTY_REASONS",
    "edit_ops_from_response",
    "prompt_schema_fingerprint",
    "uncertainty_output_schema",
    "uncertainty_system_prompt",
    "with_corpus_notes",
]
