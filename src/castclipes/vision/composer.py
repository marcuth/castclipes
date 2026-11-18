"""Compõe um quadro vertical (9:16) a partir de um quadro horizontal e do plano de enquadramento.

Dois layouts, como no podcast-clipper: um bloco único seguindo quem fala (com zoom quando a
pessoa está longe) ou split-screen com dois blocos empilhados.
"""

from __future__ import annotations

import cv2
import numpy as np

from .tracking import FramingPlan

DIVIDER_PX = 4
DIVIDER_COLOR = (35, 24, 20)  # BGR
FACE_Y_SINGLE = 0.35  # onde o rosto fica na altura do recorte (bloco único com zoom)
FACE_Y_SPLIT = 0.40


def crop_box(
    cx: float, cy: float, box_w: int, box_h: int, bounds: tuple[float, float], height: int,
    face_y: float,
) -> tuple[int, int]:
    """Canto superior esquerdo de um recorte box_w x box_h com o rosto a `face_y` da altura,
    mantido dentro de `bounds` (o painel da câmera) para nunca mostrar a emenda de layouts."""
    x0, x1 = round(bounds[0]), round(bounds[1])
    x = int(max(x0, min(cx - box_w / 2, x1 - box_w)))
    y = int(max(0, min(cy - box_h * face_y, height - box_h)))
    return x, y


def split_ranges(
    is_split, duration: float, step: float = 0.1
) -> list[tuple[float, float]]:
    """Intervalos (em segundos do corte) em que o split-screen aparece; `is_split(t)` é um predicado."""
    ranges: list[tuple[float, float]] = []
    range_start: float | None = None
    for index in range(int(duration / step) + 1):
        t = min(duration, index * step)
        if is_split(t):
            if range_start is None:
                range_start = t
        elif range_start is not None:
            ranges.append((range_start, t))
            range_start = None
    if range_start is not None:
        ranges.append((range_start, duration))
    return ranges


class VerticalComposer:
    """Transforma quadros do arquivo-fonte (tempo absoluto) em quadros `out_w x out_h`."""

    def __init__(
        self, plan: FramingPlan, frame_size: tuple[int, int], out_size: tuple[int, int],
        split: bool,
    ) -> None:
        self._plan = plan
        self._w, self._h = frame_size
        self.out_w, self.out_h = out_size
        self._split = split
        # o plano foi medido no arquivo-fonte; reescala se o decodificador reportar outro tamanho
        self._sx = self._w / plan.width if plan.width else 1.0
        self._sy = self._h / plan.height if plan.height else 1.0
        self._ratio = self.out_w / self.out_h

    def is_split_at(self, t: float) -> bool:
        return self._split and self._plan.split_at(t) is not None

    def compose(self, img: np.ndarray, t: float) -> np.ndarray:
        split = self._plan.split_at(t) if self._split else None
        return self._compose_split(img, split) if split is not None else self._compose_single(img, t)

    def _compose_single(self, img: np.ndarray, t: float) -> np.ndarray:
        frame = self._plan.single_at(t)
        bounds = (frame.bounds[0] * self._sx, frame.bounds[1] * self._sx)
        box_h = int(min(self._h, frame.crop_h * self._sy, (bounds[1] - bounds[0]) / self._ratio))
        box_w = int(box_h * self._ratio)
        if box_h >= self._h - 2:  # sem zoom: altura inteira, só acompanha na horizontal
            box_w = min(int(self._h * self._ratio), self._w)
            x, _ = crop_box(frame.cx * self._sx, 0, box_w, self._h, bounds, self._h, 0.0)
            crop = img[0:self._h, x:x + box_w]
        else:
            x, y = crop_box(frame.cx * self._sx, frame.cy * self._sy, box_w, box_h, bounds,
                            self._h, FACE_Y_SINGLE)
            crop = img[y:y + box_h, x:x + box_w]
        return cv2.resize(crop, (self.out_w, self.out_h), interpolation=cv2.INTER_CUBIC)

    def _compose_split(self, img: np.ndarray, split) -> np.ndarray:
        half_h = self.out_h // 2
        ratio_half = self.out_w / half_h
        top_bounds = (split.top_bounds[0] * self._sx, split.top_bounds[1] * self._sx)
        bottom_bounds = (split.bottom_bounds[0] * self._sx, split.bottom_bounds[1] * self._sx)
        max_w = int(min(top_bounds[1] - top_bounds[0], bottom_bounds[1] - bottom_bounds[0]))
        box_h = int(min(self._h, split.box_h * self._sy))
        box_w = int(box_h * ratio_half)
        if box_w > max_w:
            box_w = max_w
            box_h = int(box_w / ratio_half)
        # bloco de cima: pessoa da esquerda; de baixo: a da direita
        x1, y1 = crop_box(split.top[0] * self._sx, split.top[1] * self._sy, box_w, box_h,
                          top_bounds, self._h, FACE_Y_SPLIT)
        x2, y2 = crop_box(split.bottom[0] * self._sx, split.bottom[1] * self._sy, box_w, box_h,
                          bottom_bounds, self._h, FACE_Y_SPLIT)
        h1 = half_h - DIVIDER_PX // 2
        h2 = self.out_h - h1 - DIVIDER_PX
        top = cv2.resize(img[y1:y1 + box_h, x1:x1 + box_w], (self.out_w, h1),
                         interpolation=cv2.INTER_LINEAR)
        bottom = cv2.resize(img[y2:y2 + box_h, x2:x2 + box_w], (self.out_w, h2),
                            interpolation=cv2.INTER_LINEAR)
        divider = np.full((DIVIDER_PX, self.out_w, 3), DIVIDER_COLOR, dtype=np.uint8)
        return np.vstack([top, divider, bottom])
