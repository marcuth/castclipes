import subprocess

import pytest
from PIL import Image, ImageDraw

from castclipes.editing.ffmpeg_renderer import FfmpegRenderer, probe
from castclipes.editing.overlay import ImageOverlay
from castclipes.editing.silence import ffmpeg_exe


def _ffmpeg_works() -> bool:
    try:
        proc = subprocess.run([ffmpeg_exe(), "-version"], capture_output=True, check=False)
        return proc.returncode == 0
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _ffmpeg_works(), reason="ffmpeg indisponível")


def _make(tmp_path, name, source, seconds):
    out = tmp_path / name
    subprocess.run(
        [ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "lavfi", "-i", source, "-f", "lavfi",
         "-i", f"sine=duration={seconds}", "-pix_fmt", "yuv420p", "-shortest", str(out)],
        check=True,
    )
    return out


def _pixel(video, at, xy):
    frame = video.parent / f"frame_{at}.png"
    subprocess.run(
        [ffmpeg_exe(), "-loglevel", "error", "-y", "-ss", str(at), "-i", str(video),
         "-frames:v", "1", str(frame)],
        check=True,
    )
    return Image.open(frame).convert("RGB").getpixel(xy)


def test_renders_cuts_frame_cta_and_outro(tmp_path):
    body = _make(tmp_path, "body.mp4", "testsrc=duration=20:size=640x360:rate=25", 20)
    cta = _make(tmp_path, "cta.mp4", "color=c=red:size=320x180:rate=25:duration=2", 2)
    outro = tmp_path / "outro.mp4"  # sem áudio de propósito
    subprocess.run(
        [ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "color=c=blue:size=320x180:rate=25:duration=1", "-pix_fmt", "yuv420p", str(outro)],
        check=True,
    )
    frame = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    ImageDraw.Draw(frame).rectangle((0, 0, 1919, 1079), outline=(0, 255, 0, 255), width=90)
    frame_path = tmp_path / "frame.png"
    frame.save(frame_path)
    overlays = [ImageOverlay(frame_path, "center", 1.0, 1.0, 0, "stretch")]

    renderer = FfmpegRenderer(overlays, outro, cta, 25, "ultrafast", 30, 2)
    out = tmp_path / "out.mp4"
    # mantém 1-6s e 9-15s (11s); o CTA entra no 12s absoluto = 8s do corte
    duration = renderer.render(body, [(1.0, 6.0), (9.0, 15.0)], out, insert_at=12.0)

    info = probe(out)
    assert abs(duration - 14.0) < 0.5  # 11 + 2 (CTA) + 1 (outro)
    assert (info.width, info.height, info.has_audio) == (640, 360, True)
    assert _pixel(out, 3, (5, 5))[1] > 200  # moldura (verde) sobre o corte
    assert _pixel(out, 9, (5, 5)) == pytest.approx((253, 0, 0), abs=8)  # CTA, sem moldura
    assert _pixel(out, 13.5, (5, 5))[2] > 200  # outro (azul), sem moldura


def test_single_part_without_extras(tmp_path):
    body = _make(tmp_path, "body.mp4", "testsrc=duration=8:size=320x180:rate=25", 8)
    out = tmp_path / "out.mp4"
    duration = FfmpegRenderer([], None, None, 25, "ultrafast", 30, 2).render(
        body, [(2.0, 6.0)], out
    )
    assert abs(duration - 4.0) < 0.5
