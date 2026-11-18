"""Detecção e planejamento do corte de silêncio."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


@dataclass(frozen=True)
class Silence:
    start: float
    end: float


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return "ffmpeg"


def parse_silencedetect(stderr: str, total_duration: float | None = None) -> list[Silence]:
    silences: list[Silence] = []
    start: float | None = None
    for line in stderr.splitlines():
        if m := _START.search(line):
            start = max(0.0, float(m.group(1)))
        elif (m := _END.search(line)) and start is not None:
            silences.append(Silence(start, float(m.group(1))))
            start = None
    if start is not None and total_duration is not None and total_duration > start:
        silences.append(Silence(start, total_duration))  # silêncio até o fim do arquivo
    return silences


def plan_keep_ranges(
    duration: float, silences: list[Silence], min_silence: float, keep_padding: float
) -> list[tuple[float, float]]:
    """Trechos a manter. Pausas >= `min_silence` são encurtadas, preservando `keep_padding`
    em cada ponta (mantém o ritmo natural da fala)."""
    cuts: list[tuple[float, float]] = []
    for s in sorted(silences, key=lambda x: x.start):
        if s.end - s.start < min_silence:
            continue
        cut_start, cut_end = s.start + keep_padding, s.end - keep_padding
        if cut_end > cut_start:
            cuts.append((max(0.0, cut_start), min(duration, cut_end)))
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for cut_start, cut_end in cuts:
        if cut_start > cursor:
            keep.append((cursor, cut_start))
        cursor = max(cursor, cut_end)
    if cursor < duration:
        keep.append((cursor, duration))
    return keep


class SilenceDetector(Protocol):
    def detect(self, media: Path, start: float, end: float) -> list[Silence]: ...


class NullSilenceDetector:
    def detect(self, media: Path, start: float, end: float) -> list[Silence]:
        return []


class FfmpegSilenceDetector:
    def __init__(self, threshold_db: float, min_duration: float) -> None:
        self._threshold_db = threshold_db
        # o ffmpeg só precisa reportar pausas candidatas; o filtro final é do plan_keep_ranges
        self._min_duration = min_duration

    def detect(self, media: Path, start: float, end: float) -> list[Silence]:
        cmd = [
            ffmpeg_exe(), "-nostats", "-hide_banner", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", str(media), "-vn",
            "-af", f"silencedetect=noise={self._threshold_db}dB:d={self._min_duration}",
            "-f", "null", "-",
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
        )
        return parse_silencedetect(proc.stderr, end - start)
