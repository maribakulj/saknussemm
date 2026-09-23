"""Pixel-pure vision toolkit — the deterministic half of ``saknussemm[vision]``.

the vision/QE programme splits "the vision producer" into two seams because
they have opposite natures:

* **this module** resolves, decodes and *crops* page pixels — pure,
  deterministic, hashable, and testable with a Pillow-drawn fixture and
  **no network, no API key**;
* the forthcoming ``VisionEditProducer`` is the thin, non-deterministic
  half: it hands a crop to a multimodal provider and parses the reply
  into an :class:`~saknussemm.core.editing.EditScript`.

Keeping the cropper standalone means the crop hash (audit criterion 5)
and every geometry decision (XML→pixel transform, EXIF orientation,
margin, PAGE polygon mask) are verified without a VLM in the loop, and a
second producer (another VLM, a rules-on-crop pass) reuses the same
pixels.

Pillow is the ONLY image dependency and it is imported **lazily inside
each function** — importing this module (introspection, the VLM producer
picking it up) never pays the image runtime, and the pixel-blind core
never pulls it (invariant I4, enforced by the static scan in
``tests/test_edit_producer.py`` and the runtime import contract in
``tests/test_import_contract.py``). The core only ever *carries* an
:class:`~saknussemm.core.schemas.ImageAsset`; this module is what decodes
a file to populate one and what turns its geometry into a crop.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from saknussemm.core.confidence import DEFAULT_CONFUSIONS
from saknussemm.core.editing import EditScript
from saknussemm.core.protocols import ProducerMetadata, ProducerOptions
from saknussemm.core.schemas import (
    Coords,
    CorrectionRequest,
    ImageAsset,
    ImageTransform,
    ModelCapabilities,
    Usage,
)
from saknussemm.errors import ConfigurationError
from saknussemm.integrations.llm import (
    OUTPUT_JSON_SCHEMA,
    edit_ops_from_response,
    prompt_schema_fingerprint,
    uncertainty_output_schema,
    uncertainty_system_prompt,
)

__all__ = [
    "COMPOSITE_VISION_SYSTEM_PROMPT",
    "CompositeVisionEditProducer",
    "Crop",
    "ImagePart",
    "MultimodalStructuredClient",
    "PAGE_VISION_SYSTEM_PROMPT",
    "PageVisionEditProducer",
    "VISION_SYSTEM_PROMPT",
    "VisionEditProducer",
    "build_image_asset",
    "compose_line_strip",
    "crop_region",
    "line_aliases",
    "page_image",
    "verified_image_bytes",
]

#: EXIF Orientation tag id (0x0112).
_EXIF_ORIENTATION_TAG = 274


@dataclass(frozen=True)
class Crop:
    """One encoded page-region crop plus the provenance a run stamps.

    ``data`` is the encoded image bytes; ``sha256`` is their digest — the
    crop-hash the audit trail records next to the source and image hashes
    (acceptance criterion 5). ``pixel_box`` is the ``(left, top, right,
    bottom)`` actually cropped, in the EXIF-normalized ("visual") pixel
    space the transform maps into — so a caller can reproduce or overlay
    it. The crop is a pure function of (image bytes, frame, transform,
    coords, margin, mask flag): same inputs → identical ``sha256``.
    """

    data: bytes
    media_type: str
    sha256: str
    pixel_box: tuple[int, int, int, int]

    @property
    def width(self) -> int:
        return self.pixel_box[2] - self.pixel_box[0]

    @property
    def height(self) -> int:
        return self.pixel_box[3] - self.pixel_box[1]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exif_orientation(img: object) -> int | None:
    """The stored EXIF Orientation (1–8), or ``None`` when absent."""
    getexif = getattr(img, "getexif", None)
    if getexif is None:
        return None
    try:
        exif = getexif()
        raw = exif.get(_EXIF_ORIENTATION_TAG)
    except Exception:  # pragma: no cover - malformed EXIF is "no orientation"
        return None
    if raw is None:
        return None
    value = int(raw)
    return value if 1 <= value <= 8 else None


def build_image_asset(
    page_id: str,
    path: str | Path,
    *,
    transform: ImageTransform | None = None,
    frame_index: int = 0,
) -> ImageAsset:
    """Decode ``path`` and return the populated :class:`ImageAsset` the core
    only ever carries — the "builder" promised by the Phase-4 contract.

    Reads the exact file bytes (their SHA-256 is the provenance anchor),
    opens the requested ``frame_index`` (multipage TIFF), and records the
    real decoded MIME type, the EXIF orientation, and the **visual** pixel
    dimensions (after EXIF transpose — the space :attr:`ImageAsset.transform`
    maps XML coordinates into, and the space :func:`crop_region` works in).
    ``transform`` is carried verbatim; pass it when the OCR coordinate space
    is not the image's native resolution.
    """
    from PIL import Image, ImageOps  # lazy — I4

    p = Path(path)
    raw = p.read_bytes()
    with Image.open(io.BytesIO(raw)) as img:
        fmt = img.format
        mime = Image.MIME.get(fmt) if fmt else None
        media_type = str(mime) if mime else None
        n_frames = int(getattr(img, "n_frames", 1))
        if not 0 <= frame_index < n_frames:
            raise ValueError(
                f"frame_index {frame_index} out of range for {p} ({n_frames} frame(s))"
            )
        img.seek(frame_index)
        orientation = _exif_orientation(img)
        visual = ImageOps.exif_transpose(img)
        width, height = visual.size

    return ImageAsset(
        page_id=page_id,
        uri=str(p),
        sha256=_sha256(raw),
        media_type=media_type,
        pixel_width=int(width),
        pixel_height=int(height),
        frame_index=frame_index,
        exif_orientation=orientation,
        transform=transform,
    )


def _xml_bbox_to_pixels(
    coords: Coords, transform: ImageTransform | None
) -> tuple[float, float, float, float]:
    """Map an XML axis-aligned bbox to visual pixels: ``px = scale*xml +
    offset`` per axis (identity when no transform)."""
    t = transform or ImageTransform()
    left = t.scale_x * coords.hpos + t.offset_x
    top = t.scale_y * coords.vpos + t.offset_y
    right = t.scale_x * (coords.hpos + coords.width) + t.offset_x
    bottom = t.scale_y * (coords.vpos + coords.height) + t.offset_y
    return left, top, right, bottom


def _apply_margin(
    box: tuple[float, float, float, float], ratio: float
) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    mx = (right - left) * ratio
    my = (bottom - top) * ratio
    return left - mx, top - my, right + mx, bottom + my


def _clamp_box(
    box: tuple[float, float, float, float], width: int, height: int
) -> tuple[int, int, int, int]:
    """Round to int and clamp to the image, keeping at least a 1×1 box."""
    left = max(0, min(int(round(box[0])), width - 1))
    top = max(0, min(int(round(box[1])), height - 1))
    right = max(left + 1, min(int(round(box[2])), width))
    bottom = max(top + 1, min(int(round(box[3])), height))
    return left, top, right, bottom


def _polygon_pixels(
    polygon: str, transform: ImageTransform | None, offset: tuple[int, int]
) -> list[tuple[float, float]]:
    """PAGE ``Coords@points`` ("x,y x,y …") mapped to crop-local pixels."""
    t = transform or ImageTransform()
    ox, oy = offset
    points: list[tuple[float, float]] = []
    for token in polygon.split():
        xs, _, ys = token.partition(",")
        px = t.scale_x * float(xs) + t.offset_x - ox
        py = t.scale_y * float(ys) + t.offset_y - oy
        points.append((px, py))
    return points


def verified_image_bytes(asset: ImageAsset) -> bytes:
    """Read ``asset.uri`` and refuse bytes that are not the ones it recorded.

    :func:`build_image_asset` hashes what it read and puts the digest on the
    asset; nothing ever compared it again. That digest is the anchor
    ``RunProvenance.image_digests`` rests on, so a file replaced after the
    asset was built made the report attest a scan the model never saw.

    An asset without a digest is read as-is: the field is optional, a caller
    may legitimately have built the asset without hashing, and inventing a
    failure there would refuse a documented shape.
    """
    raw = Path(asset.uri).read_bytes()
    if asset.sha256 and hashlib.sha256(raw).hexdigest() != asset.sha256:
        raise ConfigurationError(
            f"{asset.uri!r} no longer holds the bytes recorded for page "
            f"{asset.page_id!r}: the asset carries sha256 {asset.sha256!r} "
            f"and the file now hashes to "
            f"{hashlib.sha256(raw).hexdigest()!r}. Cropping it would send the "
            "model one scan while the report attested another, and "
            "image_digests promises that the digest plus the coordinates make "
            "every crop reproducible. Rebuild the asset from the current "
            "file, or point at the file that was hashed."
        )
    return raw


def crop_region(
    asset: ImageAsset,
    coords: Coords,
    *,
    margin_ratio: float = 0.0,
    mask_polygon: bool = False,
    encode_format: str = "PNG",
    source_bytes: bytes | None = None,
) -> Crop:
    """Crop ``coords`` from ``asset``'s image and return an encoded :class:`Crop`.

    Opens ``asset.uri`` at ``asset.frame_index``, normalizes EXIF
    orientation (so pixels match the OCR's visual coordinate space), maps
    the XML bbox to pixels via ``asset.transform``, optionally grows it by
    ``margin_ratio`` on each side (0.1 = +10 %), clamps to the image, and
    re-encodes as ``encode_format`` (PNG = lossless, deterministic bytes).

    ``mask_polygon`` (PAGE only): when the line carries a
    ``coords.polygon``, pixels outside it are made transparent (RGBA), so
    a slanted or multi-column line does not leak its neighbours into the
    crop. A no-op when there is no polygon.

    Deterministic in its inputs — and until 2026-08-17 one of those inputs
    was a **path**, not bytes, so the sentence above was not true of the
    file: this function reopened ``asset.uri`` and never checked it against
    the digest :func:`build_image_asset` recorded. Measured, swapping the
    file between the two calls:

        asset.sha256 (recorded in the report) : e8b42963fb4dbae2
        file actually opened here            : ec6297512ddb3c8d
        crop before / after the swap         : 4e32a320… / dc9c1fc8…

    The report attested one scan while the model saw another, and
    ``RunProvenance.image_digests`` promises exactly the opposite — that the
    source digest plus the coordinates make every crop reproducible.

    ``source_bytes`` is how a caller cropping many lines from one page pays
    the read and the verification once: the producer does that per chunk.
    Passing them makes the caller responsible for what they hold, which is
    a different claim from the one this function makes about a file.
    """
    from PIL import Image, ImageDraw, ImageOps  # lazy — I4

    raw_bytes = (
        source_bytes if source_bytes is not None else verified_image_bytes(asset)
    )
    with Image.open(io.BytesIO(raw_bytes)) as raw:
        raw.seek(asset.frame_index)
        transposed = ImageOps.exif_transpose(raw)
        use_polygon = mask_polygon and bool(coords.polygon)
        image = transposed.convert("RGBA" if use_polygon else "RGB")
        img_w, img_h = image.size

        box = _apply_margin(_xml_bbox_to_pixels(coords, asset.transform), margin_ratio)
        left, top, right, bottom = _clamp_box(box, int(img_w), int(img_h))
        crop = image.crop((left, top, right, bottom))

        if use_polygon and coords.polygon is not None:
            points = _polygon_pixels(coords.polygon, asset.transform, (left, top))
            mask = Image.new("L", crop.size, 0)
            ImageDraw.Draw(mask).polygon(points, fill=255)
            crop.putalpha(mask)

        buffer = io.BytesIO()
        crop.save(buffer, format=encode_format)
        data = buffer.getvalue()

    return Crop(
        data=data,
        media_type=f"image/{encode_format.lower()}",
        sha256=_sha256(data),
        pixel_box=(left, top, right, bottom),
    )


# ---------------------------------------------------------------------------
# VisionEditProducer — the thin, non-deterministic half of the vision chain
# ---------------------------------------------------------------------------


VISION_SYSTEM_PROMPT = """\
Tu es un moteur de correction post-OCR spécialisé dans les documents patrimoniaux.
Pour chaque ligne tu reçois le texte OCR ET l'image de la ligne (le crop). L'image
fait foi : lis les caractères réellement présents à l'image.

Règles absolues :
1. Corrige uniquement les erreurs manifestes d'OCR, d'après l'image.
2. Conserve la langue source.
3. Conserve l'orthographe historique quand elle est réellement présente à l'image \
(ſ long, u pour v, ligatures) : ce n'est pas une erreur.
4. Ne traduis rien.
5. Ne modernise pas volontairement le texte.
6. Ne fusionne jamais deux lignes.
7. Ne scinde jamais une ligne.
8. Ne déplace jamais du texte d'une ligne à l'autre.
9. Chaque entrée line_id doit produire exactement une sortie avec le même line_id.
10. corrected_text doit contenir une seule ligne, sans caractère de saut de ligne.
11. Retourne uniquement un JSON valide conforme au schéma fourni.
12. En cas de doute ou d'image illisible, conserve le texte OCR (correction minimale).
13. N'invente jamais un caractère absent de l'image (pas d'hallucination visuelle).\
"""


@dataclass(frozen=True)
class ImagePart:
    """One crop handed to a multimodal provider, tied to the line it depicts.

    ``sha256`` is the crop hash — the provenance the run records so a
    decision is reproducible from (source, image, crop) hashes (acceptance
    criterion 5). ``line_id`` lets the provider (and the audit trail) map
    the image back to the exact line it belongs to.
    """

    line_id: str
    media_type: str
    data: bytes
    sha256: str


@runtime_checkable
class MultimodalStructuredClient(Protocol):
    """The multimodal counterpart of ``StructuredCompletionClient`` (§5.2 bis).

    A VLM call needs image parts the text seam cannot carry, so it is a
    separate protocol rather than a widened ``complete_structured`` — text
    producers keep their lean, image-free contract untouched. The concrete
    client (an out-of-lib provider adapter) encodes the crops into its
    vendor's multimodal message format and returns the same
    ``{lines:[{line_id, corrected_text}]}`` structured shape a text call
    would, plus token :class:`Usage`.
    """

    async def complete_structured_multimodal(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        images: list[ImagePart],
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], Usage | None]: ...


def _declared_image_cap(provider: object) -> int | None:
    """The per-call image cap a client declares on itself, if any.

    A vision producer crops every line of its chunk, and the batcher only
    splits a chunk when ``capabilities.max_images`` says where. Left
    undeclared, the run does not fail loudly: measured on OCR17+ through the
    pipeline, 19 crops went out, the provider refused the ninth (HTTP 400),
    and the engine RETRIED and DOWNGRADED — the ladder reacts to malformed
    output, not to a request refused outright — instead of splitting.

    The client is the one that knows its vendor's limit, so a client may
    declare it (``max_images_per_call``, or the demo's
    ``MAX_IMAGES_PER_CALL``) and the producer reads it when the host passed
    no ``capabilities``. An explicit ``capabilities`` still wins.
    """
    for name in ("max_images_per_call", "MAX_IMAGES_PER_CALL"):
        value = getattr(provider, name, None)
        if isinstance(value, int) and value > 0:
            return value
    return None


class VisionEditProducer:
    """Adapt a :class:`MultimodalStructuredClient` (VLM) to ``EditProducer``.

    The thin, non-deterministic half of the vision chain: for each target
    line it crops the region from the page image (the pure, deterministic
    :func:`crop_region`), hands the crops + OCR text to the multimodal
    provider, and shapes the reply into a ``replace_line``
    :class:`EditScript` — the SAME response parser
    (:func:`~saknussemm.integrations.llm.edit_ops_from_response`) the text
    producer uses, so the guard matrix, validator and uncertainty channel
    all behave identically downstream. Only the payload assembly differs.

    ``wants_geometry`` / ``wants_image`` are ``True``: the pipeline copies
    each line's geometry and the page image into the §4.1 envelope, and
    :func:`require_page_images` guarantees every page has one. The image
    MUST be a structured :class:`ImageAsset` (the cropper needs its uri,
    frame and transform) — a bare :class:`~saknussemm.core.schemas.ImageRef`
    string is refused with a clear error, since it cannot be cropped.

    The core stays pixel-blind: it forwards an opaque asset and never opens
    it; every pixel touched here goes through :func:`crop_region`.

    Pair it with the VLM guard profile — a VLM reads the image, not the
    OCR, so a correct reading of a badly-garbled line diverges further from
    the source than the text guard tolerates::

        CorrectionPipeline(producer=VisionEditProducer(...),
                           guard_config=GuardConfig.vision())
    """

    wants_geometry: bool = True
    wants_image: bool = True
    #: A VLM asked to correct N target lines must return all N (a dropped
    #: line is a degraded response → validator error → retry), same as the
    #: text LLM producer.
    requires_full_coverage: bool = True

    def __init__(
        self,
        provider: MultimodalStructuredClient,
        api_key: str,
        model: str,
        *,
        system_prompt: str | None = None,
        output_schema: dict[str, Any] | None = None,
        uncertainty_channel: bool = False,
        lexicon: set[str] | None = None,
        confusions: tuple[tuple[str, str], ...] = DEFAULT_CONFUSIONS,
        margin_ratio: float = 0.05,
        mask_polygon: bool = False,
        capabilities: ModelCapabilities | None = None,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._model = model
        self._uncertainty_channel = uncertainty_channel
        self._lexicon = lexicon
        self._confusions = confusions
        self._margin_ratio = margin_ratio
        self._mask_polygon = mask_polygon
        #: routing descriptor — a vision model: structured output
        #: AND vision. The default declares vision=True (so it passes the
        #: require_capabilities consistency gate); a host that knows its
        #: VLM's per-call image cap injects ``max_images`` so the Router can
        #: keep a chunk's crops within it.
        self.capabilities = capabilities or ModelCapabilities(
            text=True,
            vision=True,
            structured_output=True,
            max_images=_declared_image_cap(provider),
        )
        default_prompt = (
            uncertainty_system_prompt() if uncertainty_channel else VISION_SYSTEM_PROMPT
        )
        default_schema = (
            uncertainty_output_schema() if uncertainty_channel else OUTPUT_JSON_SCHEMA
        )
        self._system_prompt = default_prompt if system_prompt is None else system_prompt
        self._output_schema = default_schema if output_schema is None else output_schema
        #: Provenance: the generic "vision" producer name, the
        #: model as implementation, and a configuration fingerprint that —
        #: unlike the text producer's — also folds in the crop geometry
        #: knobs (margin, polygon mask), because they change the pixels the
        #: model sees, hence what it is asked.
        self.metadata = ProducerMetadata(
            name="vision",
            implementation=model,
            configuration_fingerprint=prompt_schema_fingerprint(
                self._system_prompt,
                {
                    "output_schema": self._output_schema,
                    "margin_ratio": self._margin_ratio,
                    "mask_polygon": self._mask_polygon,
                },
            ),
        )

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]:
        asset = payload.image_ref
        if not isinstance(asset, ImageAsset):
            raise ConfigurationError(
                "VisionEditProducer requires a structured ImageAsset page "
                "image (build it with build_image_asset), not a bare "
                f"ImageRef; got {type(asset).__name__}"
            )
        # Read and verify ONCE per chunk. This loop cropped per line and
        # each crop reopened the file, so a 40-line chunk read the same scan
        # 40 times and verified it none.
        page_bytes = verified_image_bytes(asset)
        images: list[ImagePart] = []
        for line in payload.lines:
            if line.geometry is None:
                continue
            crop = crop_region(
                asset,
                line.geometry.coords,
                margin_ratio=self._margin_ratio,
                mask_polygon=self._mask_polygon,
                source_bytes=page_bytes,
            )
            images.append(
                ImagePart(
                    line_id=line.line_id,
                    media_type=crop.media_type,
                    data=crop.data,
                    sha256=crop.sha256,
                )
            )
        if payload.lines and not images:
            # Nothing to crop: this call would reach a VISION model carrying
            # only text, produce corrections, and report vision provenance —
            # a run that LOOKS like a vision run and never sent an image.
            # Unreachable through the pipeline (LineManifest.coords is
            # required, page dimensions are required ints, and page_dims
            # covers every page), so this guards a direct caller against the
            # worst silent degradation available here. A payload where only
            # SOME lines lack geometry is still served: the rest are cropped.
            raise ConfigurationError(
                "VisionEditProducer received no line geometry for page "
                f"{payload.page_id!r}: none of its {len(payload.lines)} lines "
                "could be cropped, so the model would be asked to correct "
                "from text alone while the run reports a vision producer. "
                "Enrich the chunk with geometry (include_geometry=True and "
                "page dimensions) or route these lines to a text producer."
            )
        raw, usage = await self._provider.complete_structured_multimodal(
            api_key=self._api_key,
            model=self._model,
            system_prompt=self._system_prompt,
            # The text half of the payload — the image asset is sent as
            # image parts, never inlined into the JSON prompt.
            user_payload=payload.model_dump(exclude_none=True, exclude={"image_ref"}),
            images=images,
            json_schema=self._output_schema,
            temperature=options.temperature,
        )
        ops = edit_ops_from_response(
            raw,
            source_by_id={ln.line_id: ln.ocr_text for ln in payload.lines},
            uncertainty_channel=self._uncertainty_channel,
            confusions=self._confusions,
            lexicon=self._lexicon,
        )
        return EditScript(ops=ops), usage


# ---------------------------------------------------------------------------
# CompositeVisionEditProducer — one image per chunk, identity painted into it
# ---------------------------------------------------------------------------


COMPOSITE_VISION_SYSTEM_PROMPT = """\
Tu es un moteur de correction post-OCR spécialisé dans les documents patrimoniaux.
L'IMAGE montre les lignes d'un extrait de page, découpées et empilées ; chaque
ligne est PRÉCÉDÉE À GAUCHE de son identifiant peint entre crochets, comme [K7QZP].
Le JSON donne, pour chaque identifiant, le texte OCR de cette ligne.

Règles absolues :
1. Corrige chaque ligne d'après l'image de la ligne qui porte le MÊME identifiant.
2. Conserve la langue source.
3. Conserve l'orthographe historique quand elle est réellement présente à l'image \
(ſ long, u pour v, ligatures) : ce n'est pas une erreur.
4. Ne traduis rien.
5. Ne modernise pas volontairement le texte.
6. Ne fusionne jamais deux lignes.
7. Ne scinde jamais une ligne.
8. Ne déplace jamais du texte d'une ligne à l'autre.
9. Chaque entrée line_id doit produire exactement une sortie avec le même line_id, \
recopié tel quel.
10. corrected_text doit contenir une seule ligne, sans caractère de saut de ligne.
11. Retourne uniquement un JSON valide conforme au schéma fourni.
12. En cas de doute ou d'image illisible, conserve le texte OCR (correction minimale).
13. N'invente jamais un caractère absent de l'image (pas d'hallucination visuelle).\
"""

#: Characters an alias may use: no ``0``/``O`` and no ``1``/``I``, the pairs a
#: model (or a person) confuses when reading a painted label back.
_ALIAS_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_ALIAS_LENGTH = 5


def line_aliases(line_ids: Sequence[str]) -> dict[str, str]:
    """A short opaque label per line id — deterministic, unique in the batch.

    Why not the line id itself, and why not ``1, 2, 3``. Measured on a
    six-column page of *Le Temps* (1890): given integers, a model that drops
    one parasite line **renumbers** what follows, so 20 (and 142, with a
    smaller model) lines came back under the wrong number. Given opaque
    tokens it **copies** them, because it has no other way to produce
    one — zero under the wrong label on the same page. A raw ALTO id
    (``PAG_2_TL000075``) is opaque enough but long to paint at a legible
    size; five characters from a hash of it are not.

    Deterministic in the id (a rerun paints the same labels, so a crop hash
    is reproducible) and unique within the batch: a collision takes the next
    slice of the digest.
    """
    aliases: dict[str, str] = {}
    taken: set[str] = set()
    for line_id in line_ids:
        digest = hashlib.sha256(line_id.encode("utf-8")).digest()
        chars = [_ALIAS_ALPHABET[b % len(_ALIAS_ALPHABET)] for b in digest]
        for start in range(0, len(chars) - _ALIAS_LENGTH + 1):
            candidate = "".join(chars[start : start + _ALIAS_LENGTH])
            if candidate not in taken:
                break
        else:  # pragma: no cover - 32 slices of a digest do not all collide
            candidate = f"{chars[0]}{len(taken):04d}"
        aliases[line_id] = candidate
        taken.add(candidate)
    return aliases


def compose_line_strip(
    rows: Sequence[tuple[str, Crop]],
    *,
    row_height: int = 44,
    label_width: int = 230,
    gap: int = 10,
    max_row_width: int = 1800,
    max_side: int = 2048,
    encode_format: str = "PNG",
) -> Crop:
    """Stack line crops into one image, each row labelled with its alias.

    The identity of a line is painted INTO the pixels, on the left of the
    ink it names, so a model that pairs by the image — and they do: shown a
    crop with a stray neighbour, a model transcribes top to bottom and
    fills the labels in order — pairs each reading with the right label.
    Nothing the model was not sent can appear in the strip: every row is a
    crop of exactly one line.

    Deterministic in its inputs (same crops, same labels, same knobs → the
    same bytes, hence the same ``sha256``), like :func:`crop_region`. The
    strip is downscaled only when a side would exceed ``max_side``; the
    caller keeps rows legible by keeping chunks short — 20 rows of 44 px is
    the measured sweet spot, and :class:`CompositeVisionEditProducer` bounds
    it through the batcher.
    """
    from PIL import Image, ImageDraw, ImageFont  # lazy — I4

    decoded = []
    for label, crop in rows:
        with Image.open(io.BytesIO(crop.data)) as raw:
            image = raw.convert("RGB")
        scale = row_height / max(1, image.height)
        width = max(1, min(max_row_width, int(round(image.width * scale))))
        decoded.append(
            (label, image.resize((width, row_height), Image.Resampling.LANCZOS))
        )

    strip_w = label_width + max((img.width for _, img in decoded), default=1) + gap
    strip_h = len(decoded) * (row_height + gap) + gap
    canvas = Image.new("RGB", (strip_w, strip_h), "white")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default(size=int(row_height * 0.68))
    except TypeError:  # pragma: no cover - Pillow < 10.1 has no sized default
        font = ImageFont.load_default()
    y = gap
    for label, image in decoded:
        draw.text((8, y + 4), f"[{label}]", fill=(160, 0, 0), font=font)
        canvas.paste(image, (label_width, y))
        draw.line(
            (0, y + row_height + gap // 2, strip_w, y + row_height + gap // 2),
            fill=(200, 200, 200),
            width=1,
        )
        y += row_height + gap

    if max(canvas.size) > max_side:
        factor = max_side / max(canvas.size)
        canvas = canvas.resize(
            (max(1, int(canvas.width * factor)), max(1, int(canvas.height * factor))),
            Image.Resampling.LANCZOS,
        )
    buffer = io.BytesIO()
    canvas.save(buffer, format=encode_format)
    data = buffer.getvalue()
    return Crop(
        data=data,
        media_type=f"image/{encode_format.lower()}",
        sha256=_sha256(data),
        pixel_box=(0, 0, canvas.width, canvas.height),
    )


class CompositeVisionEditProducer:
    """A vision producer that sends ONE labelled strip per chunk.

    :class:`VisionEditProducer` sends one crop per line and the line id in
    the text; identity travels beside the pixels. This producer paints it
    into them (:func:`compose_line_strip`) and sends the strip as a single
    image with a lean JSON of ``{line_id, ocr_text, hyphenation_role}``
    entries keyed by the same painted alias (:func:`line_aliases`).

    Why. Measured on 5 111 lines of 1930s press (NewsEye, human ground
    truth): with ids in the text only, a model shown a column crop
    transcribed the image top to bottom and filled the ids in order — 1 746
    lines came back under the wrong id. With the ids painted beside the ink
    and 20 rows per strip: 84. The character error rate went from 39 % to
    6.4 % without any guard, and every remaining mis-attachment fell to the
    page-scope neighbour margin (``GuardConfig(attachment_scope="page")``),
    which is the guard profile to pair this producer with.

    Row count is bounded through the existing image cap: the batcher splits
    any chunk longer than ``capabilities.max_images`` lines, and here one
    line is one row, so ``max_lines`` is declared as ``max_images``. Twenty
    is the measured knee — 40 rows doubled the drift, 10 cost twice the
    calls for 0.1 point.

    Everything after the reply is shared with the other LLM-shaped
    producers: the aliases are mapped back to real line ids and the same
    :func:`~saknussemm.integrations.llm.edit_ops_from_response` shapes the
    ops, so validator, guards and retries behave identically downstream. A
    reply under an alias this chunk never painted yields no op, the
    validator reports the line missing, and the retry machinery takes over.
    """

    wants_geometry: bool = True
    wants_image: bool = True
    requires_full_coverage: bool = True

    def __init__(
        self,
        provider: MultimodalStructuredClient,
        api_key: str,
        model: str,
        *,
        system_prompt: str | None = None,
        max_lines: int = 20,
        row_height: int = 44,
        margin_ratio: float = 0.05,
        mask_polygon: bool = False,
    ) -> None:
        if max_lines < 1:
            raise ConfigurationError("max_lines must be at least 1")
        self._provider = provider
        self._api_key = api_key
        self._model = model
        self._row_height = row_height
        self._margin_ratio = margin_ratio
        self._mask_polygon = mask_polygon
        self._system_prompt = (
            COMPOSITE_VISION_SYSTEM_PROMPT if system_prompt is None else system_prompt
        )
        #: The line-keyed schema, not a parameter: the reply is keyed by the
        #: painted aliases and mapped back here, so a caller-supplied shape
        #: could not be un-aliased.
        self._output_schema = OUTPUT_JSON_SCHEMA
        #: One strip per call, so a provider's per-call image cap never
        #: binds; what ``max_images`` bounds here is the ROW count, through
        #: the batcher that already splits image-bearing chunks.
        self.capabilities = ModelCapabilities(
            text=True, vision=True, structured_output=True, max_images=max_lines
        )
        self.metadata = ProducerMetadata(
            name="vision-composite",
            implementation=model,
            configuration_fingerprint=prompt_schema_fingerprint(
                self._system_prompt,
                {
                    "output_schema": self._output_schema,
                    "max_lines": max_lines,
                    "row_height": row_height,
                    "margin_ratio": margin_ratio,
                    "mask_polygon": mask_polygon,
                },
            ),
        )

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]:
        asset = payload.image_ref
        if not isinstance(asset, ImageAsset):
            raise ConfigurationError(
                "CompositeVisionEditProducer requires a structured ImageAsset "
                "page image (build it with build_image_asset), not a bare "
                f"ImageRef; got {type(asset).__name__}"
            )
        page_bytes = verified_image_bytes(asset)
        aliases = line_aliases([line.line_id for line in payload.lines])
        rows: list[tuple[str, Crop]] = []
        for line in payload.lines:
            if line.geometry is None:
                continue
            crop = crop_region(
                asset,
                line.geometry.coords,
                margin_ratio=self._margin_ratio,
                mask_polygon=self._mask_polygon,
                source_bytes=page_bytes,
            )
            rows.append((aliases[line.line_id], crop))
        if payload.lines and not rows:
            raise ConfigurationError(
                "CompositeVisionEditProducer received no line geometry for "
                f"page {payload.page_id!r}: none of its {len(payload.lines)} "
                "lines could be cropped, so the model would be asked to "
                "correct from text alone while the run reports a vision "
                "producer. Enrich the chunk with geometry or route these "
                "lines to a text producer."
            )
        strip = compose_line_strip(rows, row_height=self._row_height)
        user_payload: dict[str, Any] = {
            "task": payload.task,
            "document_id": payload.document_id,
            "page_id": payload.page_id,
            "lines": [
                {
                    "line_id": aliases[line.line_id],
                    "ocr_text": line.ocr_text,
                    **(
                        {"hyphenation_role": line.hyphenation_role}
                        if line.hyphenation_role
                        else {}
                    ),
                }
                for line in payload.lines
            ],
        }
        raw, usage = await self._provider.complete_structured_multimodal(
            api_key=self._api_key,
            model=self._model,
            system_prompt=self._system_prompt,
            user_payload=user_payload,
            images=[
                ImagePart(
                    line_id="strip",
                    media_type=strip.media_type,
                    data=strip.data,
                    sha256=strip.sha256,
                )
            ],
            json_schema=self._output_schema,
            temperature=options.temperature,
        )
        ops = edit_ops_from_response(
            _unalias_response(raw, {alias: lid for lid, alias in aliases.items()}),
            source_by_id={ln.line_id: ln.ocr_text for ln in payload.lines},
        )
        return EditScript(ops=ops), usage


def _unalias_response(raw: object, id_by_alias: Mapping[str, str]) -> object:
    """The reply with painted aliases mapped back to real line ids.

    An entry under an alias this chunk never painted is dropped rather than
    guessed: the validator then reports its line missing and the retry
    machinery takes over, which is the documented path for a malformed
    reply. The alias is matched case-insensitively, because a model reading
    a painted label back sometimes lowercases it and nothing else changes.
    """
    if not isinstance(raw, dict):
        return raw
    lines = raw.get("lines")
    if not isinstance(lines, list):
        return raw
    folded = {alias.upper(): line_id for alias, line_id in id_by_alias.items()}
    kept: list[object] = []
    for entry in lines:
        if not isinstance(entry, dict):
            continue
        alias = entry.get("line_id")
        line_id = folded.get(alias.strip().upper()) if isinstance(alias, str) else None
        if line_id is None:
            continue
        kept.append({**entry, "line_id": line_id})
    return {**raw, "lines": kept}


# ---------------------------------------------------------------------------
# PageVisionEditProducer — the whole page as ONE image, identity in the text
# ---------------------------------------------------------------------------


PAGE_VISION_SYSTEM_PROMPT = """\
Tu es un moteur de correction post-OCR spécialisé dans les documents patrimoniaux.
L'IMAGE montre la PAGE ENTIÈRE. Le JSON donne les lignes de cette page dans l'ordre
de lecture, chacune avec son identifiant et son texte OCR. Repère chaque ligne dans
l'image d'après son texte OCR et sa position, puis corrige-la d'après l'image.

Règles absolues :
1. Corrige uniquement les erreurs manifestes d'OCR, d'après l'image.
2. Conserve la langue source.
3. Conserve l'orthographe historique quand elle est réellement présente à l'image \
(ſ long, u pour v, ligatures) : ce n'est pas une erreur.
4. Ne traduis rien.
5. Ne modernise pas volontairement le texte.
6. Ne fusionne jamais deux lignes.
7. Ne scinde jamais une ligne.
8. Ne déplace jamais du texte d'une ligne à l'autre.
9. Chaque entrée line_id doit produire exactement une sortie avec le même line_id, \
recopié tel quel.
10. corrected_text doit contenir une seule ligne, sans caractère de saut de ligne.
11. Retourne uniquement un JSON valide conforme au schéma fourni.
12. En cas de doute ou d'image illisible, conserve le texte OCR (correction minimale).
13. N'invente jamais un caractère absent de l'image (pas d'hallucination visuelle).\
"""


def page_image(
    asset: ImageAsset,
    *,
    max_side: int = 1024,
    source_bytes: bytes | None = None,
    quality: int = 88,
) -> Crop:
    """The whole page, EXIF-normalized and bounded to ``max_side`` pixels.

    JPEG rather than PNG: a page at 1024 px is a photograph-sized image and
    the model reads it, it does not diff it; at quality 88 a page weighs a
    few hundred kilobytes instead of several megabytes. Deterministic in its
    inputs like :func:`crop_region`, so the ``sha256`` is a provenance
    anchor. 1024 is the measured setting: 2048 read no better and less
    stably (2.9–4.6 % against 3.7 %, H10).
    """
    from PIL import Image, ImageOps  # lazy — I4

    raw_bytes = (
        source_bytes if source_bytes is not None else verified_image_bytes(asset)
    )
    with Image.open(io.BytesIO(raw_bytes)) as raw:
        raw.seek(asset.frame_index)
        image = ImageOps.exif_transpose(raw).convert("RGB")
        if max(image.size) > max_side:
            factor = max_side / max(image.size)
            image = image.resize(
                (max(1, int(image.width * factor)), max(1, int(image.height * factor))),
                Image.Resampling.LANCZOS,
            )
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality)
        data = buffer.getvalue()
        box = (0, 0, image.width, image.height)
    return Crop(data=data, media_type="image/jpeg", sha256=_sha256(data), pixel_box=box)


