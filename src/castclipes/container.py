"""Composition root: monta o pipeline a partir das Settings."""

from __future__ import annotations

from .ai.base import LLMClient
from .ai.factory import create_llm_client
from .analysis.constraints import ClipConstraints
from .analysis.heuristics import HeuristicClipSelector
from .analysis.selector import ClipSelector, LLMClipSelector
from .analysis.triage import LLMVideoTriage
from .captions.words import create_word_aligner
from .config import Settings
from .downloader import VideoDownloader
from .editing.render_factory import create_renderer, create_short_renderer
from .editing.silence import FfmpegSilenceDetector, NullSilenceDetector
from .events import EventBus
from .metadata.generator import LLMMetadataGenerator
from .models import ClipFormat
from .observers.listeners import LoggingObserver, WebhookObserver
from .pipeline import Pipeline
from .publishing.youtube import create_publisher
from .sources.rss import RssVideoSource, ytdlp_playlist
from .storage.state import StateStore
from .thumbnails.base import create_thumbnail_generator
from .transcription.factory import create_fallback_provider, create_primary_provider


def build_pipeline(settings: Settings) -> Pipeline:
    llm = create_llm_client(settings)
    downloader = VideoDownloader(settings.work_dir, settings.max_source_height)
    selectors = {fmt: _create_selector(settings, llm, fmt) for fmt in ClipFormat}
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
        source=RssVideoSource(
            settings.source_live_playlist_ids, settings.source_max_age_hours,
            settings.source_fallback_limit,
            ytdlp_playlist if settings.source_fallback_limit > 0 else None,
        ),
        downloader=downloader,
        primary_transcriber=create_primary_provider(settings),
        fallback_transcriber=create_fallback_provider(settings, downloader),
        triage=LLMVideoTriage(llm, settings.triage_min_score),
        selectors=selectors,
        silence=silence,
        renderer=create_renderer(settings),
        short_renderer=create_short_renderer(settings),
        aligner=create_word_aligner(settings),
        metadata=LLMMetadataGenerator(llm, settings),
        thumbnails=create_thumbnail_generator(settings),
        publisher=create_publisher(settings),
        store=StateStore(settings.db_path),
        bus=bus,
    )


def _create_selector(settings: Settings, llm: LLMClient, fmt: ClipFormat) -> ClipSelector:
    """Strategy do seletor de cortes conforme SELECTOR_ENGINE."""
    long = fmt is ClipFormat.LONG
    rules = ClipConstraints(
        min_seconds=settings.long_min_seconds if long else settings.short_min_seconds,
        max_seconds=settings.long_max_seconds if long else settings.short_max_seconds,
        min_score=settings.long_min_score if long else settings.short_min_score,
        max_clips=settings.max_long_per_video if long else settings.max_shorts_per_video,
        edge_padding=(
            settings.clip_edge_padding_seconds if long else settings.short_edge_padding_seconds
        ),
    )
    target = settings.long_target_seconds if long else settings.short_target_seconds
    if settings.selector_engine == "heuristics":
        return HeuristicClipSelector(fmt, rules, target, settings.heuristic_skip_intro_seconds)
    return LLMClipSelector(
        llm, fmt, rules, target, settings.selection_window_seconds,
        settings.selection_window_overlap_seconds,
    )
