from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest

from castclipes.config import Settings
from castclipes.models import (
    ClipCandidate,
    ClipFormat,
    ClipMetadata,
    PublishResult,
    RenderedClip,
    SourceVideo,
)
from castclipes.publishing.facebook import FacebookError, FacebookPublisher
from castclipes.publishing.multi import MultiPublisher
from castclipes.publishing.youtube import DryRunPublisher, YouTubePublisher, create_publisher

SETTINGS = {
    "_env_file": None, "facebook_page_id": "123", "facebook_page_access_token": "TOKEN",
    "facebook_api_version": "v23.0",
}


def make_clip(tmp_path, fmt: ClipFormat, size: int = 10, thumb: bool = False) -> RenderedClip:
    path = tmp_path / "clip.mp4"
    path.write_bytes(bytes(range(size)))
    clip = RenderedClip(
        ClipCandidate(0, 30, "assunto", 0.9, format=fmt),
        SourceVideo(id="v", title="t"), path, 30.0,
        ClipMetadata("Título do corte", "Descrição", ("a",)),
    )
    if thumb:
        clip.thumbnail_path = tmp_path / "t.jpg"
        clip.thumbnail_path.write_bytes(b"jpg")
    return clip


def form(request: httpx.Request) -> dict[str, str]:
    """Campos do corpo (urlencoded ou multipart) como dict simples."""
    body = request.content
    if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        return {k: v[0] for k, v in parse_qs(body.decode()).items()}
    fields = {}
    for part in body.split(b"--")[1:-1]:
        head, _, value = part.partition(b"\r\n\r\n")
        if b'name="' in head and b"filename=" not in head:
            name = head.split(b'name="')[1].split(b'"')[0].decode()
            fields[name] = value.rstrip(b"\r\n").decode()
        elif b"filename=" in head:
            fields[head.split(b'name="')[1].split(b'"')[0].decode()] = "<file>"
    return fields


def publisher(handler) -> FacebookPublisher:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FacebookPublisher(Settings(**SETTINGS), client, sleep=lambda s: None)


def test_long_video_uses_chunked_upload_and_publishes(tmp_path):
    calls = []

    def handler(request):
        fields = form(request)
        calls.append((str(request.url), fields))
        phase = fields["upload_phase"]
        if phase == "start":
            return httpx.Response(200, json={
                "upload_session_id": "S", "video_id": "777", "start_offset": "0", "end_offset": "6",
            })
        if phase == "transfer":
            start = int(fields["start_offset"])
            nxt = {0: ("6", "10"), 6: ("10", "10")}[start]
            return httpx.Response(200, json={"start_offset": nxt[0], "end_offset": nxt[1]})
        return httpx.Response(200, json={"success": True})

    result = publisher(handler).publish(make_clip(tmp_path, ClipFormat.LONG, thumb=True))
    assert result.video_id == "777" and result.url == "https://www.facebook.com/watch/?v=777"
    phases = [c[1]["upload_phase"] for c in calls]
    assert phases == ["start", "transfer", "transfer", "finish"]
    assert calls[0][0].startswith("https://graph-video.facebook.com/v23.0/123/videos")
    assert calls[0][1]["file_size"] == "10" and calls[0][1]["access_token"] == "TOKEN"
    finish = calls[-1][1]
    assert finish["published"] == "true" and finish["title"] == "Título do corte"
    assert "Descrição" in finish["description"] and finish["thumb"] == "<file>"


def test_scheduled_long_video_sends_schedule_fields(tmp_path):
    seen = {}

    def handler(request):
        fields = form(request)
        if fields["upload_phase"] == "start":
            return httpx.Response(200, json={
                "upload_session_id": "S", "video_id": "1", "start_offset": "0", "end_offset": "0",
            })
        seen.update(fields)
        return httpx.Response(200, json={"success": True})

    when = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    publisher(handler).publish(make_clip(tmp_path, ClipFormat.LONG), publish_at=when)
    assert seen["published"] == "false"
    assert seen["scheduled_publish_time"] == str(int(when.timestamp()))
    assert seen["unpublished_content_type"] == "SCHEDULED"


