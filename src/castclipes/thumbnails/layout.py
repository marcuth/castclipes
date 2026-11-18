"""Composição: onde cortar o frame (zoom nos rostos) e em que área cabe o texto."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import ImageFont

from .faces import FaceBox

ASPECT = 16 / 9
TEXT_SIDE_MIN_FREE = 0.36
"""Fração mínima da largura livre ao lado dos rostos para o texto ir de lado."""


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass(frozen=True)
class Composition:
    crop: Rect
    """Recorte em pixels do frame original, sempre 16:9."""
    text_area: Rect
    """Área do texto em fração (0 a 1) da thumbnail final."""
    text_side: Literal["left", "right", "bottom"]
    group: Rect
    """Caixa que envolve os rostos, em fração da thumbnail final."""


def _union(faces: list[FaceBox]) -> Rect:
    x0, y0 = min(f.x for f in faces), min(f.y for f in faces)
    x1, y1 = max(f.x + f.w for f in faces), max(f.y + f.h for f in faces)
    return Rect(x0, y0, x1 - x0, y1 - y0)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compose(
    faces: list[FaceBox], frame_w: int, frame_h: int, max_zoom: float = 1.6
) -> Composition:
    """Calcula recorte e área de texto. `faces` em fração do frame original (não vazio)."""
    group = _union(faces)
    # maior recorte 16:9 que cabe no frame
    base_w, base_h = (frame_h * ASPECT, float(frame_h)) if frame_w / frame_h > ASPECT else (
        float(frame_w), frame_w / ASPECT
    )
    base_w_frac, base_h_frac = base_w / frame_w, base_h / frame_h

    two_faces = len(faces) > 1
    target_h = 0.42 if two_faces else 0.52
    # fração do rosto *dentro do recorte base*; o zoom o aproxima do alvo sem ultrapassar a largura
    group_h_in_base = group.h / base_h_frac
    group_w_in_base = group.w / base_w_frac
    zoom = _clamp(min(target_h / group_h_in_base, 0.8 / group_w_in_base), 1.0, max_zoom)
    crop_w, crop_h = base_w / zoom, base_h / zoom

    gcx, gcy = (group.x + group.w / 2) * frame_w, (group.y + group.h / 2) * frame_h
    # um rosto vai para um terço lateral (texto do outro lado); dois ficam ao centro
    anchor_x = 0.5 if two_faces else (0.30 if group.x + group.w / 2 < 0.5 else 0.70)
    anchor_y = 0.40 if two_faces else 0.48
    crop_x = _clamp(gcx - anchor_x * crop_w, 0, frame_w - crop_w)
    crop_y = _clamp(gcy - anchor_y * crop_h, 0, frame_h - crop_h)

    g = Rect(
        (group.x * frame_w - crop_x) / crop_w,
        (group.y * frame_h - crop_y) / crop_h,
        group.w * frame_w / crop_w,
        group.h * frame_h / crop_h,
    )
    free_left, free_right = g.x, 1.0 - g.right
    side: Literal["left", "right", "bottom"]
    if not two_faces and max(free_left, free_right) >= TEXT_SIDE_MIN_FREE:
        if free_right >= free_left:
            side, area = "right", Rect(g.right + 0.03, 0.12, 0.97 - g.right - 0.03, 0.70)
        else:
            side, area = "left", Rect(0.03, 0.12, g.x - 0.06, 0.70)
    else:
        top = min(g.bottom + 0.03, 0.68)
        side, area = "bottom", Rect(0.04, top, 0.92, 0.95 - top)
    return Composition(Rect(crop_x, crop_y, crop_w, crop_h), area, side, g)


@dataclass(frozen=True)
class TextBlock:
    lines: tuple[str, ...]
    size: int
    line_height: int
    width: int
    height: int


def fit_text(
    text: str, font_path: Path, area_w: int, area_h: int, max_size: int = 170, max_lines: int = 3
) -> TextBlock | None:
    """Maior fonte que faz o texto caber na área, quebrando em até `max_lines` linhas."""
    words = text.split()
    if not words:
        return None
    for size in range(max_size, 23, -4):
        font = ImageFont.truetype(str(font_path), size)
        lines = _wrap(words, font, area_w)
        if lines is None or len(lines) > max_lines:
            continue
        line_height = round(size * 1.08)
        height = line_height * len(lines)
        if height <= area_h:
            width = max(round(font.getlength(line)) for line in lines)
            return TextBlock(tuple(lines), size, line_height, width, height)
    return None


def _wrap(words: list[str], font: ImageFont.FreeTypeFont, max_width: int) -> list[str] | None:
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.getlength(candidate) <= max_width:
            current = candidate
        elif current:
            lines.append(current)
            current = word
            if font.getlength(word) > max_width:
                return None
        else:
            return None
    lines.append(current)
    return lines
