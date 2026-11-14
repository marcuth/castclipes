"""Thumbnails: ponto de extensão. Provedor/prompt ainda em aberto (ver IDEIA.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..config import Settings
from ..models import ClipCandidate, ClipMetadata, SourceVideo


class ThumbnailGenerator(Protocol):
    def generate(
        self, video: SourceVideo, candidate: ClipCandidate, metadata: ClipMetadata, out: Path
    ) -> Path | None: ...


class NullThumbnailGenerator:
    def generate(
        self, video: SourceVideo, candidate: ClipCandidate, metadata: ClipMetadata, out: Path
    ) -> Path | None:
        return None


def create_thumbnail_generator(settings: Settings) -> ThumbnailGenerator:
    return NullThumbnailGenerator()
