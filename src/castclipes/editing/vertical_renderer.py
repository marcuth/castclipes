"""Render dos shorts (9:16).

O OpenCV lê o arquivo-fonte e `VerticalComposer` monta cada quadro vertical (enquadramento por
rosto ou split-screen). Os quadros seguem por pipe para UM ffmpeg, que junta o áudio do trecho,
aplica a moldura/marca d'água e queima as legendas ASS. Sem MoviePy no caminho dos pixels.
"""

from __future__ import annotations

import logging
import random
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from PIL import Image

from ..captions.ass import CaptionStyle, generate_ass
from ..config import Settings
from ..models import Word
from ..vision.composer import VerticalComposer, split_ranges
from ..vision.detection import set_model_path
from ..vision.tracking import FramingPlan, analyze_framing
from .ffmpeg_renderer import AUDIO_RATE, probe
from .overlay import ImageOverlay
from .silence import ffmpeg_exe

logger = logging.getLogger(__name__)

MIN_SPLIT_RATIO = 0.20
"""Só considera o split-screen se houver dois rostos em pelo menos essa fração do corte."""
BUNDLED_FONT = Path(__file__).parent.parent / "thumbnails" / "assets" / "fonts" / "Anton-Regular.ttf"


class ShortRenderer(Protocol):
    def render(
        self, source: Path, start: float, end: float, out: Path, words: Sequence[Word]
    ) -> float:
        """Monta o short a partir de [start, end] (tempos absolutos de `source`) e devolve a
        duração final. `words` tem tempo relativo ao início do corte."""
        ...


def read_frames(
    source: Path, start: float, count: int, fps: float
) -> Iterator[tuple[float, np.ndarray]]:
    """`(tempo absoluto, quadro BGR)` a `fps`, a partir de `start`. Repete o quadro anterior
    quando o vídeo-fonte tem fps menor e pula quadros quando tem fps maior."""
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"não consegui abrir {source}")
    try:
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        position = int(start * src_fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, position)  # próximo quadro a ser lido
        last: np.ndarray | None = None
        for k in range(count):
            t = start + k / fps
            wanted = round(t * src_fps)
            while position < wanted:  # pula sem decodificar tudo
                if not cap.grab():
                    break
                position += 1
            if position == wanted or last is None:
                ok, frame = cap.read()
                if ok:
                    last = frame
                    position += 1
            if last is None:
                raise RuntimeError(f"sem quadros em {source} a partir de {start:.1f}s")
            yield t, last
    finally:
        cap.release()


