"""Publica o mesmo corte em vários destinos (YouTube + Facebook ...)."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime

from ..models import PublishResult, RenderedClip
from .base import Publisher

logger = logging.getLogger(__name__)


class MultiPublisher:
    """O destino principal manda no resultado (é ele que o pipeline grava no estado).

    Os extras são "melhor esforço": se falharem, só registra o erro. Propagar a falha faria o
    pipeline marcar o vídeo como `failed` e reenviar o corte ao principal (duplicado)."""

    def __init__(self, primary: Publisher, extras: dict[str, Publisher]) -> None:
        self._primary = primary
        self._extras = extras

    def publish(self, clip: RenderedClip, publish_at: datetime | None = None) -> PublishResult:
        result = self._primary.publish(clip, publish_at=publish_at)
        links = dict(result.extra)
        title = clip.metadata.title if clip.metadata else "?"
        for name, publisher in self._extras.items():
            try:
                extra = publisher.publish(clip, publish_at=publish_at)
            except Exception:
                logger.exception("Falha ao publicar em %s: %s", name, title)
                continue
            if extra.url:
                links[name] = extra.url
                logger.info("Publicado em %s: %s", name, extra.url)
        return replace(result, extra=links)
