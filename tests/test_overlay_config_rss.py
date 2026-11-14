from jaguar_xiv_missao.config import Settings
from jaguar_xiv_missao.editing.overlay import compute_position
from jaguar_xiv_missao.sources.rss import live_playlist_id, parse_feed

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
  <title>TV do MBL</title>
  <entry>
    <yt:videoId>abc123DEF45</yt:videoId><yt:channelId>UC1</yt:channelId>
    <title>Live de hoje</title><published>2026-11-14T10:00:00+00:00</published>
    <media:group><media:description>Descrição</media:description></media:group>
  </entry>
</feed>"""


def test_positions():
    assert compute_position("top-right", (1920, 1080), (100, 50), 24) == (1796, 24)
    assert compute_position("bottom-left", (1920, 1080), (100, 50), 24) == (24, 1006)
    assert compute_position("center", (1920, 1080), (100, 50), 0) == (910, 515)


def test_settings_csv_and_empty_paths(monkeypatch):
    monkeypatch.setenv("SOURCE_LIVE_PLAYLIST_IDS", "UULV1, UC2")
    monkeypatch.setenv("WATERMARK_PATH", "")
    monkeypatch.setenv("CLIP_MIN_SECONDS", "300")
    s = Settings(_env_file=None)
    assert s.source_live_playlist_ids == ["UULV1", "UC2"]
    assert s.watermark_path is None
    assert s.clip_min_seconds == 300 and s.clip_max_seconds == 2400


def test_parse_feed():
    [video] = parse_feed(FEED)
    assert video.id == "abc123DEF45" and video.channel_title == "TV do MBL"
    assert video.published_at is not None and video.channel_id == "UC1"


def test_live_playlist_id_accepts_channel_or_playlist():
    assert live_playlist_id("UCZYyHef3eBoBEztAOY_Fe_g") == "UULVZYyHef3eBoBEztAOY_Fe_g"
    assert live_playlist_id(" UULVabc ") == "UULVabc"


def test_overlay_size_stretch_fills_video_and_width_keeps_aspect():
    from jaguar_xiv_missao.editing.overlay import overlay_size

    assert overlay_size("stretch", (1280, 720), (1920, 1080), 0.14) == (1280, 720)
    assert overlay_size("stretch", (1280, 720), (500, 500), 0.14) == (1280, 720)
    assert overlay_size("width", (1280, 720), (200, 100), 0.5) == (640, 320)


def test_choose_insert_point_prefers_pause_near_target():
    from jaguar_xiv_missao.editing.insertion import choose_insert_point
    from jaguar_xiv_missao.models import Transcript, TranscriptSegment

    segs = [TranscriptSegment(i * 10.0, i * 10.0 + 9.5, f"s{i}") for i in range(20)]
    segs[9] = TranscriptSegment(90.0, 97.0, "pausa longa depois")  # fim 97, próxima começa em 100
    transcript = Transcript(segs, "test")
    assert choose_insert_point(transcript, 0, 200, 0.5) == 97.0
    assert choose_insert_point(Transcript([], "test"), 0, 200) is None


def test_to_relative_skips_removed_silence():
    from jaguar_xiv_missao.editing.insertion import to_relative

    keep = [(100.0, 110.0), (115.0, 130.0)]
    assert to_relative(keep, 105.0) == 5.0
    assert to_relative(keep, 112.0) == 10.0  # dentro do silêncio removido
    assert to_relative(keep, 120.0) == 15.0
