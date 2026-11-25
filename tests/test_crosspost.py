import json
from datetime import UTC, datetime, timedelta

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
from castclipes.publishing.crosspost import CrosspostQueue
from castclipes.publishing.graph import GraphError
from castclipes.publishing.instagram import InstagramPublisher
from castclipes.publishing.threads import ThreadsPublisher
from castclipes.publishing.youtube import DryRunPublisher, YouTubePublisher, create_publisher
from castclipes.storage.state import StateStore

T0 = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
CREDS = {
    "_env_file": None, "facebook_page_id": "123", "facebook_page_access_token": "PT",
    "instagram_user_id": "ig1", "threads_user_id": "th1", "threads_access_token": "TT",
}


def make_clip(tmp_path, fmt=ClipFormat.SHORT) -> RenderedClip:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"0123456789")
    return RenderedClip(
        ClipCandidate(10, 40, "assunto", 0.9, format=fmt), SourceVideo(id="vid", title="Live"),
        path, 30.0, ClipMetadata("Título", "Descrição longa", ("tag",)),
    )


def body(request: httpx.Request) -> dict[str, str]:
    from urllib.parse import parse_qs

    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


# ---------- Instagram ----------
def test_instagram_reel_resumable_flow(tmp_path):
    seen = []
    polls = iter(["IN_PROGRESS", "FINISHED"])

    def handler(request):
        url = str(request.url)
        seen.append((request.method, url.split("?")[0]))
        if url.startswith("https://rupload.example"):
            assert request.headers["authorization"] == "OAuth PT"
            assert request.headers["file_size"] == "10" and request.content == b"0123456789"
            return httpx.Response(200, json={"success": True})
        if request.method == "GET" and "status_code" in url:
            return httpx.Response(200, json={"status_code": next(polls)})
        if request.method == "GET":
            return httpx.Response(200, json={"permalink": "https://instagram.com/reel/abc"})
        if url.endswith("/ig1/media"):
            data = body(request)
            assert data["media_type"] == "REELS" and data["upload_type"] == "resumable"
            assert data["caption"].startswith("Título\n\nDescrição")
            return httpx.Response(200, json={"id": "C1", "uri": "https://rupload.example/C1"})
        assert url.endswith("/ig1/media_publish") and body(request)["creation_id"] == "C1"
        return httpx.Response(200, json={"id": "M1"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pub = InstagramPublisher(Settings(**CREDS), client, sleep=lambda s: None)
    result = pub.publish(make_clip(tmp_path))
    assert result.video_id == "M1" and result.url == "https://instagram.com/reel/abc"
    assert pub.supports == frozenset({ClipFormat.SHORT})


def test_instagram_processing_error_raises(tmp_path):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"status_code": "ERROR", "status": "formato"})
        if str(request.url).startswith("https://rupload"):
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"id": "C1", "uri": "https://rupload.example/C1"})

    pub = InstagramPublisher(
        Settings(**CREDS), httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None
    )
    with pytest.raises(GraphError, match="ERROR"):
        pub.publish(make_clip(tmp_path))


# ---------- Threads ----------
def test_threads_posts_text_with_youtube_link(tmp_path):
    calls = []

    def handler(request):
        url = str(request.url).split("?")[0]
        calls.append(url)
        if url.endswith("/refresh_access_token"):
            assert request.url.params["grant_type"] == "th_refresh_token"
            assert request.url.params["access_token"] == "TT"
            return httpx.Response(200, json={"access_token": "TT2", "expires_in": 5184000})
        if request.method == "GET":
            return httpx.Response(200, json={"permalink": "https://threads.net/@x/post/1"})
        if url.endswith("/th1/threads"):
            data = body(request)
            assert data["media_type"] == "TEXT" and data["text"] == "Título"
            assert data["link_attachment"] == "https://youtu.be/yt1"
            assert data["access_token"] == "TT2"
            return httpx.Response(200, json={"id": "CR"})
        assert body(request)["creation_id"] == "CR"
        return httpx.Response(200, json={"id": "P1"})

    clip = make_clip(tmp_path)
    clip.extra["youtube_url"] = "https://youtu.be/yt1"
    pub = ThreadsPublisher(
        Settings(**CREDS, data_dir=tmp_path / "data"),
        httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None
    )
    assert pub.publish(clip).url == "https://threads.net/@x/post/1"
    with pytest.raises(GraphError, match="link do YouTube"):
        pub.publish(make_clip(tmp_path))


