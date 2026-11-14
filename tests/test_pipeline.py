"""Teste de integração do pipeline com dublês no lugar de rede, IA e vídeo."""

from dataclasses import replace
from pathlib import Path

from jaguar_xiv_missao.analysis.triage import TriageResult
from jaguar_xiv_missao.config import Settings
from jaguar_xiv_missao.editing.silence import NullSilenceDetector
from jaguar_xiv_missao.events import ClipPublished, EventBus, VideoSkipped, VideoWaiting
from jaguar_xiv_missao.models import (
    ClipCandidate,
    ClipMetadata,
    PublishResult,
    SourceVideo,
    Transcript,
    TranscriptSegment,
)
from jaguar_xiv_missao.pipeline import Pipeline
from jaguar_xiv_missao.storage.state import StateStore
from jaguar_xiv_missao.thumbnails.base import NullThumbnailGenerator


class FakeSource:
    def __init__(self, videos): self.videos = videos
    def latest(self): return self.videos


class FakeDownloader:
    def enrich(self, v): return replace(v, duration_seconds=self.duration, live_status=self.live_status)
    def __init__(self, duration, live_status="was_live"):
        self.duration = duration
        self.live_status = live_status
        self.downloads = 0
        self.cleaned = []

    def download_video(self, v):
        self.downloads += 1
        return Path("x.mp4")

    def cleanup(self, video_id): self.cleaned.append(video_id)


class FakeTranscriber:
    name = "fake"
    def __init__(self, transcript): self.transcript = transcript
    def fetch(self, v): return self.transcript


class FakeTriage:
    def __init__(self, ok): self.ok = ok
    def evaluate(self, v): return TriageResult(self.ok, 0.9 if self.ok else 0.1, "r")


class FakeSelector:
    def select(self, v, t): return [ClipCandidate(10, 700, "assunto", 0.9)]


class FakeRenderer:
    def render(self, src, keep, out, insert_at=None): return 650.0


class FakeMetadata:
    def generate(self, v, c): return ClipMetadata("TITULO", "desc", ("tag",))


class FakePublisher:
    def __init__(self): self.published = []
    def publish(self, clip, publish_at=None):
        self.published.append(clip)
        self.slots = [*getattr(self, 'slots', []), publish_at]
        return PublishResult("yt1", "https://youtu.be/yt1")


def build(
    tmp_path, *, transcript, duration=1800, triage_ok=True, fallback=None, live_status="was_live", **settings
):
    s = Settings(_env_file=None, data_dir=tmp_path, **settings)
    bus, events = EventBus(), []
    bus.subscribe_all(events.append)
    video = SourceVideo(id="v1", title="Renan Santos")
    publisher = FakePublisher()
    pipe = Pipeline(
        settings=s, source=FakeSource([video]), downloader=FakeDownloader(duration, live_status),
        primary_transcriber=FakeTranscriber(transcript),
        fallback_transcriber=FakeTranscriber(fallback), triage=FakeTriage(triage_ok),
        selector=FakeSelector(), silence=NullSilenceDetector(), renderer=FakeRenderer(),
        metadata=FakeMetadata(), thumbnails=NullThumbnailGenerator(), publisher=publisher,
        store=StateStore(tmp_path / "s.db"), bus=bus,
    )
    return pipe, events, publisher


def good_transcript():
    text = "Renan Santos fala do MBL e do Partido Missão. " * 3
    return Transcript([TranscriptSegment(0, 900, text)], "youtube")


def test_happy_path_publishes_once(tmp_path):
    pipe, events, publisher = build(tmp_path, transcript=good_transcript())
    pipe.run_once()
    pipe.run_once()  # segunda rodada não reprocessa
    assert len(publisher.published) == 1
    assert pipe.downloader.downloads == 1 and pipe.downloader.cleaned == ["v1"]
    assert any(isinstance(e, ClipPublished) for e in events)


def test_skips_short_source(tmp_path):
    pipe, events, publisher = build(tmp_path, transcript=good_transcript(), duration=120)
    pipe.run_once()
    assert not publisher.published
    assert any(isinstance(e, VideoSkipped) and "curto" in e.reason for e in events)


def test_no_captions_and_triage_rejects(tmp_path):
    pipe, events, publisher = build(tmp_path, transcript=None, triage_ok=False, live_caption_wait_minutes=0)
    pipe.run_once()
    assert not publisher.published
    assert any(isinstance(e, VideoSkipped) and "triagem" in e.reason for e in events)


def test_no_captions_triage_ok_uses_whisper(tmp_path):
    pipe, _, publisher = build(
        tmp_path, transcript=None, fallback=good_transcript(), live_caption_wait_minutes=0
    )
    pipe.run_once()
    assert len(publisher.published) == 1


def test_daily_limit_defers_video(tmp_path):
    pipe, _, publisher = build(tmp_path, transcript=good_transcript(), max_publish_per_day=0)
    pipe.run_once()
    assert not publisher.published and not pipe.store.seen("v1")
    assert pipe.downloader.downloads == 0  # nada baixado quando o limite já estourou


def test_live_in_progress_waits_without_marking(tmp_path):
    for status in ("is_live", "is_upcoming", "post_live"):
        pipe, events, publisher = build(tmp_path / status, transcript=good_transcript(), live_status=status)
        pipe.run_once()
        assert not publisher.published and not pipe.store.seen("v1")
        assert any(isinstance(e, VideoWaiting) for e in events)
        assert pipe.downloader.downloads == 0


def test_regular_upload_is_always_ignored(tmp_path):
    pipe, events, publisher = build(tmp_path, transcript=good_transcript(), live_status="not_live")
    pipe.run_once()
    assert not publisher.published
    assert any(isinstance(e, VideoSkipped) and "live" in e.reason for e in events)


def test_ended_live_without_captions_waits_before_whisper(tmp_path):
    pipe, events, publisher = build(tmp_path, transcript=None, fallback=good_transcript())
    pipe.run_once()
    assert not publisher.published and not pipe.store.seen("v1")
    assert pipe.store.waiting_since("v1") is not None
    assert any(isinstance(e, VideoWaiting) for e in events)


def test_ended_live_without_captions_uses_whisper_after_wait(tmp_path):
    pipe, _, publisher = build(
        tmp_path, transcript=None, fallback=good_transcript(), live_caption_wait_minutes=0
    )
    pipe.run_once()
    assert len(publisher.published) == 1


def test_manual_process_forces_non_live(tmp_path):
    pipe, _, publisher = build(tmp_path, transcript=good_transcript(), live_status="not_live")
    pipe.process(SourceVideo(id="v1", title="t"), force=True)
    assert len(publisher.published) == 1
