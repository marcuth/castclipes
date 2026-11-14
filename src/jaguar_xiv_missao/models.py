"""Modelos de domínio (sem dependências externas)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class ClipPattern(StrEnum):
    """Padrões de corte observados no canal-alvo (ver PADROES_CANAL.md)."""

    REACTION = "reaction"  # "X REAGE a Y"
    RESPONSE = "response"  # "X RESPONDE Y"
    REVELATION = "revelation"  # "X FALA A VERDADE / REVELA BASTIDORES"
    DEBATE = "debate"
    OTHER = "other"


@dataclass(frozen=True)
class SourceVideo:
    id: str
    title: str
    description: str = ""
    channel_id: str = ""
    channel_title: str = ""
    published_at: datetime | None = None
    duration_seconds: float | None = None
    is_live: bool = False

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


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
    pattern: ClipPattern = ClipPattern.OTHER
    speakers: tuple[str, ...] = ()
    target: str | None = None
    """Terceiro visado (ex.: 'Nikolas Ferreira'); aparece no título."""
    summary: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class ClipMetadata:
    title: str
    description: str
    tags: tuple[str, ...]


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