# ---------- fila ----------
class Primary:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def publish(self, clip, publish_at=None):
        self.calls.append(publish_at)
        if self.error:
            raise self.error
        return self.result


class Net:
    def __init__(self, supports, native=False, fail=0, delay=timedelta(0)):
        self.supports, self.native_schedule, self.fail = frozenset(supports), native, fail
        self.schedule_delay = delay
        self.calls: list[tuple[RenderedClip, datetime | None]] = []

    def publish(self, clip, publish_at=None):
        self.calls.append((clip, publish_at))
        if self.fail:
            self.fail -= 1
            raise GraphError("boom")
        return PublishResult("id", f"https://net/{len(self.calls)}")


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def store(tmp_path):
    s = StateStore(tmp_path / "db.sqlite")
    yield s
    s.close()


def queue(store, primary, networks, clock, **kw):
    return CrosspostQueue(primary, networks, store, now=clock, **kw)


ALL = {ClipFormat.LONG, ClipFormat.SHORT}


def test_publishes_to_every_network_and_returns_links(tmp_path, store):
    clip = make_clip(tmp_path)
    fb, ig = Net(ALL, native=True), Net({ClipFormat.SHORT})
    result = queue(
        store, Primary(PublishResult("yt1", "https://youtu.be/yt1")),
        {"facebook": fb, "instagram": ig}, Clock(T0),
    ).publish(clip)
    assert result.video_id == "yt1"
    assert result.extra == {"facebook": "https://net/1", "instagram": "https://net/1"}
    assert fb.calls[0][0].path == clip.path and fb.calls[0][0].extra["youtube_url"] == "https://youtu.be/yt1"
    assert fb.calls[0][0].metadata.title == "Título"


def test_network_skips_unsupported_format(tmp_path, store):
    ig = Net({ClipFormat.SHORT})
    result = queue(store, Primary(PublishResult("yt", "u")), {"instagram": ig}, Clock(T0)).publish(
        make_clip(tmp_path, ClipFormat.LONG)
    )
    assert ig.calls == [] and result.extra == {}


def test_failed_network_is_retried_later_without_touching_primary(tmp_path, store):
    clock, primary = Clock(T0), Primary(PublishResult("yt", "u"))
    threads = Net(ALL, fail=1)
    q = queue(store, primary, {"threads": threads}, clock, retry_minutes=15)
    result = q.publish(make_clip(tmp_path))
    assert result.extra == {} and len(primary.calls) == 1
    assert q.flush() == 0  # ainda não venceu
    clock.now = T0 + timedelta(minutes=16)
    assert q.flush() == 1
    assert len(primary.calls) == 1 and len(threads.calls) == 2
    assert store.crosspost_urls("vid", "short", 10, 40) == {"threads": "https://net/2"}
    assert q.flush() == 0  # concluído: não reenvia


def test_gives_up_after_max_attempts(tmp_path, store):
    clock = Clock(T0)
    net = Net(ALL, fail=99)
    q = queue(store, Primary(PublishResult("yt", "u")), {"threads": net}, clock,
              max_attempts=2, retry_minutes=1)
    q.publish(make_clip(tmp_path))
    clock.now += timedelta(hours=1)
    q.flush()
    clock.now += timedelta(hours=1)
    q.flush()
    assert len(net.calls) == 2 and store.due_crossposts(clock.now + timedelta(days=9)) == []


