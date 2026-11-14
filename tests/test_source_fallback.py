from datetime import UTC, datetime, timedelta

from jaguar_xiv_missao.models import SourceVideo
from jaguar_xiv_missao.sources import rss
from jaguar_xiv_missao.sources.rss import RssVideoSource


def _boom(_playlist_id):
    raise RuntimeError("404")


def test_falls_back_to_ytdlp_when_rss_fails(monkeypatch):
    monkeypatch.setattr(rss, "_fetch", _boom)
    calls = []

    def fallback(playlist_id, limit):
        calls.append((playlist_id, limit))
        return [SourceVideo(id="abc", title="live")]

    source = RssVideoSource(["UULVx"], 48, fallback_limit=7, fallback=fallback)
    assert [v.id for v in source.latest()] == ["abc"]
    assert calls == [("UULVx", 7)]


def test_no_fallback_configured_skips_playlist(monkeypatch):
    monkeypatch.setattr(rss, "_fetch", _boom)
    assert list(RssVideoSource(["UULVx"], 48, fallback=None).latest()) == []


def test_failing_fallback_does_not_stop_other_playlists(monkeypatch):
    monkeypatch.setattr(rss, "_fetch", _boom)

    def fallback(playlist_id, limit):
        if playlist_id == "UULVbad":
            raise RuntimeError("yt-dlp falhou")
        return [SourceVideo(id=playlist_id, title="t")]

    source = RssVideoSource(["UULVbad", "UULVok"], 48, fallback=fallback)
    assert [v.id for v in source.latest()] == ["UULVok"]


def test_pipeline_rejects_old_videos(tmp_path):
    from tests.test_pipeline import build, good_transcript

    old = SourceVideo(
        id="old", title="t", duration_seconds=3600, live_status="was_live",
        published_at=datetime.now(UTC) - timedelta(hours=100),
    )
    pipeline = build(tmp_path, transcript=good_transcript())[0]
    assert "antigo demais" in pipeline._reject_reason(old)
    assert pipeline._reject_reason(old, force=True) is None