class PageVisionEditProducer:
    """A vision producer that shows the model the WHOLE page, once per call.

    The measured quality lever, and the one no producer gave a path to:
    on OCR17+ (9 pages, human ground truth, `medium`), a crop per line
    reads at 6.4–6.7 %, a labelled strip at 6.25 %, and the page as a
    single image at **3.7–4.6 %** — the model uses the page's typography
    and language around a line to read the line. Identity travels in the
    text under opaque aliases (:func:`line_aliases`): on a clean page the
    model copies them back; a mis-attachment slipping through is what
    ``GuardConfig(attachment_scope="page")`` is for, and this producer
    should be run with it.

    No geometry is needed (nothing is cropped), so ``wants_geometry`` is
    ``False``; one image per call, so no per-call image cap binds and the
    chunk is whatever the planner made — the whole page under the default
    budget. Everything after the reply is the shared LLM-shaped path.
    """

    wants_geometry: bool = False
    wants_image: bool = True
    requires_full_coverage: bool = True

    def __init__(
        self,
        provider: MultimodalStructuredClient,
        api_key: str,
        model: str,
        *,
        system_prompt: str | None = None,
        max_side: int = 1024,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._model = model
        self._max_side = max_side
        self._system_prompt = (
            PAGE_VISION_SYSTEM_PROMPT if system_prompt is None else system_prompt
        )
        self._output_schema = OUTPUT_JSON_SCHEMA
        self.capabilities = ModelCapabilities(
            text=True, vision=True, structured_output=True
        )
        self.metadata = ProducerMetadata(
            name="vision-page",
            implementation=model,
            configuration_fingerprint=prompt_schema_fingerprint(
                self._system_prompt,
                {"output_schema": self._output_schema, "max_side": max_side},
            ),
        )

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]:
        asset = payload.image_ref
        if not isinstance(asset, ImageAsset):
            raise ConfigurationError(
                "PageVisionEditProducer requires a structured ImageAsset page "
                "image (build it with build_image_asset), not a bare ImageRef; "
                f"got {type(asset).__name__}"
            )
        image = page_image(asset, max_side=self._max_side)
        aliases = line_aliases([line.line_id for line in payload.lines])
        user_payload: dict[str, Any] = {
            "task": payload.task,
            "document_id": payload.document_id,
            "page_id": payload.page_id,
            "lines": [
                {
                    "line_id": aliases[line.line_id],
                    "ocr_text": line.ocr_text,
                    **(
                        {"hyphenation_role": line.hyphenation_role}
                        if line.hyphenation_role
                        else {}
                    ),
                }
                for line in payload.lines
            ],
        }
        raw, usage = await self._provider.complete_structured_multimodal(
            api_key=self._api_key,
            model=self._model,
            system_prompt=self._system_prompt,
            user_payload=user_payload,
            images=[
                ImagePart(
                    line_id="page",
                    media_type=image.media_type,
                    data=image.data,
                    sha256=image.sha256,
                )
            ],
            json_schema=self._output_schema,
            temperature=options.temperature,
        )
        ops = edit_ops_from_response(
            _unalias_response(raw, {alias: lid for lid, alias in aliases.items()}),
            source_by_id={ln.line_id: ln.ocr_text for ln in payload.lines},
        )
        return EditScript(ops=ops), usage
