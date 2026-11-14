"""Extração de frames do vídeo completo com ffmpeg (seek rápido, um frame por chamada)."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from PIL import Image

from ..editing.silence import ffmpeg_exe


def extract_frame(source: Path, at: float, width: int | None = None) -> Image.Image | None:
    """Frame em `at` segundos (tempo absoluto do arquivo). `width` reduz a imagem (aspecto mantido)."""
    cmd = [ffmpeg_exe(), "-nostdin", "-loglevel", "error", "-ss", f"{at:.3f}", "-i", str(source)]
    if width:
        cmd += ["-vf", f"scale={width}:-2"]
    cmd += ["-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        return None
    return Image.open(io.BytesIO(proc.stdout)).convert("RGB")


def sample_times(start: float, end: float, count: int, margin_pct: float = 0.05) -> list[float]:
    """`count` instantes igualmente espaçados dentro do corte, longe das pontas."""
    span = end - start
    if count <= 0 or span <= 0:
        return []
    lo, hi = start + span * margin_pct, end - span * margin_pct
    if count == 1:
        return [(lo + hi) / 2]
    step = (hi - lo) / (count - 1)
    return [lo + i * step for i in range(count)]
