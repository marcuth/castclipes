"""Nota de cada frame candidato: rosto bem enquadrado, pouca poluição visual, nitidez.

Funções puras (numpy + Pillow); a detecção de rosto vem de fora. Os limiares são pontos de
partida e podem precisar de ajuste com frames reais das lives.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from .faces import FaceBox

ANALYSIS_WIDTH = 320
MIN_FACE_HEIGHT = 0.12
"""Rosto menor que isso (fração da altura do frame) é público ao fundo, não o falante."""
IDEAL_FACE_HEIGHT = 0.26
MAX_FACE_HEIGHT = 0.60
EDGE_THRESHOLD = 28.0
"""Gradiente (0-255) a partir do qual um pixel conta como borda."""
CLUTTER_SATURATION = 0.18
"""Densidade de bordas em que a nota de limpeza chega a zero."""
SHARPNESS_REFERENCE = 120.0
FACE_PADDING = 0.35
"""Quanto cada rosto é expandido (proporção do tamanho) ao ser excluído da medida de poluição."""


@dataclass(frozen=True)
class FrameScore:
    total: float
    framing: float
    clean: float
    sharp: float
    faces: tuple[FaceBox, ...]


def usable_faces(faces: list[FaceBox], max_faces: int = 2) -> list[FaceBox]:
    """Só os rostos principais: grandes o bastante e comparáveis ao maior."""
    if not faces:
        return []
    biggest = max(f.h for f in faces)
    kept = [f for f in faces if f.h >= MIN_FACE_HEIGHT and f.h >= biggest * 0.5]
    return sorted(kept, key=lambda f: f.area, reverse=True)[:max_faces]


def _gray(image: Image.Image) -> np.ndarray:
    small = image.convert("L")
    if small.width > ANALYSIS_WIDTH:
        height = max(1, round(small.height * ANALYSIS_WIDTH / small.width))
        small = small.resize((ANALYSIS_WIDTH, height), Image.BILINEAR)
    return np.asarray(small, dtype=np.float32)


def _gradient(gray: np.ndarray) -> np.ndarray:
    gx = np.abs(np.diff(gray, axis=1))[:-1, :]
    gy = np.abs(np.diff(gray, axis=0))[:, :-1]
    return np.hypot(gx, gy)


def _mask_outside(shape: tuple[int, int], faces: list[FaceBox]) -> np.ndarray:
    """True onde NÃO é rosto (rosto + folga ficam de fora da conta de poluição)."""
    h, w = shape
    mask = np.ones((h, w), dtype=bool)
    for f in faces:
        pad_x, pad_y = f.w * FACE_PADDING, f.h * FACE_PADDING
        x0, x1 = int(max(0.0, f.x - pad_x) * w), int(min(1.0, f.x + f.w + pad_x) * w)
        y0, y1 = int(max(0.0, f.y - pad_y) * h), int(min(1.0, f.y + f.h + pad_y) * h)
        mask[y0:y1, x0:x1] = False
    return mask


def clutter_density(image: Image.Image, faces: list[FaceBox]) -> float:
    """Fração de pixels de borda fora dos rostos (0 = fundo liso, alto = muita poluição)."""
    grad = _gradient(_gray(image))
    mask = _mask_outside(grad.shape, faces)
    if not mask.any():
        return 0.0
    return float((grad[mask] > EDGE_THRESHOLD).mean())


def sharpness(image: Image.Image, faces: list[FaceBox]) -> float:
    """Variância do laplaciano na região do rosto principal (ou do frame, sem rosto)."""
    gray = _gray(image)
    if faces:
        f = faces[0]
        h, w = gray.shape
        region = gray[int(f.y * h): int((f.y + f.h) * h) + 1, int(f.x * w): int((f.x + f.w) * w) + 1]
        if region.shape[0] >= 3 and region.shape[1] >= 3:
            gray = region
    lap = (
        -4 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    )
    return float(lap.var())


def framing_score(faces: list[FaceBox]) -> float:
    """0 sem rosto; sobe com rosto grande, inteiro dentro do frame e detectado com confiança."""
    if not faces:
        return 0.0
    biggest = faces[0]
    size = min(1.0, biggest.h / IDEAL_FACE_HEIGHT)
    if biggest.h > MAX_FACE_HEIGHT:
        size *= MAX_FACE_HEIGHT / biggest.h
    inside = all(
        f.x >= 0.01 and f.y >= 0.01 and f.x + f.w <= 0.99 and f.y + f.h <= 0.99 for f in faces
    )
    eyes_high = all(f.cy <= 0.65 for f in faces)
    placement = (1.0 if inside else 0.3) * (1.0 if eyes_high else 0.6)
    confidence = sum(f.score for f in faces) / len(faces)
    return size * placement * confidence


def score_frame(image: Image.Image, faces: list[FaceBox]) -> FrameScore:
    main = usable_faces(faces)
    framing = framing_score(main)
    density = clutter_density(image, main)
    clean = max(0.0, 1.0 - density / CLUTTER_SATURATION)
    sharp = min(1.0, sharpness(image, main) / SHARPNESS_REFERENCE)
    luma = float(np.asarray(image.convert("L"), dtype=np.float32).mean())
    exposure = 1.0 if 45 <= luma <= 215 else 0.4
    total = 0.0 if framing == 0 else (0.45 * framing + 0.35 * clean + 0.20 * sharp) * exposure
    return FrameScore(total, framing, clean, sharp, tuple(main))
