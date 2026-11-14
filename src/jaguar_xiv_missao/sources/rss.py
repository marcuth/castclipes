"""Fonte de vídeos via feed RSS/Atom do YouTube."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from time import struct_time

import feedparser

from ..models import SourceVideo

logger = logging.getLogger(__name__)

FEED_URL = "https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"
PLAYLIST_URL = "https://www.youtube.com/playlist?list={playlist_id}"
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


def ytdlp_playlist(playlist_id: str, limit: int) -> list[SourceVideo]:
    """Reserva do RSS: lista os vídeos mais recentes da playlist via yt-dlp (sem baixar nada).

    A listagem rasa não traz data nem descrição; o `enrich` completa isso depois, e o pipeline
    descarta o que passou de SOURCE_MAX_AGE_HOURS.
    """
    from yt_dlp import YoutubeDL

    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": "in_playlist", "playlistend": limit}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(PLAYLIST_URL.format(playlist_id=playlist_id), download=False)
    return [
        SourceVideo(
            id=entry["id"],
            title=entry.get("title") or "",
            channel_id=entry.get("channel_id") or "",
            channel_title=entry.get("channel") or entry.get("uploader") or "",
        )
        for entry in (info or {}).get("entries") or []
        if entry and entry.get("id")
    ]


class RssVideoSource:
    def __init__(
        self,
        playlist_ids: list[str],
        max_age_hours: int,
        fallback_limit: int = 5,
        fallback: Callable[[str, int], list[SourceVideo]] | None = ytdlp_playlist,
    ) -> None:
        self._playlist_ids = [live_playlist_id(p) for p in playlist_ids]
        self._max_age = timedelta(hours=max_age_hours)
        self._fallback_limit = fallback_limit
        self._fallback = fallback

    def latest(self) -> Iterable[SourceVideo]:
        cutoff = datetime.now(UTC) - self._max_age
        for playlist_id in self._playlist_ids:
            videos = self._read(playlist_id)
            if videos is None:
                continue
            for video in videos:
                if video.published_at is None or video.published_at >= cutoff:
                    yield video


    def _read(self, playlist_id: str) -> list[SourceVideo] | None:
        try:
            return parse_feed(_fetch(playlist_id))
        except Exception as exc:  # noqa: BLE001 - qualquer falha do feed cai no yt-dlp
            logger.warning("Feed RSS da playlist %s indisponível (%s)", playlist_id, exc)
        if self._fallback is None:
            return None
        try:
            videos = self._fallback(playlist_id, self._fallback_limit)
        except Exception:
            logger.exception("Falha ao listar a playlist %s também via yt-dlp", playlist_id)
            return None
        logger.info("Playlist %s lida via yt-dlp (%d vídeos)", playlist_id, len(videos))
        return videos


def _fetch(playlist_id: str) -> bytes:
    import httpx

    response = httpx.get(FEED_URL.format(playlist_id=playlist_id), timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.content