def test_non_native_network_waits_for_the_queue_slot(tmp_path, store):
    slot = T0 + timedelta(hours=3)
    clock = Clock(T0)
    threads = Net(ALL, delay=timedelta(minutes=5))
    ig = Net({ClipFormat.SHORT})
    fb = Net(ALL, native=True)
    q = queue(store, Primary(PublishResult("yt", "u")), {"threads": threads, "instagram": ig, "facebook": fb}, clock)
    q.publish(make_clip(tmp_path), publish_at=slot)
    assert [c[1] for c in fb.calls] == [slot]  # Facebook agenda sozinho, já
    assert ig.calls == [] and threads.calls == []
    clock.now = slot - timedelta(minutes=1)
    assert q.flush() == 0
    clock.now = slot
    q.flush()
    assert len(ig.calls) == 1 and ig.calls[0][1] is None and threads.calls == []
    clock.now = slot + timedelta(minutes=5)
    q.flush()
    assert len(threads.calls) == 1


def test_native_schedule_in_the_past_publishes_now(tmp_path, store):
    clock = Clock(T0)
    fb = Net(ALL, native=True, fail=1)
    q = queue(store, Primary(PublishResult("yt", "u")), {"facebook": fb}, clock, retry_minutes=1)
    q.publish(make_clip(tmp_path), publish_at=T0 + timedelta(minutes=30))
    clock.now = T0 + timedelta(minutes=29)  # faltam 1 min: menos que o mínimo do Facebook
    q.flush()
    assert fb.calls[0][1] == T0 + timedelta(minutes=30) and fb.calls[1][1] is None


def test_missing_file_gives_up(tmp_path, store):
    clip = make_clip(tmp_path)
    net = Net(ALL, fail=1)
    clock = Clock(T0)
    q = queue(store, Primary(PublishResult("yt", "u")), {"threads": net}, clock, retry_minutes=1)
    q.publish(clip)
    clip.path.unlink()
    clock.now += timedelta(hours=1)
    assert q.flush() == 0 and len(net.calls) == 1
    assert store.due_crossposts(clock.now + timedelta(days=9)) == []


def test_primary_failure_enqueues_nothing(tmp_path, store):
    net = Net(ALL)
    with pytest.raises(RuntimeError):
        queue(store, Primary(error=RuntimeError("yt caiu")), {"threads": net}, Clock(T0)).publish(
            make_clip(tmp_path)
        )
    assert net.calls == [] and store.due_crossposts(T0 + timedelta(days=1)) == []


def test_dry_run_primary_enqueues_nothing(tmp_path, store):
    net = Net(ALL)
    queue(store, Primary(PublishResult(None, None, dry_run=True)), {"threads": net}, Clock(T0)).publish(
        make_clip(tmp_path)
    )
    assert net.calls == []


def test_same_clip_is_not_enqueued_twice(tmp_path, store):
    net = Net(ALL)
    q = queue(store, Primary(PublishResult("yt", "u")), {"threads": net}, Clock(T0))
    clip = make_clip(tmp_path)
    q.publish(clip)
    q.publish(clip)
    assert len(net.calls) == 1


def test_payload_roundtrip_is_json(tmp_path, store):
    q = queue(store, Primary(PublishResult("yt", "u")), {"threads": Net(ALL, fail=1)}, Clock(T0))
    q.publish(make_clip(tmp_path))
    row = store._db.execute("SELECT payload FROM crossposts").fetchone()[0]
    assert json.loads(row)["extra"]["youtube_url"] == "u"


# ---------- fábrica ----------
def test_factory_wiring(store):
    assert isinstance(create_publisher(Settings(_env_file=None)), DryRunPublisher)
    dry = Settings(**CREDS, crosspost_networks=["facebook"])
    assert isinstance(create_publisher(dry, store), DryRunPublisher)  # dry_run nunca envia
    assert isinstance(create_publisher(Settings(_env_file=None, publish_mode="youtube")), YouTubePublisher)
    both = Settings(**CREDS, publish_mode="youtube", crosspost_networks=["facebook", "instagram", "threads"])
    queue_ = create_publisher(both, store)
    assert isinstance(queue_, CrosspostQueue)
    with pytest.raises(ValueError, match="StateStore"):
        create_publisher(both)
    missing = Settings(_env_file=None, publish_mode="youtube", crosspost_networks=["threads"])
    with pytest.raises(ValueError, match="THREADS_USER_ID"):
        create_publisher(missing, store)
    with pytest.raises(ValueError):
        Settings(_env_file=None, crosspost_networks=["tiktok"])
