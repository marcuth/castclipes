from __future__ import annotations

import logging

from ..models import SourceVideo, Transcript, TranscriptSegment

logger = logging.getLogger(__name__)


class YouTubeTranscriptProvider:
    name = "youtube"

    def __init__(self, languages: list[str]) -> None:
        self._languages = languages

    def fetch(self, video: SourceVideo) -> Transcript | None:
        from youtube_transcript_api import YouTubeTranscriptApi

        try:
            fetched = YouTubeTranscriptApi().fetch(video.id, languages=self._languages)
        except Exception as exc:  # noqa: BLE001 - legendas desativadas, bloqueio de IP, etc.
            logger.info("Sem legenda do YouTube para %s (%s)", video.id, type(exc).__name__)
            return None
        segments = [
            TranscriptSegment(s.start, s.start + s.duration, s.text.replace("\n", " ").strip())
            for s in fetched
            if s.text.strip()
        ]
        return Transcript(segments, source=self.name, language=fetched.language_code)
