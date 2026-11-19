"""Shorts: palavras das legendas, tempo por palavra, composição vertical e render de ponta a ponta."""

import itertools
import random
import subprocess

import numpy as np
import pytest
from PIL import Image

from castclipes.captions import remotion as captions_remotion
from castclipes.captions.remotion import CaptionError, normalize_words
from castclipes.captions.words import (
    FallbackWordAligner,
    TranscriptWordAligner,
    words_from_transcript,
)
from castclipes.config import Settings
from castclipes.editing import vertical_renderer
from castclipes.editing.ffmpeg_renderer import probe
from castclipes.editing.overlay import ImageOverlay
from castclipes.editing.silence import ffmpeg_exe
from castclipes.editing.vertical_renderer import FfmpegVerticalRenderer, read_frames
from castclipes.models import ClipCandidate, Transcript, TranscriptSegment, Word
from castclipes.vision.composer import VerticalComposer, crop_box, split_ranges
from castclipes.vision.tracking import FramingPlan, SingleFrame, SplitFrame


def _ffmpeg_works() -> bool:
    try:
        return subprocess.run([ffmpeg_exe(), "-version"], capture_output=True, check=False).returncode == 0
    except OSError:
        return False


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_works(), reason="ffmpeg indisponível")


# ---------- legendas ----------
def test_normalize_words_fixes_overlaps_and_empty():
    words = [Word(1.0, 3.0, "b"), Word(0.0, 1.5, "a"), Word(2.0, 2.0, "  ")]
    fixed = normalize_words(words)
    assert [w.text for w in fixed] == ["a", "b"]
    assert fixed[0].end <= fixed[1].start


def test_remotion_without_node_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(captions_remotion.shutil, "which", lambda name: None)
    with pytest.raises(CaptionError):
        captions_remotion.render_remotion_captions([Word(0, 0.5, "a")], 1.0, tmp_path / "c.webm")
    assert captions_remotion.render_remotion_captions([], 1.0, tmp_path / "c.webm") is None


# ---------- tempo por palavra ----------
def _transcript():
    return Transcript(
        [
            TranscriptSegment(100.0, 104.0, "uma frase de quatro"),
            TranscriptSegment(104.0, 106.0, "exato", words=(Word(104.1, 105.0, "exato"),)),
            TranscriptSegment(300.0, 305.0, "fora do corte"),
        ],
        "youtube",
    )


def test_words_from_transcript_interpolates_and_uses_real_words():
    words = words_from_transcript(_transcript(), 100.0, 110.0)
    assert [w.text for w in words] == ["uma", "frase", "de", "quatro", "exato"]
    assert words[0].start == pytest.approx(0.0)
    assert words[3].end == pytest.approx(4.0)  # relativo ao início do corte
    assert words[-1] == Word(pytest.approx(4.1), pytest.approx(5.0), "exato")
    assert all(a.end <= b.start + 1e-6 for a, b in itertools.pairwise(words[:4]))


def test_fallback_aligner_uses_next_when_first_fails_or_is_empty(tmp_path):
    cand = ClipCandidate(100.0, 110.0, "t", 0.9)

    class Boom:
        def align(self, *a): raise ImportError("sem whisper")

    class Empty:
        def align(self, *a): return []

    aligner = FallbackWordAligner(Boom(), Empty(), TranscriptWordAligner())
    assert len(aligner.align(tmp_path / "x.mp4", cand, _transcript())) == 5
    assert FallbackWordAligner(Boom()).align(tmp_path / "x.mp4", cand, _transcript()) == []


# ---------- composição vertical ----------
def test_crop_box_stays_inside_bounds():
    assert crop_box(10, 500, 200, 400, (0, 1000), 1080, 0.35) == (0, 360)
    assert crop_box(990, 500, 200, 400, (0, 1000), 1080, 0.35) == (800, 360)
    assert crop_box(500, 5000, 200, 400, (0, 1000), 1080, 0.35)[1] == 680  # y colado embaixo


def test_split_ranges():
    ranges = split_ranges(lambda t: 1.0 <= t < 2.0, 4.0)
    assert ranges == [(pytest.approx(1.0), pytest.approx(2.0))]
    assert split_ranges(lambda t: True, 1.0) == [(0.0, 1.0)]
    assert split_ranges(lambda t: False, 1.0) == []


