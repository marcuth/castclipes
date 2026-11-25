"""Publicação no Threads: post de texto com o link do vídeo no YouTube.

A API do Threads só aceita vídeo por URL pública (`video_url`), e os cortes ficam em disco local.
Por isso o post leva o título e o link do corte no YouTube (`link_attachment` gera o cartão).
O link só funciona depois que o vídeo é publicado: com a fila de postagem ligada, o
`CrosspostQueue` espera o horário agendado (mais uma folga) antes de postar.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import httpx

from ..config import Settings
from ..models import ClipFormat, PublishResult, RenderedClip
from .graph import GraphClient, GraphError
from .threads_token import ThreadsTokenManager

logger = logging.getLogger(__name__)

GRAPH = "https://graph.threads.net/v1.0"
TEXT_LIMIT = 500


class ThreadsPublisher:
    supports = frozenset({ClipFormat.LONG, ClipFormat.SHORT})
    native_schedule = False
    schedule_delay = timedelta(minutes=5)
    """Folga depois do horário agendado do YouTube, para o vídeo já estar público."""

    def __init__(
        self, settings: Settings, client: httpx.Client | None = None, sleep=time.sleep
    ) -> None:
        self._user = settings.threads_user_id
        self._client = client or httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0))
        self._tokens = ThreadsTokenManager(
            settings.threads_access_token,
            settings.data_dir / "threads_token.json",
            self._client,
        )
        self._api = GraphClient(self._tokens.token, self._client, sleep)

    def maintain(self) -> None:
        """Renova o token quando necessário; chamado em cada rodada do pipeline."""
        self._tokens.refresh_if_due()
        self._api.token = self._tokens.token

    def publish(self, clip: RenderedClip, publish_at: datetime | None = None) -> PublishResult:
        meta = clip.metadata
        link = clip.extra.get("youtube_url")
        if meta is None:
            raise ValueError("RenderedClip sem metadata")
        if not link:
            raise GraphError("sem link do YouTube para anexar ao post do Threads")
        self.maintain()
        container = self._api.post(
            f"{GRAPH}/{self._user}/threads",
            data={"media_type": "TEXT", "text": meta.title[:TEXT_LIMIT], "link_attachment": link},
        )
        post = self._api.post(
            f"{GRAPH}/{self._user}/threads_publish", data={"creation_id": container["id"]}
        )
        try:
            url = self._api.get(f"{GRAPH}/{post['id']}", {"fields": "permalink"}).get("permalink")
        except GraphError:  # o post já saiu; o link é só informativo
            url = None
        return PublishResult(post["id"], url)
