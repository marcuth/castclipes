"""Modelos de domínio (sem dependências externas)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class ClipFormat(StrEnum):
    """Formato de saída de um corte."""

    LONG = "long"  # 16:9, um assunto do começo ao fim (minutos)
    SHORT = "short"  # 9:16, um gancho de poucos segundos, com legenda palavra a palavra


@dataclass(frozen=True)
class SourceVideo:
    id: str
    title: str
    description: str = ""
    channel_id: str = ""
    channel_title: str = ""
    published_at: datetime | None = None
    duration_seconds: float | None = None
    live_status: str | None = None
    """Valor do yt-dlp: is_upcoming, is_live, post_live, was_live ou not_live."""

    @property
    def live_in_progress(self) -> bool:
        """Live agendada, no ar ou recém-encerrada (gravação ainda sendo processada)."""
        return self.live_status in {"is_upcoming", "is_live", "post_live"}

    @property
    def live_ended(self) -> bool:
        return self.live_status == "was_live"

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"


@dataclass(frozen=True)
class Word:
    """Palavra com tempo (usada nas legendas dos shorts)."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: tuple[Word, ...] = ()
    """Vazio quando a fonte não traz tempo por palavra (legenda do YouTube)."""


@dataclass
class Transcript:
    segments: list[TranscriptSegment]
    source: str  # "youtube" | "whisper"
    language: str = "pt"

    @property
    def duration(self) -> float:
        return self.segments[-1].end if self.segments else 0.0

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.segments)

    def window(self, start: float, end: float) -> list[TranscriptSegment]:
        return [s for s in self.segments if s.end > start and s.start < end]

    def text_between(self, start: float, end: float) -> str:
        return " ".join(s.text for s in self.window(start, end))

    def render(self, start: float = 0.0, end: float | None = None, step: float = 15.0) -> str:
        """Texto com marcadores `[mm:ss]` a cada `step` s, para prompts de IA."""
        end = self.duration if end is None else end
        lines: list[str] = []
        next_mark = start
        for seg in self.window(start, end):
            if seg.start >= next_mark:
                lines.append(f"\n[{int(seg.start)}s]")
                next_mark = seg.start + step
            lines.append(seg.text)
        return " ".join(lines).strip()


@dataclass(frozen=True)
class ClipCandidate:
    start: float
    end: float
    topic: str
    score: float
    format: ClipFormat = ClipFormat.LONG
    hook: str = ""
    """Frase de abertura do corte (primeiros segundos); base do título dos shorts."""
    speakers: tuple[str, ...] = ()
    summary: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class ClipMetadata:
    title: str
    description: str
    tags: tuple[str, ...]
    thumbnail_text: str = ""
    """Gancho curto (3 a 5 palavras) para a thumbnail; vazio = derivado do título."""


@dataclass
class RenderedClip:
    candidate: ClipCandidate
    source: SourceVideo
    path: Path
    duration_seconds: float
    metadata: ClipMetadata | None = None
    thumbnail_path: Path | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishResult:
    video_id: str | None
    url: str | None
    dry_run: bool = False
