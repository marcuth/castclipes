"""Orquestração: descobrir -> transcrever -> selecionar (long/short) -> baixar -> editar -> publicar."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .analysis.selector import ClipSelector
from .analysis.triage import VideoTriage
from .captions.words import WordAligner
from .config import Settings
from .downloader import VideoDownloader
from .editing.insertion import choose_insert_point
from .editing.renderer import Renderer
from .editing.silence import SilenceDetector, plan_keep_ranges
from .editing.vertical_renderer import ShortRenderer
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
from .models import ClipCandidate, ClipFormat, RenderedClip, SourceVideo, Transcript
from .publishing.base import Publisher
from .publishing.schedule import next_slot
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
    selectors: dict[ClipFormat, ClipSelector]
    silence: SilenceDetector
    renderer: Renderer
    short_renderer: ShortRenderer
    aligner: WordAligner
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

    @property
    def formats(self) -> list[ClipFormat]:
        return [ClipFormat(f) for f in self.settings.clip_formats]

    def process(
        self, video: SourceVideo, *, force: bool = False,
        formats: list[ClipFormat] | None = None,
    ) -> None:
        """`force` ignora as regras de live (usado no comando `process` manual).
        `formats` substitui CLIP_FORMATS nesta execução."""
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

            candidates = self._select(video, transcript, formats or self.formats)
            self.bus.publish(ClipsSelected(video, candidates))
            if not candidates:
                return self._skip(video, "IA não encontrou cortes bons")

            source_file: Path | None = None
            try:
                for candidate in candidates:
                    if self.store.published_today() >= s.max_publish_per_day:
                        logger.warning("Limite diário de publicações atingido; retomo amanhã")
                        return  # não marca o vídeo como processado
                    if s.publish_schedule_enabled and self._next_slot() is None:
                        logger.warning("Fila de postagem cheia (%d dias); retomo quando liberar",
                                       s.publish_queue_days)
                        return
                    if self.store.clip_done(
                            video.id, candidate.format.value, candidate.start, candidate.end):
                        continue
                    if source_file is None:  # baixa o vídeo completo uma vez; cortes são locais
                        source_file = self.downloader.download_video(video)
                    self._make_clip(video, candidate, source_file, transcript)
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
        # Regra fixa do projeto: só lives encerradas (uploads comuns nunca entram).
        if not force and not video.live_ended:
            return "não é uma live"
        if not force and video.published_at is not None:
            age = datetime.now(UTC) - video.published_at
            if age > timedelta(hours=s.source_max_age_hours):
                return f"antigo demais ({age.total_seconds() / 3600:.0f}h)"
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

    def _select(
        self, video: SourceVideo, transcript: Transcript, formats: list[ClipFormat]
    ) -> list[ClipCandidate]:
        """Cortes de todos os formatos pedidos: longos primeiro, depois shorts.
        Formatos diferentes podem se sobrepor (um short pode sair de dentro de um corte longo)."""
        candidates: list[ClipCandidate] = []
        for fmt in (ClipFormat.LONG, ClipFormat.SHORT):
            if fmt in formats:
                candidates += self.selectors[fmt].select(video, transcript)
        return candidates

    def _make_clip(
        self, video: SourceVideo, candidate: ClipCandidate, source_file: Path,
        transcript: Transcript,
    ) -> None:
        s = self.settings
        stem = f"{video.id}_{candidate.format.value}_{int(candidate.start)}_{int(candidate.end)}"
        out = s.output_dir / f"{stem}.mp4"
        if candidate.format is ClipFormat.SHORT:
            duration = self._render_short(candidate, source_file, transcript, out)
        else:
            duration = self._render_long(candidate, source_file, transcript, out)
        clip = RenderedClip(candidate, video, out, duration)
        clip.metadata = self.metadata.generate(video, candidate)
        if candidate.format is ClipFormat.LONG:  # Shorts não aceitam thumbnail própria
            try:
                clip.thumbnail_path = self.thumbnails.generate(
                    video, candidate, clip.metadata, s.output_dir / f"{stem}.jpg", source_file
                )
            except Exception:  # thumbnail é opcional: nunca derruba a publicação
                logger.exception("Falha ao gerar a thumbnail de %s; publicando sem ela", video.id)
        self.bus.publish(ClipRendered(clip))
        slot = self._next_slot() if s.publish_schedule_enabled else None
        result = self.publisher.publish(clip, publish_at=slot)
        self.store.record_clip(
            video.id, candidate.format.value, candidate.start, candidate.end,
            clip.metadata.title, result.video_id,
            scheduled_for=slot if result.video_id else None,
        )
        if slot is not None:
            logger.info("Agendado para %s (%s)", slot.astimezone(ZoneInfo(s.publish_timezone)),
                        clip.metadata.title)
        self.bus.publish(ClipPublished(clip, result))

    def _render_long(
        self, candidate: ClipCandidate, source_file: Path, transcript: Transcript, out: Path
    ) -> float:
        s = self.settings
        keep = [(candidate.start, candidate.end)]
        if s.silence_cut_enabled:
            silences = self.silence.detect(source_file, candidate.start, candidate.end)
            relative = plan_keep_ranges(
                candidate.duration, silences, s.silence_min_duration_seconds,
                s.silence_keep_padding_seconds,
            )
            keep = [(candidate.start + a, candidate.start + b) for a, b in relative]
        insert_at = None
        if s.cta_video_path and candidate.duration >= s.cta_min_clip_seconds:
            insert_at = choose_insert_point(
                transcript, candidate.start, candidate.end, s.cta_position_pct
            )
        return self.renderer.render(source_file, keep, out, insert_at=insert_at)

    def _render_short(
        self, candidate: ClipCandidate, source_file: Path, transcript: Transcript, out: Path
    ) -> float:
        """Shorts não passam pelo corte de silêncio: as legendas dependem do tempo original."""
        words = []
        if self.settings.short_captions:
            words = self.aligner.align(source_file, candidate, transcript)
            if not words:
                logger.warning(
                    "Sem palavras para legendar o short %s-%s", candidate.start, candidate.end
                )
        return self.short_renderer.render(source_file, candidate.start, candidate.end, out, words)

    def _next_slot(self) -> datetime | None:
        return next_slot(self.store.scheduled_times(), self.settings)

    def _skip(self, video: SourceVideo, reason: str) -> None:
        self.store.mark(video.id, "skipped", reason)
        self.bus.publish(VideoSkipped(video, reason))
