from __future__ import annotations

from typing import Protocol

from ..models import SourceVideo, Transcript


class TranscriptProvider(Protocol):
    name: str

    def fetch(self, video: SourceVideo) -> Transcript | None:
        """Retorna None se este provedor não consegue transcrever o vídeo."""