class FfmpegVerticalRenderer:
    def __init__(
        self,
        settings: Settings,
        overlays: list[ImageOverlay],
        rng: random.Random | None = None,
    ) -> None:
        self._s = settings
        self._overlays = overlays
        self._rng = rng or random.Random()
        set_model_path(settings.face_model_path)

    # ---------- API ----------
    def render(
        self, source: Path, start: float, end: float, out: Path, words: Sequence[Word]
    ) -> float:
        s = self._s
        info = probe(source)
        if not info.has_audio:
            raise RuntimeError(f"{source} não tem áudio")
        out.parent.mkdir(parents=True, exist_ok=True)
        end = min(end, info.duration)
        duration = end - start
        fps = float(s.render_fps)

        plan = analyze_framing(str(source), start, end, s.short_framing_sample_fps)
        composer = VerticalComposer(
            plan, (info.width, info.height), (s.short_width, s.short_height),
            split=self._use_split(plan),
        )
        center = split_ranges(lambda t: composer.is_split_at(start + t), duration)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            captions = self._write_captions(tmp_dir, words, center)
            cmd = self._command(source, start, duration, out, fps, captions)
            self._pipe(cmd, tmp_dir, source, start, int(duration * fps), fps, composer)
        return probe(out).duration

    # ---------- partes ----------
    def _use_split(self, plan: FramingPlan) -> bool:
        s = self._s
        if not s.short_split_screen or plan.split_ratio < MIN_SPLIT_RATIO:
            return False
        use = self._rng.random() < s.short_split_chance
        logger.info(
            "Split-screen %s (dois rostos em %.0f%% do corte, chance %.0f%%)",
            "ativado" if use else "não sorteado", plan.split_ratio * 100,
            s.short_split_chance * 100,
        )
        return use

    def _write_captions(
        self, tmp: Path, words: Sequence[Word], center: list[tuple[float, float]]
    ) -> bool:
        """Grava `subs.ass` e a fonte em `tmp`. O filtro usa nomes relativos (cwd=tmp) porque o
        escape de caminhos do Windows (`C:\\`) quebra o filtro `subtitles`."""
        if not self._s.short_captions or not words:
            return False
        font = self._s.short_caption_font_path or BUNDLED_FONT
        fonts_dir = tmp / "fonts"
        fonts_dir.mkdir()
        shutil.copy(font, fonts_dir / font.name)
        style = CaptionStyle(
            font_name=_font_family(font), font_file=font,
            highlight=self._s.short_caption_highlight, margin_v=self._s.short_caption_margin_v,
        )
        (tmp / "subs.ass").write_text(generate_ass(words, style, center), encoding="utf-8")
        return True

    def _command(
        self, source: Path, start: float, duration: float, out: Path, fps: float, captions: bool
    ) -> list[str]:
        s = self._s
        cmd = [
            ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{s.short_width}x{s.short_height}",
            "-framerate", f"{fps:g}", "-i", "pipe:0",
            "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source.resolve()),
        ]
        lines = ["[0:v]format=yuv420p[v0]"]
        current = "v0"
        for j, overlay in enumerate(self._overlays):
            with Image.open(overlay.path) as image:
                item = image.size
            (ow, oh), (x, y) = overlay.placement((s.short_width, s.short_height), item)
            idx = 2 + j
            cmd += ["-loop", "1", "-framerate", f"{fps:g}", "-i", str(overlay.path.resolve())]
            alpha = f",colorchannelmixer=aa={overlay.opacity}" if overlay.opacity < 1 else ""
            lines.append(f"[{idx}:v]scale={ow}:{oh},format=rgba{alpha}[ov{j}]")
            lines.append(f"[{current}][ov{j}]overlay=x={x}:y={y}:shortest=1[v{j + 1}]")
            current = f"v{j + 1}"
        if captions:
            lines.append(f"[{current}]subtitles=subs.ass:fontsdir=fonts[outv]")
        else:
            lines.append(f"[{current}]null[outv]")
        lines.append(f"[1:a]aresample={AUDIO_RATE},aformat=channel_layouts=stereo[outa]")
        cmd += [
            "-filter_complex", ";".join(lines), "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", s.render_preset, "-crf", str(s.render_crf),
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-threads", str(s.render_threads),
            "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}", "-movflags", "+faststart",
            str(out.resolve()),
        ]
        return cmd

    @staticmethod
    def _pipe(
        cmd: list[str], cwd: Path, source: Path, start: float, count: int, fps: float,
        composer: VerticalComposer,
    ) -> None:
        err_path = cwd / "ffmpeg.err"
        with open(err_path, "wb") as err:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err, cwd=cwd)
            assert proc.stdin is not None
            try:
                for t, frame in read_frames(source, start, count, fps):
                    proc.stdin.write(np.ascontiguousarray(composer.compose(frame, t)).tobytes())
                proc.stdin.close()
            except BrokenPipeError:
                pass  # o ffmpeg morreu; o motivo está no stderr
            except BaseException:
                proc.kill()
                raise
            finally:
                if not proc.stdin.closed:
                    try:
                        proc.stdin.close()
                    except OSError:
                        pass
                code = proc.wait()
        if code != 0:
            raise RuntimeError(
                f"ffmpeg falhou ({code}):\n"
                + err_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            )


def _font_family(path: Path) -> str:
    """Nome de família que o libass usa para achar a fonte (lido do próprio arquivo)."""
    from PIL import ImageFont

    try:
        family, _ = ImageFont.truetype(str(path), 20).getname()
        return family
    except OSError:
        return path.stem.split("-")[0]

