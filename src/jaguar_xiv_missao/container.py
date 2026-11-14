"""Composition root: monta o pipeline a partir das Settings."""

from __future__ import annotations

from .ai.factory import create_llm_client
from .analysis.constraints import ClipConstraints
from .analysis.selector import LLMClipSelector
from .analysis.triage import LLMVideoTriage
from .config import Settings
from .downloader import VideoDownloader
from .editing.render_factory import create_renderer
from .editing.silence import FfmpegSilenceDetector, NullSilenceDetector
from .events import EventBus
from .metadata.generator import LLMMetadataGenerator
from .observers.listeners import LoggingObserver, WebhookObserver
from .pipeline import Pipeline
from .publishing.youtube import create_publisher
from .sources.rss import RssVideoSource
from .storage.state import StateStore
from .thumbnails.base import create_thumbnail_generator
from .transcription.factory import create_fallback_provider, create_primary_provider


def build_pipeline(settings: Settings) -> Pipeline:
    llm = create_llm_client(settings)
    downloader = VideoDownloader(settings.work_dir, settings.max_source_height)
    rules = ClipConstraints(
        min_seconds=settings.clip_min_seconds,
        max_seconds=settings.clip_max_seconds,
        min_score=settings.clip_min_score,
        max_clips=settings.max_clips_per_video,
        edge_padding=settings.clip_edge_padding_seconds,
    )
    bus = EventBus()
    bus.subscribe_all(LoggingObserver())
    if settings.notify_webhook_url:
        bus.subscribe_all(WebhookObserver(settings.notify_webhook_url))

    silence = (
        FfmpegSilenceDetector(settings.silence_threshold_db, settings.silence_min_duration_seconds)
        if settings.silence_cut_enabled
        else NullSilenceDetector()
    )
    return Pipeline(
        settings=settings,
        source=RssVideoSource(settings.source_live_playlist_ids, settings.source_max_age_hours),
        downloader=downloader,
        primary_transcriber=create_primary_provider(settings),
        fallback_transcriber=create_fallback_provider(settings, downloader),
        triage=LLMVideoTriage(llm, settings.triage_min_score),
        selector=LLMClipSelector(
            llm, rules, settings.clip_target_seconds, settings.selection_window_seconds,
            settings.selection_window_overlap_seconds,
        ),
        silence=silence,
        renderer=create_renderer(settings),
        metadata=LLMMetadataGenerator(llm, settings),
        thumbnails=create_thumbnail_generator(settings),
        publisher=create_publisher(settings),
        store=StateStore(settings.db_path),
        bus=bus,
    )
