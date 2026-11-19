"""Publicação numa Página do Facebook via Graph API.

- Corte longo (16:9): `/{page}/videos` com upload em partes (start / transfer / finish).
- Short (9:16): Reels da Página, `/{page}/video_reels` (start / upload / finish).

Precisa de um token de acesso **da Página** (de longa duração) com `pages_manage_posts`,
`pages_read_engagement` e `publish_video`. Veja docs/publishing.md.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import httpx

from ..config import Settings
from ..models import ClipFormat, PublishResult, RenderedClip
from .graph import UPLOAD_TIMEOUT, GraphClient

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com"
GRAPH_VIDEO = "https://graph-video.facebook.com"


class FacebookPublisher:
    supports = frozenset({ClipFormat.LONG, ClipFormat.SHORT})
    native_schedule = True
    """O Facebook agenda sozinho (`scheduled_publish_time`): o envio é feito já, com o horário."""

    def __init__(
        self, settings: Settings, client: httpx.Client | None = None, sleep=time.sleep
    ) -> None:
        self._page = settings.facebook_page_id
        self._version = settings.facebook_api_version
        self._api = GraphClient(settings.facebook_page_access_token, client, sleep)

    # ---------- API ----------
    def publish(self, clip: RenderedClip, publish_at: datetime | None = None) -> PublishResult:
        meta = clip.metadata
        if meta is None:
            raise ValueError("RenderedClip sem metadata")
        if clip.candidate.format is ClipFormat.SHORT:
            return self._publish_reel(clip, meta.title, meta.description, publish_at)
        return self._publish_video(clip, meta.title, meta.description, publish_at)

    # ---------- vídeo (corte longo) ----------
    def _publish_video(
        self, clip: RenderedClip, title: str, description: str, publish_at: datetime | None
    ) -> PublishResult:
        url = f"{GRAPH_VIDEO}/{self._version}/{self._page}/videos"
        path = Path(clip.path)
        size = path.stat().st_size
        started = self._api.post(url, data={"upload_phase": "start", "file_size": str(size)})
        session, video_id = started["upload_session_id"], started["video_id"]
        start, end = int(started["start_offset"]), int(started["end_offset"])
        with path.open("rb") as file:
            while start < end:
                file.seek(start)
                chunk = file.read(end - start)
                reply = self._api.post(
                    url,
                    data={
                        "upload_phase": "transfer", "upload_session_id": session,
                        "start_offset": str(start),
                    },
                    files={"video_file_chunk": ("chunk", chunk, "application/octet-stream")},
                    timeout=UPLOAD_TIMEOUT,
                )
                start, end = int(reply["start_offset"]), int(reply["end_offset"])
                logger.info("Facebook: upload %.0f%%", 100 * start / max(size, 1))
        data = {
            "upload_phase": "finish", "upload_session_id": session,
            "title": title, "description": f"{title}\n\n{description}",
            **self._schedule_fields(publish_at, reel=False),
        }
        files = None
        thumb = clip.thumbnail_path
        if thumb and Path(thumb).exists():
            files = {"thumb": (Path(thumb).name, Path(thumb).read_bytes(), "image/jpeg")}
        self._api.post(url, data=data, files=files)
        return PublishResult(video_id, f"https://www.facebook.com/watch/?v={video_id}")

    # ---------- Reels (short) ----------
    def _publish_reel(
        self, clip: RenderedClip, title: str, description: str, publish_at: datetime | None
    ) -> PublishResult:
        url = f"{GRAPH}/{self._version}/{self._page}/video_reels"
        path = Path(clip.path)
        size = path.stat().st_size
        started = self._api.post(url, data={"upload_phase": "start"})
        video_id, upload_url = started["video_id"], started["upload_url"]
        self._api.post(
            upload_url,
            content=path.read_bytes(),
            headers={
                "Authorization": f"OAuth {self._api.token}", "offset": "0",
                "file_size": str(size),
            },
            auth_in_body=False,
            timeout=UPLOAD_TIMEOUT,
        )
        self._api.post(
            url,
            data={
                "upload_phase": "finish", "video_id": video_id,
                "description": f"{title}\n\n{description}",
                **self._schedule_fields(publish_at, reel=True),
            },
        )
        return PublishResult(video_id, f"https://www.facebook.com/reel/{video_id}")

    @staticmethod
    def _schedule_fields(publish_at: datetime | None, reel: bool) -> dict[str, str]:
        if publish_at is None:
            return {"video_state": "PUBLISHED"} if reel else {"published": "true"}
        stamp = str(int(publish_at.timestamp()))
        if reel:
            return {"video_state": "SCHEDULED", "scheduled_publish_time": stamp}
        return {
            "published": "false", "scheduled_publish_time": stamp,
            "unpublished_content_type": "SCHEDULED",
        }
