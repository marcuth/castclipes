"""Montagem final do corte com moviepy (v2)."""

from __future__ import annotations

from pathlib import Path

from .overlay import Overlay


class ClipRenderer:
    def __init__(
        self,
        overlays: list[Overlay],
        outro_path: Path | None,
        fps: int,
        preset: str,
        crf: int,
        threads: int,
    ) -> None:
        self._overlays = overlays
        self._outro_path = outro_path
        self._fps = fps
        self._preset = preset
        self._crf = crf
        self._threads = threads

    def render(self, source: Path, keep: list[tuple[float, float]], out: Path) -> float:
        from moviepy import CompositeVideoClip, VideoFileClip, concatenate_videoclips

        out.parent.mkdir(parents=True, exist_ok=True)
        opened = [VideoFileClip(str(source))]
        try:
            src = opened[0]
            parts = [src.subclipped(s, min(e, src.duration)) for s, e in keep if e - s > 0.05]
            body = concatenate_videoclips(parts, method="chain") if len(parts) > 1 else parts[0]
            final = body
            if self._overlays:
                final = CompositeVideoClip([body, *(o.layer(body) for o in self._overlays)])
            if self._outro_path:
                outro = VideoFileClip(str(self._outro_path))
                opened.append(outro)
                if outro.size != final.size:
                    outro = outro.resized(final.size)
                final = concatenate_videoclips([final, outro], method="compose")
            final.write_videofile(
                str(out),
                fps=self._fps,
                codec="libx264",
                audio_codec="aac",
                preset=self._preset,
                threads=self._threads,
                ffmpeg_params=["-crf", str(self._crf), "-pix_fmt", "yuv420p"],
                logger=None,
            )
            return float(final.duration)
        finally:
            for clip in opened:
                clip.close()
