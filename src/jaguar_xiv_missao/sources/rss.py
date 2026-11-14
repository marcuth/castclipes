"""Fonte de vídeos via feed RSS/Atom do YouTube."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from time import struct_time

import feedparser

from ..models import SourceVideo

logger = logging.getLogger(__name__)

FEED_URL = "https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"
LIVES_PREFIX = "UULV"  # playlist automática com as lives de um canal (UC<x> -> UULV<x>)


def live_playlist_id(value: str) -> str:
    """Aceita ID de playlist de lives (UULV...) ou ID de canal (UC...)."""
    value = value.strip()
    return LIVES_PREFIX + value[2:] if value.startswith("UC") else value



def _to_dt(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime(*value[:6], tzinfo=UTC)


def parse_feed(content: str | bytes, channel_id: str = "") -> list[SourceVideo]:
    feed = feedparser.parse(content)
    channel_title = feed.feed.get("title", "")
    videos: list[SourceVideo] = []
    for entry in feed.entries:
        video_id = entry.get("yt_videoid")
        if not video_id:
            continue
        videos.append(
            SourceVideo(
                id=video_id,
                title=entry.get("title", ""),
                description=entry.get("summary", ""),
                channel_id=entry.get("yt_channelid", channel_id),
                channel_title=channel_title,
                published_at=_to_dt(entry.get("published_parsed")),
            )
        )
    return videos


class RssVideoSource:
    def __init__(self, playlist_ids: list[str], max_age_hours: int) -> None:
        self._playlist_ids = [live_playlist_id(p) for p in playlist_ids]
        self._max_age = timedelta(hours=max_age_hours)

    def latest(self) -> Iterable[SourceVideo]:
        cutoff = datetime.now(UTC) - self._max_age
        for playlist_id in self._playlist_ids:
            try:
                videos = parse_feed(_fetch(playlist_id))
            except Exception:
                logger.exception("Falha ao ler o feed da playlist %s", playlist_id)
                continue
            for video in videos:
                if video.published_at is None or video.published_at >= cutoff:
                    yield video


def _fetch(playlist_id: str) -> bytes:
    import httpx

    response = httpx.get(FEED_URL.format(playlist_id=playlist_id), timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.content
