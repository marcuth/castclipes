"""Thumbnails: Strategy (`ThumbnailGenerator`) + factory."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..config import Settings
from ..models import ClipCandidate, ClipMetadata, SourceVideo

BUNDLED_FONT = Path(__file__).parent / "assets" / "fonts" / "Anton-Regular.ttf"


class ThumbnailGenerator(Protocol):
    def generate(
        self, video: SourceVideo, candidate: ClipCandidate, metadata: ClipMetadata, out: Path,
        source_file: Path,
    ) -> Path | None:
        """`source_file` é o vídeo completo; `candidate.start/end` são tempos absolutos nele."""
        ...


class NullThumbnailGenerator:
    def generate(
        self, video: SourceVideo, candidate: ClipCandidate, metadata: ClipMetadata, out: Path,
        source_file: Path,
    ) -> Path | None:
        return None


def create_thumbnail_generator(settings: Settings) -> ThumbnailGenerator:
    if settings.thumbnail_provider == "none":
        return NullThumbnailGenerator()
    # imports tardios: mediapipe/xpict só são carregados quando o recurso está ligado
    from .faces import MediaPipeFaceDetector
    from .template import FrameSelector, XpictThumbnailGenerator

    detector = MediaPipeFaceDetector(
        settings.face_model_path, settings.thumbnail_face_min_confidence
    )
    return XpictThumbnailGenerator(
        FrameSelector(detector, settings.thumbnail_sample_count),
        settings.thumbnail_font_path or BUNDLED_FONT,
        settings.thumbnail_accent_color,
        settings.thumbnail_logo_path,
        settings.thumbnail_max_zoom,
    )
