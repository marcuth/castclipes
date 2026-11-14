"""Detecção de rostos com o BlazeFace do Google (MediaPipe Tasks, modelo `short_range`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
)


@dataclass(frozen=True)
class FaceBox:
    """Caixa do rosto normalizada (0 a 1) em relação à imagem."""

    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h


class FaceDetector(Protocol):
    def detect(self, image: Image.Image) -> list[FaceBox]: ...


def ensure_model(path: Path) -> Path:
    """Baixa o modelo (~230 KB) na primeira execução."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Baixando modelo de detecção de rosto para %s", path)
    response = httpx.get(MODEL_URL, follow_redirects=True, timeout=60)
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


class MediaPipeFaceDetector:
    def __init__(self, model_path: Path, min_confidence: float = 0.6) -> None:
        self._model_path = model_path
        self._min_confidence = min_confidence
        self._detector = None

    def _load(self):
        if self._detector is None:
            from mediapipe.tasks.python import BaseOptions, vision

            options = vision.FaceDetectorOptions(
                base_options=BaseOptions(model_asset_path=str(ensure_model(self._model_path))),
                min_detection_confidence=self._min_confidence,
            )
            self._detector = vision.FaceDetector.create_from_options(options)
        return self._detector

    def detect(self, image: Image.Image) -> list[FaceBox]:
        import mediapipe as mp

        rgb = np.ascontiguousarray(np.asarray(image.convert("RGB")))
        height, width = rgb.shape[:2]
        result = self._load().detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        boxes: list[FaceBox] = []
        for det in result.detections:
            box = det.bounding_box
            score = det.categories[0].score if det.categories else 0.0
            boxes.append(
                FaceBox(box.origin_x / width, box.origin_y / height, box.width / width,
                        box.height / height, float(score))
            )
        return sorted(boxes, key=lambda b: b.area, reverse=True)
