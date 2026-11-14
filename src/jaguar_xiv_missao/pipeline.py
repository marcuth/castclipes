"""Orquestração: descobrir -> transcrever -> selecionar -> baixar -> editar -> publicar."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .analysis.selector import ClipSelector
from .analysis.text import count_mentions
from .analysis.triage import VideoTriage
from .config import Settings
from .downloader import VideoDownloader
from .editing.renderer import ClipRenderer
from .editing.silence import SilenceDetector, plan_keep_ranges
from .events import (
    ClipPublished,
    ClipRendered,
    ClipsSelected,
    EventBus,
    PipelineError,
    TranscriptReady,
    VideoDiscovered,
    VideoSkipped,
    VideoWaiting,
)
from .metadata.generator import MetadataGenerator
from .models import ClipCandidate, RenderedClip, SourceVideo, Transcript
from .publishing.base import Publisher
from .sources.base import VideoSource
from .storage.state import StateStore
from .thumbnails.base import ThumbnailGenerator
from .transcription.base import TranscriptProvider

logger = logging.getLogger(__name__)


@dataclass
class Pipeline:
    settings: Settings
    source: VideoSource
    downloader: VideoDownloader
    primary_transcriber: TranscriptProvider
    fallback_transcriber: TranscriptProvider
    triage: VideoTriage
    selector: ClipSelector
    silence: SilenceDetector
    renderer: ClipRenderer
    metadata: MetadataGenerator
    thumbnails: ThumbnailGenerator
    publisher: Publisher
    store: StateStore
    bus: EventBus

    # ---------- entrada ----------
    def run_once(self) -> None:
        for video in self.source.latest():
            if self.store.seen(video.id):
                continue
            self.process(video)

    def process(self, video: SourceVideo, *, force: bool = False) -> None:
        """`force` ignora as regras de live (usado no comando `process` manual)."""
        s = self.settings
        self.bus.publish(VideoDiscovered(video))
        try:
            video = self.downloader.enrich(video)
            if not force and video.live_in_progress:
                # Sem marcar no estado: a próxima verificação olha de novo.
                return self.bus.publish(VideoWaiting(video, f"live {video.live_status}"))
            reason = self._reject_reason(video, force)
            if reason:
                return self._skip(video, reason)

            transcript = self._transcribe(video, force)
            if transcript is None:
                return
            if not self._mentions_enough(video, transcript):
                return self._skip(video, "poucas menções aos alvos")

            candidates = self.selector.select(video, transcript)
            self.bus.publish(ClipsSelected(video, candidates))
            if not candidates:
                return self._skip(video, "IA não encontrou cortes bons")

            source_file: Path | None = None
            try:
                for candidate in candidates:
                    if self.store.published_today() >= s.max_publish_per_day:
                        logger.warning("Limite diário de publicações atingido; retomo amanhã")
                        return  # não marca o vídeo como processado
                    if self.store.clip_done(video.id, candidate.start, candidate.end):
                        continue
                    if source_file is None:  # baixa o vídeo completo uma vez; cortes são locais
                        source_file = self.downloader.download_video(video)
                    self._make_clip(video, candidate, source_file)
            finally:
                self.downloader.cleanup(video.id)
            self.store.mark(video.id, "done")
        except Exception as exc:
            logger.exception("Falha ao processar %s", video.id)
            self.store.mark(video.id, "failed", repr(exc))
            self.bus.publish(PipelineError(video, exc))

    # ---------- etapas ----------
    def _reject_reason(self, video: SourceVideo, force: bool = False) -> str | None:
        s = self.settings
        if s.only_lives and not force and not video.live_ended:
            return "não é uma live"
        duration = video.duration_seconds or 0
        if duration < s.source_min_duration_seconds:
            return f"muito curto ({duration:.0f}s)"
        if duration > s.source_max_duration_seconds:
            return f"muito longo ({duration:.0f}s)"
        return None

    def _transcribe(self, video: SourceVideo, force: bool = False) -> Transcript | None:
        transcript = self.primary_transcriber.fetch(video)
        if transcript is None and video.live_ended and not force and self._caption_wait(video):
            return None
        if transcript is None:
            verdict = self.triage.evaluate(video)
            if not verdict.approved:
                self._skip(video, f"sem legenda e triagem reprovou ({verdict.score:.2f}): {verdict.reason}")
                return None
            transcript = self.fallback_transcriber.fetch(video)
        if transcript is None or not transcript.segments:
            self._skip(video, "não foi possível transcrever")
            return None
        self.bus.publish(TranscriptReady(video, transcript.source, len(transcript.segments)))
        return transcript

    def _caption_wait(self, video: SourceVideo) -> bool:
        """True se a live acabou há pouco e a legenda automática ainda pode sair."""
        wait = timedelta(minutes=self.settings.live_caption_wait_minutes)
        since = self.store.waiting_since(video.id)
        if since is None:
            self.store.mark_waiting(video.id, "aguardando legenda da live")
            since = datetime.now(UTC)
        if datetime.now(UTC) - since < wait:
            self.bus.publish(VideoWaiting(video, "aguardando legenda automática da live"))
            return True
        return False

    def _mentions_enough(self, video: SourceVideo, transcript: Transcript) -> bool:
        text = f"{video.title} {video.description} {transcript.full_text}"
        mentions = count_mentions(text, self.settings.target_keywords)
        return mentions >= self.settings.min_keyword_mentions

    def _make_clip(self, video: SourceVideo, candidate: ClipCandidate, source_file: Path) -> None:
        s = self.settings
        stem = f"{video.id}_{int(candidate.start)}_{int(candidate.end)}"
        out = s.output_dir / f"{stem}.mp4"
        keep = [(candidate.start, candidate.end)]
        if s.silence_cut_enabled:
            silences = self.silence.detect(source_file, candidate.start, candidate.end)
            relative = plan_keep_ranges(
                candidate.duration, silences, s.silence_min_duration_seconds,
                s.silence_keep_padding_seconds,
            )
            keep = [(candidate.start + a, candidate.start + b) for a, b in relative]
        duration = self.renderer.render(source_file, keep, out)
        clip = RenderedClip(candidate, video, out, duration)
        clip.metadata = self.metadata.generate(video, candidate)
        clip.thumbnail_path = self.thumbnails.generate(
            video, candidate, clip.metadata, s.output_dir / f"{stem}.jpg"
        )
        self.bus.publish(ClipRendered(clip))
        result = self.publisher.publish(clip)
        self.store.record_clip(
            video.id, candidate.start, candidate.end, clip.metadata.title, result.video_id
        )
        self.bus.publish(ClipPublished(clip, result))

    def _skip(self, video: SourceVideo, reason: str) -> None:
        self.store.mark(video.id, "skipped", reason)
        self.bus.publish(VideoSkipped(video, reason))
