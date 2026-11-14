"""Overlays opcionais (marca d'água, QR/CTA em PNG)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..config import Settings


def compute_position(
    position: str, container: tuple[int, int], item: tuple[int, int], margin: int
) -> tuple[int, int]:
    cw, ch = container
    iw, ih = item
    horizontal = {"left": margin, "right": cw - iw - margin, "center": (cw - iw) // 2}
    vertical = {"top": margin, "bottom": ch - ih - margin, "center": (ch - ih) // 2}
    if position == "center":
        return horizontal["center"], vertical["center"]
    vert, _, horiz = position.partition("-")
    return horizontal[horiz], vertical[vert]


class Overlay(Protocol):
    def layer(self, base: Any) -> Any:
        """Devolve um clip moviepy posicionado para ser composto sobre `base`."""


class ImageOverlay:
    def __init__(
        self, path: Path, position: str, width_pct: float, opacity: float, margin: int
    ) -> None:
        self._path = path
        self._position = position
        self._width_pct = width_pct
        self._opacity = opacity
        self._margin = margin

    def layer(self, base: Any) -> Any:
        from moviepy import ImageClip

        clip = ImageClip(str(self._path)).resized(width=max(1, int(base.w * self._width_pct)))
        x, y = compute_position(self._position, (base.w, base.h), (clip.w, clip.h), self._margin)
        return clip.with_duration(base.duration).with_opacity(self._opacity).with_position((x, y))


def create_overlays(settings: Settings) -> list[Overlay]:
    """Simple Factory: monta os overlays habilitados no .env, na ordem de empilhamento."""
    overlays: list[Overlay] = []
    if settings.watermark_path:
        overlays.append(
            ImageOverlay(
                settings.watermark_path, settings.watermark_position, settings.watermark_width_pct,
                settings.watermark_opacity, settings.watermark_margin_px,
            )
        )
    if settings.cta_path:
        overlays.append(
            ImageOverlay(
                settings.cta_path, settings.cta_position, settings.cta_width_pct,
                settings.cta_opacity, settings.cta_margin_px,
            )
        )
    return overlays
