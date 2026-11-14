"""Fonte de vídeos via feed RSS/Atom do YouTube."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from time import struct_time

import feedparser

from ..models import SourceVideo

logger = logging.getLogger(__name__)

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


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
    def __init__(self, channel_ids: list[str], max_age_hours: int) -> None:
        self._channel_ids = channel_ids
        self._max_age = timedelta(hours=max_age_hours)

    def latest(self) -> Iterable[SourceVideo]:
        cutoff = datetime.now(UTC) - self._max_age
        for channel_id in self._channel_ids:
            try:
                videos = parse_feed(_fetch(channel_id), channel_id)
            except Exception:
                logger.exception("Falha ao ler o feed do canal %s", channel_id)
                continue
            for video in videos:
                if video.published_at is None or video.published_at >= cutoff:
                    yield video


def _fetch(channel_id: str) -> bytes:
    import httpx

    response = httpx.get(FEED_URL.format(channel_id=channel_id), timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.content
