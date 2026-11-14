"""Overlay opcional (marca d'água / moldura em PNG)."""

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


def overlay_size(
    fit: str, base: tuple[int, int], item: tuple[int, int], width_pct: float
) -> tuple[int, int]:
    """`stretch`: tamanho do vídeo (moldura). `width`: largura = pct do vídeo, aspecto mantido."""
    if fit == "stretch":
        return base
    width = max(1, int(base[0] * width_pct))
    return width, max(1, round(item[1] * width / item[0]))


class Overlay(Protocol):
    def layer(self, base: Any) -> Any:
        """Devolve um clip moviepy posicionado para ser composto sobre `base`."""


class ImageOverlay:
    def __init__(
        self, path: Path, position: str, width_pct: float, opacity: float, margin: int,
        fit: str = "width",
    ) -> None:
        self._path = path
        self._position = position
        self._width_pct = width_pct
        self._opacity = opacity
        self._margin = margin
        self._fit = fit

    def layer(self, base: Any) -> Any:
        from moviepy import ImageClip

        clip = ImageClip(str(self._path))
        size = overlay_size(self._fit, (base.w, base.h), (clip.w, clip.h), self._width_pct)
        clip = clip.resized(size)
        if self._fit == "stretch":
            x, y = 0, 0
        else:
            x, y = compute_position(
                self._position, (base.w, base.h), (clip.w, clip.h), self._margin
            )
        return clip.with_duration(base.duration).with_opacity(self._opacity).with_position((x, y))


def create_overlays(settings: Settings) -> list[Overlay]:
    """Simple Factory: monta os overlays habilitados no .env, na ordem de empilhamento."""
    overlays: list[Overlay] = []
    if settings.watermark_path:
        overlays.append(
            ImageOverlay(
                settings.watermark_path, settings.watermark_position, settings.watermark_width_pct,
                settings.watermark_opacity, settings.watermark_margin_px, settings.watermark_fit,
            )
        )
    return overlays
