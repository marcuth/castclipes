from __future__ import annotations

from ..config import Settings
from ..downloader import VideoDownloader
from .base import TranscriptProvider
from .whisper import WhisperTranscriptProvider
from .youtube import YouTubeTranscriptProvider


def create_primary_provider(settings: Settings) -> TranscriptProvider:
    return YouTubeTranscriptProvider(settings.transcript_languages)


def create_fallback_provider(settings: Settings, downloader: VideoDownloader) -> TranscriptProvider:
    return WhisperTranscriptProvider(
        downloader,
        settings.whisper_model,
        settings.whisper_device,
        settings.whisper_compute_type,
        settings.transcript_languages[0] if settings.transcript_languages else "pt",
    )