def test_short_is_published_as_reel(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if "upload.example" in str(request.url):
            assert request.headers["authorization"] == "OAuth TOKEN"
            assert request.headers["offset"] == "0" and request.headers["file_size"] == "10"
            assert request.content == bytes(range(10))
            return httpx.Response(200, json={"success": True})
        fields = form(request)
        if fields["upload_phase"] == "start":
            return httpx.Response(200, json={
                "video_id": "999", "upload_url": "https://upload.example/rupload",
            })
        assert fields["video_id"] == "999" and fields["video_state"] == "PUBLISHED"
        assert "Título do corte" in fields["description"]
        return httpx.Response(200, json={"success": True})

    result = publisher(handler).publish(make_clip(tmp_path, ClipFormat.SHORT))
    assert result.url == "https://www.facebook.com/reel/999"
    assert str(calls[0].url).startswith("https://graph.facebook.com/v23.0/123/video_reels")
    assert len(calls) == 3


def test_scheduled_reel_uses_scheduled_state(tmp_path):
    finish = {}

    def handler(request):
        if "upload.example" in str(request.url):
            return httpx.Response(200, json={"success": True})
        fields = form(request)
        if fields["upload_phase"] == "start":
            return httpx.Response(200, json={"video_id": "9", "upload_url": "https://upload.example/x"})
        finish.update(fields)
        return httpx.Response(200, json={"success": True})

    when = datetime(2030, 1, 1, tzinfo=UTC)
    publisher(handler).publish(make_clip(tmp_path, ClipFormat.SHORT), publish_at=when)
    assert finish["video_state"] == "SCHEDULED"
    assert finish["scheduled_publish_time"] == str(int(when.timestamp()))


def test_api_error_raises_with_meta_message(tmp_path):
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "Token expirado", "code": 190}})

    with pytest.raises(FacebookError, match="Token expirado"):
        publisher(handler).publish(make_clip(tmp_path, ClipFormat.SHORT))


def test_server_errors_are_retried_then_succeed(tmp_path):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503, text="indisponível")
        if "upload.example" in str(request.url):
            return httpx.Response(200, json={"success": True})
        fields = form(request)
        if fields["upload_phase"] == "start":
            return httpx.Response(200, json={"video_id": "9", "upload_url": "https://upload.example/x"})
        return httpx.Response(200, json={"success": True})

    assert publisher(handler).publish(make_clip(tmp_path, ClipFormat.SHORT)).video_id == "9"
    assert len(attempts) == 5


class Stub:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    def publish(self, clip, publish_at=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_multi_publisher_keeps_primary_result_and_adds_links(tmp_path):
    clip = make_clip(tmp_path, ClipFormat.SHORT)
    primary = Stub(PublishResult("yt1", "https://youtu.be/yt1"))
    fb = Stub(PublishResult("fb1", "https://www.facebook.com/reel/fb1"))
    result = MultiPublisher(primary, {"facebook": fb}).publish(clip)
    assert result.video_id == "yt1" and result.extra == {"facebook": "https://www.facebook.com/reel/fb1"}


def test_multi_publisher_swallows_extra_failures(tmp_path):
    clip = make_clip(tmp_path, ClipFormat.SHORT)
    primary = Stub(PublishResult("yt1", "u"))
    result = MultiPublisher(primary, {"facebook": Stub(error=RuntimeError("boom"))}).publish(clip)
    assert result.video_id == "yt1" and result.extra == {}


def test_multi_publisher_does_not_post_extra_when_primary_fails(tmp_path):
    clip = make_clip(tmp_path, ClipFormat.SHORT)
    fb = Stub(PublishResult("fb1", "u"))
    with pytest.raises(RuntimeError):
        MultiPublisher(Stub(error=RuntimeError("yt caiu")), {"facebook": fb}).publish(clip)
    assert fb.calls == 0


def test_factory_wiring(tmp_path):
    assert isinstance(create_publisher(Settings(_env_file=None)), DryRunPublisher)
    dry = Settings(**SETTINGS, facebook_enabled=True)
    assert isinstance(create_publisher(dry), DryRunPublisher)  # dry_run nunca envia
    live = Settings(_env_file=None, publish_mode="youtube")
    assert isinstance(create_publisher(live), YouTubePublisher)
    both = Settings(**SETTINGS, publish_mode="youtube", facebook_enabled=True)
    assert isinstance(create_publisher(both), MultiPublisher)
    with pytest.raises(ValueError, match="FACEBOOK_PAGE_ID"):
        create_publisher(Settings(_env_file=None, publish_mode="youtube", facebook_enabled=True))
