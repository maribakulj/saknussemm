"""The path and immutable bytes of one source at the start of a run."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    raw: bytes
