"""Publicação de Reels no Instagram (conta Business/Creator) via Graph API.

Fluxo com upload resumível, sem precisar de URL pública:
1. cria o container (`media_type=REELS`, `upload_type=resumable`) e recebe a `uri` de upload;
2. envia o arquivo para essa `uri`;
3. espera o processamento (`status_code=FINISHED`);
4. `media_publish`.

Só shorts (9:16): a API de conteúdo do Instagram não recebe os cortes longos. A API também não
agenda: o `CrosspostQueue` segura o envio até o horário da fila.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import httpx

from ..config import Settings
from ..models import ClipFormat, PublishResult, RenderedClip
from .graph import UPLOAD_TIMEOUT, GraphClient, GraphError

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com"
CAPTION_LIMIT = 2200
POLL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600


def caption_for(title: str, description: str) -> str:
    return f"{title}\n\n{description}"[:CAPTION_LIMIT]


class InstagramPublisher:
    supports = frozenset({ClipFormat.SHORT})
    native_schedule = False

    def __init__(
        self, settings: Settings, client: httpx.Client | None = None, sleep=time.sleep
    ) -> None:
        self._user = settings.instagram_user_id
        self._version = settings.facebook_api_version
        token = settings.instagram_access_token or settings.facebook_page_access_token
        self._api = GraphClient(token, client, sleep)
        self._sleep = sleep

    def publish(self, clip: RenderedClip, publish_at: datetime | None = None) -> PublishResult:
        meta = clip.metadata
        if meta is None:
            raise ValueError("RenderedClip sem metadata")
        base = f"{GRAPH}/{self._version}"
        path = Path(clip.path)
        container = self._api.post(
            f"{base}/{self._user}/media",
            data={
                "media_type": "REELS", "upload_type": "resumable",
                "caption": caption_for(meta.title, meta.description), "share_to_feed": "true",
            },
        )
        container_id = container["id"]
        self._api.post(
            container["uri"],
            content=path.read_bytes(),
            headers={
                "Authorization": f"OAuth {self._api.token}", "offset": "0",
                "file_size": str(path.stat().st_size),
            },
            auth_in_body=False,
            timeout=UPLOAD_TIMEOUT,
        )
        self._wait_until_ready(base, container_id)
        media = self._api.post(f"{base}/{self._user}/media_publish", data={"creation_id": container_id})
        media_id = media["id"]
        try:
            url = self._api.get(f"{base}/{media_id}", {"fields": "permalink"}).get("permalink")
        except GraphError:  # o post já saiu; o link é só informativo
            url = None
        return PublishResult(media_id, url)

    def _wait_until_ready(self, base: str, container_id: str) -> None:
        waited = 0
        while True:
            status = self._api.get(f"{base}/{container_id}", {"fields": "status_code,status"})
            code = status.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise GraphError(f"Instagram recusou o vídeo ({code}): {status.get('status', '')}")
            if waited >= POLL_TIMEOUT_SECONDS:
                raise GraphError("Instagram demorou demais para processar o vídeo")
            self._sleep(POLL_SECONDS)
            waited += POLL_SECONDS
