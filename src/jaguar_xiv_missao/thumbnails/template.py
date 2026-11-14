"""Thumbnail sem IA generativa: melhor frame do corte (rosto + fundo limpo) + template xpict."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xpict
from PIL import Image

from ..metadata.formatting import SMALL_WORDS
from ..models import ClipCandidate, ClipMetadata, SourceVideo
from .faces import FaceDetector
from .frames import extract_frame, sample_times
from .layout import Composition, compose, fit_text
from .scoring import FrameScore, score_frame

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1280, 720
DETECT_WIDTH = 640
MAX_BYTES = 2_000_000
"""Limite do YouTube para thumbnails: 2 MB."""
TEXT_MAX_WORDS = 4


@dataclass(frozen=True)
class BestFrame:
    image: Image.Image
    score: FrameScore
    at: float


class FrameSelector:
    """Amostra frames do corte e devolve o de maior nota."""

    def __init__(self, detector: FaceDetector, sample_count: int = 24, min_score: float = 0.2) -> None:
        self._detector = detector
        self._count = sample_count
        self._min_score = min_score

    def best(self, source: Path, start: float, end: float) -> BestFrame | None:
        best: tuple[float, float, FrameScore] | None = None
        for at in sample_times(start, end, self._count):
            small = extract_frame(source, at, DETECT_WIDTH)
            if small is None:
                continue
            score = score_frame(small, self._detector.detect(small))
            logger.debug("frame %.1fs: nota %.2f (rosto %.2f, limpo %.2f)", at, score.total,
                         score.framing, score.clean)
            if best is None or score.total > best[0]:
                best = (score.total, at, score)
        if best is None or best[0] < self._min_score:
            return None
        _, at, score = best
        full = extract_frame(source, at)  # resolução original, só do vencedor
        return BestFrame(full, score, at) if full is not None else None


def thumbnail_text(metadata: ClipMetadata) -> str:
    """Texto curto da thumbnail: o campo da IA, ou o fim do título (onde fica o gatilho)."""
    if metadata.thumbnail_text.strip():
        return metadata.thumbnail_text.strip().upper()
    words = re.sub(r"[!?.…:;,]+", " ", metadata.title).upper().split()
    words = words[-TEXT_MAX_WORDS:]
    while len(words) > 1 and words[0].lower() in SMALL_WORDS:
        words.pop(0)
    return " ".join(words)


def _gradient(comp: Composition) -> Image.Image:
    """Escurece o lado do texto para dar contraste sem esconder o rosto."""
    ys, xs = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    area = comp.text_area
    fade = 220.0  # largura da transição, em px
    if comp.text_side == "bottom":
        alpha = np.clip((ys - (area.y * HEIGHT - fade / 2)) / fade, 0, 1)
    elif comp.text_side == "right":
        alpha = np.clip((xs - (area.x * WIDTH - fade)) / fade, 0, 1)
    else:
        alpha = np.clip(((area.right * WIDTH + fade) - xs) / fade, 0, 1)
    alpha = (alpha ** 1.4 * 0.78 * 255).astype(np.uint8)
    rgba = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    rgba[..., 3] = alpha
    return Image.fromarray(rgba)


class XpictThumbnailGenerator:
    def __init__(
        self,
        selector: FrameSelector,
        font_path: Path,
        accent: str = "#FFD400",
        logo_path: Path | None = None,
        max_zoom: float = 1.6,
    ) -> None:
        self._selector = selector
        self._font_path = font_path
        self._accent = accent
        self._logo = logo_path if logo_path and logo_path.exists() else None
        self._max_zoom = max_zoom
        self._font = xpict.utils.font(name="thumbnail", file_path=str(font_path), color="#ffffff")
        self._template = self._build_template()

    def _build_template(self):
        font = self._font
        return xpict.template(
            config={"width": WIDTH, "height": HEIGHT, "fill": "#000000"},
            layers=[
                xpict.image(src=lambda ctx: ctx.data["frame"], x=0, y=0, width=WIDTH, height=HEIGHT),
                xpict.image(src=lambda ctx: ctx.data["gradient"], x=0, y=0),
                xpict.repeat(
                    each=lambda ctx: ctx.data["lines"],
                    layer=lambda item, info: xpict.text(
                        text=item["text"], x=item["x"], y=item["y"], align=item["align"],
                        baseline="top", font=font(size=item["size"], color=item["color"]),
                        stroke={"width": max(4, round(item["size"] * 0.14)), "fill": "#000000"},
                    ),
                ),
                xpict.image(
                    src=lambda ctx: ctx.data["logo"], x=lambda ctx: ctx.data["logo_x"], y=24,
                    width=110, when=lambda ctx: ctx.data["logo"] is not None,
                ),
            ],
        )

    def generate(
        self, video: SourceVideo, candidate: ClipCandidate, metadata: ClipMetadata, out: Path,
        source_file: Path,
    ) -> Path | None:
        best = self._selector.best(source_file, candidate.start, candidate.end)
        if best is None:
            logger.warning("Nenhum frame com rosto bem enquadrado em %s; sem thumbnail", video.id)
            return None
        logger.info("Thumbnail de %s: frame em %.1fs (nota %.2f)", video.id, best.at, best.score.total)
        image = self._render(best, thumbnail_text(metadata))
        out.parent.mkdir(parents=True, exist_ok=True)
        _save_jpeg(image, out)
        return out

    def _render(self, best: BestFrame, text: str) -> Image.Image:
        frame = best.image
        comp = compose(list(best.score.faces), frame.width, frame.height, self._max_zoom)
        c = comp.crop
        cropped = frame.crop((round(c.x), round(c.y), round(c.x + c.w), round(c.y + c.h)))
        data = {
            "frame": cropped.resize((WIDTH, HEIGHT), Image.LANCZOS),
            "gradient": _gradient(comp),
            "lines": self._text_lines(comp, text),
            "logo": Image.open(self._logo).convert("RGBA") if self._logo else None,
            "logo_x": 24 if comp.text_side != "left" else WIDTH - 110 - 24,
        }
        return self._template.render(data).convert("RGB")

    def _text_lines(self, comp: Composition, text: str) -> list[dict]:
        a = comp.text_area
        block = fit_text(text, self._font_path, round(a.w * WIDTH), round(a.h * HEIGHT))
        if block is None:
            return []
        centered = comp.text_side == "bottom"
        x = round((a.x + a.w / 2) * WIDTH) if centered else round(a.x * WIDTH)
        top = round(a.y * HEIGHT + (a.h * HEIGHT - block.height) / 2)
        last = len(block.lines) - 1
        return [
            {
                "text": line, "x": x, "y": top + i * block.line_height, "size": block.size,
                "align": "center" if centered else "left",
                "color": self._accent if i == last else "#ffffff",
            }
            for i, line in enumerate(block.lines)
        ]


def _save_jpeg(image: Image.Image, out: Path) -> None:
    for quality in (92, 85, 78, 70):
        image.save(out, "JPEG", quality=quality, optimize=True)
        if out.stat().st_size <= MAX_BYTES:
            return