def _frame(w=1920, h=1080):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, : w // 2] = (0, 0, 255)  # metade esquerda vermelha (BGR)
    img[:, w // 2:] = (255, 0, 0)  # metade direita azul
    return img


def _plan(split=None, cx=480.0):
    plan = FramingPlan(1920, 1080)
    plan.times = [0.0, 10.0]
    plan.shot_ids = [0, 0]
    plan.single = [SingleFrame(cx, 540, 1080, (0.0, 1920.0))] * 2
    plan.split = [split, split]
    return plan


def test_single_composition_follows_the_speaker():
    left = VerticalComposer(_plan(cx=300), (1920, 1080), (1080, 1920), split=False)
    right = VerticalComposer(_plan(cx=1600), (1920, 1080), (1080, 1920), split=False)
    out_left, out_right = left.compose(_frame(), 1.0), right.compose(_frame(), 1.0)
    assert out_left.shape == (1920, 1080, 3)
    assert tuple(out_left[960, 540]) == (0, 0, 255) and tuple(out_right[960, 540]) == (255, 0, 0)


def test_split_composition_stacks_two_people_with_divider():
    split = SplitFrame((480, 540), (1440, 540), 1000, (0.0, 1920.0), (0.0, 1920.0))
    composer = VerticalComposer(_plan(split), (1920, 1080), (1080, 1920), split=True)
    assert composer.is_split_at(1.0)
    out = composer.compose(_frame(), 1.0)
    assert out.shape == (1920, 1080, 3)
    assert tuple(out[300, 540]) == (0, 0, 255)  # bloco de cima: esquerda (vermelho)
    assert tuple(out[1600, 540]) == (255, 0, 0)  # bloco de baixo: direita (azul)
    off = VerticalComposer(_plan(split), (1920, 1080), (1080, 1920), split=False)
    assert not off.is_split_at(1.0)


# ---------- render de ponta a ponta ----------
def _make_source(tmp_path, seconds=4):
    out = tmp_path / "src.mp4"
    subprocess.run(
        [ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         f"testsrc=duration={seconds}:size=640x360:rate=25", "-f", "lavfi", "-i",
         f"sine=duration={seconds}", "-pix_fmt", "yuv420p", "-shortest", str(out)],
        check=True,
    )
    return out


@needs_ffmpeg
def test_read_frames_resamples_to_requested_fps(tmp_path):
    source = _make_source(tmp_path)
    frames = list(read_frames(source, 1.0, 20, 10.0))  # 25 fps de origem -> 10 fps
    assert len(frames) == 20 and frames[0][0] == 1.0 and frames[-1][0] == pytest.approx(2.9)
    assert frames[0][1].shape == (360, 640, 3)


def _fake_captions(words, duration, out, center_ranges=(), **kwargs):
    """Overlay transparente com uma faixa verde opaca (stand-in do Remotion; sem Node nos testes)."""
    frames = out.with_name("cap_%03d.png")
    img = Image.new("RGBA", (540, 960), (0, 0, 0, 0))
    img.paste((0, 255, 0, 255), (0, 440, 540, 520))
    for i in range(int(duration * 25) + 1):
        img.save(str(frames) % i)
    subprocess.run(
        [ffmpeg_exe(), "-loglevel", "error", "-y", "-framerate", "25", "-i", str(frames),
         "-c:v", "libvpx", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", str(out)], check=True,
    )
    return out


@needs_ffmpeg
def test_vertical_renderer_end_to_end_with_frame_and_captions(tmp_path, monkeypatch):
    source = _make_source(tmp_path)
    monkeypatch.setattr(
        vertical_renderer, "analyze_framing", lambda *a, **k: FramingPlan(640, 360)
    )  # sem rostos: recorte central, sem baixar o modelo do MediaPipe
    frame_png = tmp_path / "moldura.png"
    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    img.paste((255, 0, 255, 255), (0, 0, 1080, 40))  # faixa magenta no topo
    img.save(frame_png)

    settings = Settings(
        _env_file=None, data_dir=tmp_path, short_width=540, short_height=960, render_fps=25,
        render_preset="ultrafast", short_framing_sample_fps=2,
    )
    monkeypatch.setattr(vertical_renderer, "render_remotion_captions", _fake_captions)
    renderer = FfmpegVerticalRenderer(
        settings, [ImageOverlay(frame_png, "center", 1.0, 1.0, 0, "stretch")], random.Random(1)
    )
    words = [Word(0.0, 0.5, "olá"), Word(0.5, 1.0, "mundo")]
    out = tmp_path / "out" / "short.mp4"
    duration = renderer.render(source, 1.0, 3.0, out, words)

    info = probe(out)
    assert (info.width, info.height) == (540, 960) and info.has_audio
    assert duration == pytest.approx(2.0, abs=0.15)
    frame = tmp_path / "f.png"
    subprocess.run(
        [ffmpeg_exe(), "-loglevel", "error", "-y", "-ss", "1.5", "-i", str(out), "-frames:v", "1",
         str(frame)], check=True,
    )
    pixel = Image.open(frame).convert("RGB").getpixel((270, 5))
    assert pixel[0] > 200 and pixel[1] < 60 and pixel[2] > 200  # moldura magenta por cima
    shot = Image.open(frame).convert("RGB")
    inside, outside = shot.getpixel((270, 480)), shot.getpixel((270, 700))
    assert inside[1] > 200 and inside[0] < 80 and inside[2] < 80  # legenda (overlay) por cima
    assert outside != inside  # fora da faixa o overlay é transparente


@needs_ffmpeg
def test_vertical_renderer_reports_ffmpeg_failure(tmp_path, monkeypatch):
    source = _make_source(tmp_path, 2)
    monkeypatch.setattr(
        vertical_renderer, "analyze_framing", lambda *a, **k: FramingPlan(640, 360)
    )
    settings = Settings(
        _env_file=None, data_dir=tmp_path, short_width=540, short_height=960,
        render_preset="not-a-preset", short_captions=False,
    )
    renderer = FfmpegVerticalRenderer(settings, [])
    with pytest.raises(RuntimeError, match="ffmpeg falhou"):
        renderer.render(source, 0.0, 1.0, tmp_path / "x.mp4", [])


@needs_ffmpeg
def test_vertical_renderer_fails_when_remotion_fails(tmp_path, monkeypatch):
    source = _make_source(tmp_path)
    monkeypatch.setattr(
        vertical_renderer, "analyze_framing", lambda *a, **k: FramingPlan(640, 360)
    )

    def boom(*a, **k):
        raise CaptionError("sem node")

    monkeypatch.setattr(vertical_renderer, "render_remotion_captions", boom)
    settings = Settings(
        _env_file=None, data_dir=tmp_path, short_width=540, short_height=960, render_fps=25,
        render_preset="ultrafast", short_framing_sample_fps=2,
    )
    renderer = FfmpegVerticalRenderer(settings, [], random.Random(1))
    with pytest.raises(CaptionError):
        renderer.render(source, 1.0, 3.0, tmp_path / "out" / "short.mp4", [Word(0.0, 0.5, "olá")])
