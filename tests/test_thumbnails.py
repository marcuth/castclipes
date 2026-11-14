from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from jaguar_xiv_missao.models import ClipCandidate, ClipMetadata
from jaguar_xiv_missao.thumbnails import template
from jaguar_xiv_missao.thumbnails.base import BUNDLED_FONT, NullThumbnailGenerator
from jaguar_xiv_missao.thumbnails.faces import FaceBox
from jaguar_xiv_missao.thumbnails.frames import sample_times
from jaguar_xiv_missao.thumbnails.layout import compose, fit_text
from jaguar_xiv_missao.thumbnails.scoring import score_frame, usable_faces
from jaguar_xiv_missao.thumbnails.template import (
    BestFrame,
    FrameSelector,
    XpictThumbnailGenerator,
    thumbnail_text,
)

FACE = FaceBox(0.30, 0.23, 0.15, 0.37, 0.9)


def flat_frame() -> Image.Image:
    return Image.new("RGB", (640, 360), (40, 60, 90))


def noisy_frame() -> Image.Image:
    rng = np.random.default_rng(1)
    return Image.fromarray(rng.integers(0, 255, (360, 640, 3), dtype=np.uint8))


def test_sample_times_spread_inside_clip():
    times = sample_times(100, 200, 5)
    assert len(times) == 5
    assert times[0] > 100 and times[-1] < 200
    assert times == sorted(times)
    assert sample_times(0, 0, 3) == []


def test_usable_faces_drops_tiny_background_faces():
    big = FaceBox(0.3, 0.2, 0.2, 0.4, 0.9)
    tiny = FaceBox(0.8, 0.1, 0.03, 0.06, 0.9)
    assert usable_faces([tiny, big]) == [big]
    assert usable_faces([]) == []


def test_no_face_means_zero_score():
    assert score_frame(flat_frame(), []).total == 0


def test_clean_background_beats_cluttered_one():
    clean = score_frame(flat_frame(), [FACE])
    cluttered = score_frame(noisy_frame(), [FACE])
    assert clean.clean > cluttered.clean
    assert clean.total > cluttered.total


def test_cropped_face_scores_lower_than_framed_face():
    cut = FaceBox(0.30, -0.05, 0.15, 0.37, 0.9)
    assert score_frame(flat_frame(), [FACE]).framing > score_frame(flat_frame(), [cut]).framing


def test_compose_single_face_puts_text_on_opposite_side():
    left = compose([FaceBox(0.2, 0.25, 0.12, 0.3, 0.9)], 1920, 1080)
    right = compose([FaceBox(0.7, 0.25, 0.12, 0.3, 0.9)], 1920, 1080)
    assert left.text_side == "right" and right.text_side == "left"
    for comp in (left, right):
        assert abs(comp.crop.w / comp.crop.h - 16 / 9) < 0.01
        assert comp.crop.x >= 0 and comp.crop.right <= 1920 + 0.01
        assert comp.crop.y >= 0 and comp.crop.bottom <= 1080 + 0.01


def test_compose_two_faces_puts_text_at_bottom():
    comp = compose([FaceBox(0.2, 0.25, 0.12, 0.3, 0.9), FaceBox(0.6, 0.25, 0.12, 0.3, 0.9)],
                   1920, 1080)
    assert comp.text_side == "bottom"


def test_fit_text_respects_area_and_line_limit():
    block = fit_text("VÍDEO BIZARRO DEMAIS", BUNDLED_FONT, 500, 400)
    assert block is not None
    assert block.width <= 500 and block.height <= 400 and len(block.lines) <= 3
    assert fit_text("", BUNDLED_FONT, 500, 400) is None
    assert fit_text("PALAVRAGIGANTESCADEMAIS " * 5, BUNDLED_FONT, 40, 40) is None


def test_thumbnail_text_prefers_ai_then_title_tail():
    with_ai = ClipMetadata("T", "d", (), thumbnail_text="surto ao vivo")
    assert thumbnail_text(with_ai) == "SURTO AO VIVO"
    derived = ClipMetadata("ARTHUR do VAL REAGE a VÍDEO BIZARRO!", "d", ())
    assert thumbnail_text(derived) == "REAGE A VÍDEO BIZARRO"


class FakeDetector:
    def __init__(self, faces):
        self._faces = faces

    def detect(self, image):
        return self._faces


def test_selector_picks_best_frame_and_rejects_faceless(monkeypatch):
    calls = []

    def fake_extract(source, at, width=None):
        calls.append((at, width))
        return flat_frame() if width else Image.new("RGB", (1920, 1080), (40, 60, 90))

    monkeypatch.setattr(template, "extract_frame", fake_extract)
    best = FrameSelector(FakeDetector([FACE]), sample_count=4).best(Path("x.mp4"), 0, 100)
    assert best is not None and best.image.size == (1920, 1080)
    assert calls[-1][1] is None  # só o vencedor é extraído em resolução original
    assert FrameSelector(FakeDetector([]), sample_count=4).best(Path("x.mp4"), 0, 100) is None


def test_generator_writes_jpeg_under_limit(tmp_path):
    gen = XpictThumbnailGenerator(None, BUNDLED_FONT)
    best = BestFrame(Image.new("RGB", (1920, 1080), (40, 60, 90)),
                     score_frame(flat_frame(), [FACE]), 5.0)
    image = gen._render(best, "VÍDEO BIZARRO DEMAIS")
    assert image.size == (1280, 720)
    out = tmp_path / "t.jpg"
    template._save_jpeg(image, out)
    assert 0 < out.stat().st_size <= template.MAX_BYTES


def test_generate_returns_none_without_good_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(template, "extract_frame", lambda *a, **k: flat_frame())
    gen = XpictThumbnailGenerator(FrameSelector(FakeDetector([]), 3), BUNDLED_FONT)
    cand = ClipCandidate(0, 60, "t", 0.9)
    out = gen.generate(SimpleNamespace(id="v"), cand, ClipMetadata("T", "d", ()), tmp_path / "t.jpg", Path("x.mp4"))
    assert out is None and not (tmp_path / "t.jpg").exists()


def test_null_generator_accepts_source_file(tmp_path):
    cand = ClipCandidate(0, 60, "t", 0.9)
    assert NullThumbnailGenerator().generate(
        None, cand, ClipMetadata("T", "d", ()), tmp_path / "t.jpg", Path("x.mp4")
    ) is None
