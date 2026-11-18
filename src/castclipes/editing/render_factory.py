"""Simple Factories dos renderers: corte longo (ffmpeg ou moviepy) e short (9:16)."""

from __future__ import annotations

from ..config import Settings
from ..models import ClipFormat
from .ffmpeg_renderer import FfmpegRenderer
from .overlay import create_overlays
from .renderer import ClipRenderer, Renderer
from .vertical_renderer import FfmpegVerticalRenderer, ShortRenderer


def create_renderer(settings: Settings) -> Renderer:
    """Renderer dos cortes longos (16:9)."""
    args = (
        create_overlays(settings, ClipFormat.LONG), settings.outro_path, settings.cta_video_path,
        settings.render_fps, settings.render_preset, settings.render_crf, settings.render_threads,
    )
    if settings.render_engine == "moviepy":
        return ClipRenderer(*args)
    return FfmpegRenderer(*args)


def create_short_renderer(settings: Settings) -> ShortRenderer:
    return FfmpegVerticalRenderer(settings, create_overlays(settings, ClipFormat.SHORT))
