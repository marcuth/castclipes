"""Observers: logging e notificação por webhook (Discord/Slack compatível)."""

from __future__ import annotations

import logging

from ..events import (
    ClipPublished,
    ClipRendered,
    ClipsSelected,
    Event,
    PipelineError,
    TranscriptReady,
    VideoDiscovered,
    VideoSkipped,
)

logger = logging.getLogger("jaguar")


class LoggingObserver:
    def __call__(self, event: Event) -> None:
        match event:
            case VideoDiscovered(video):
                logger.info("Novo vídeo: %s (%s)", video.title, video.id)
            case VideoSkipped(video, reason):
                logger.info("Ignorado %s: %s", video.id, reason)
            case TranscriptReady(video, source, segments):
                logger.info("Transcrição %s de %s: %d segmentos", source, video.id, segments)
            case ClipsSelected(video, candidates):
                for c in candidates:
                    logger.info(
                        "Corte %s [%.0f-%.0f s, %.0f min, nota %.2f]: %s",
                        video.id, c.start, c.end, c.duration / 60, c.score, c.topic,
                    )
            case ClipRendered(clip):
                logger.info("Renderizado: %s (%.1f min)", clip.path, clip.duration_seconds / 60)
            case ClipPublished(clip, result):
                logger.info("Publicado: %s", result.url or "(dry-run)")
            case PipelineError(video, error):
                logger.error("Erro em %s: %r", video.id if video else "-", error)


class WebhookObserver:
    def __init__(self, url: str) -> None:
        self._url = url

    def __call__(self, event: Event) -> None:
        if isinstance(event, ClipPublished):
            title = event.clip.metadata.title if event.clip.metadata else event.clip.path.name
            text = f"✅ {title}\n{event.result.url or '(dry-run)'}"
        elif isinstance(event, PipelineError):
            text = f"❌ Erro: {event.error!r}"
        else:
            return
        import httpx

        httpx.post(self._url, json={"content": text, "text": text}, timeout=10)
