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
