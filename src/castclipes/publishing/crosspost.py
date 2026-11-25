"""Publicação cruzada (Facebook, Instagram, Threads) com fila persistente.

O YouTube é o destino principal: ele manda no resultado e no estado do pipeline. Cada rede
extra vira um registro na tabela `crossposts` (SQLite) e é enviada por `flush()`:

- se falhar, tenta de novo depois (até `max_attempts`), sem reenviar o corte ao YouTube;
- redes que não agendam (Instagram, Threads) esperam o horário da fila de postagem
  (`due_at`); o Facebook agenda sozinho e recebe o horário no próprio envio.

Falha numa rede extra nunca derruba o pipeline.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from ..models import (
    ClipCandidate,
    ClipFormat,
    ClipMetadata,
    PublishResult,
    RenderedClip,
    SourceVideo,
)
from ..storage.state import CrosspostJob, StateStore
from .base import Publisher

logger = logging.getLogger(__name__)

MIN_NATIVE_LEAD = timedelta(minutes=10)
"""O Facebook recusa agendamento com menos de 10 min de antecedência."""


class NetworkPublisher(Publisher, Protocol):
    supports: frozenset[ClipFormat]
    native_schedule: bool


def _dump(clip: RenderedClip, youtube_url: str | None, publish_at: datetime | None) -> str:
    c, m = clip.candidate, clip.metadata
    assert m is not None
    return json.dumps(
        {
            "path": str(clip.path), "duration": clip.duration_seconds,
            "thumbnail": str(clip.thumbnail_path) if clip.thumbnail_path else None,
            "format": c.format.value, "start": c.start, "end": c.end, "topic": c.topic,
            "score": c.score, "source_id": clip.source.id, "source_title": clip.source.title,
            "title": m.title, "description": m.description, "tags": list(m.tags),
            "thumbnail_text": m.thumbnail_text,
            "extra": {**clip.extra, **({"youtube_url": youtube_url} if youtube_url else {})},
            "publish_at": publish_at.isoformat() if publish_at else None,
        },
        ensure_ascii=False,
    )


def _load(payload: str) -> tuple[RenderedClip, datetime | None]:
    d = json.loads(payload)
    candidate = ClipCandidate(
        d["start"], d["end"], d["topic"], d["score"], format=ClipFormat(d["format"])
    )
    clip = RenderedClip(
        candidate, SourceVideo(id=d["source_id"], title=d["source_title"]), Path(d["path"]),
        d["duration"],
        ClipMetadata(d["title"], d["description"], tuple(d["tags"]), d["thumbnail_text"]),
        Path(d["thumbnail"]) if d["thumbnail"] else None, d["extra"],
    )
    return clip, (datetime.fromisoformat(d["publish_at"]) if d["publish_at"] else None)


class CrosspostQueue:
    def __init__(
        self,
        primary: Publisher,
        networks: dict[str, NetworkPublisher],
        store: StateStore,
        max_attempts: int = 5,
        retry_minutes: int = 15,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._primary = primary
        self._networks = networks
        self._store = store
        self._max_attempts = max_attempts
        self._retry = timedelta(minutes=retry_minutes)
        self._now = now

    # ---------- Publisher ----------
    def publish(self, clip: RenderedClip, publish_at: datetime | None = None) -> PublishResult:
        result = self._primary.publish(clip, publish_at=publish_at)
        if result.dry_run or clip.metadata is None:
            return result
        c = clip.candidate
        payload = _dump(clip, result.url, publish_at)
        for name, network in self._networks.items():
            if c.format not in network.supports:
                continue
            due = self._now()
            if publish_at is not None and not network.native_schedule:
                due = publish_at + getattr(network, "schedule_delay", timedelta(0))
            self._store.enqueue_crosspost(
                clip.source.id, c.format.value, c.start, c.end, name, due, payload
            )
        self.flush()
        links = self._store.crosspost_urls(clip.source.id, c.format.value, c.start, c.end)
        return replace(result, extra={**result.extra, **links})

    # ---------- fila ----------
    def flush(self) -> int:
        """Envia os registros vencidos. Devolve quantos saíram."""
        sent = 0
        for name, network in self._networks.items():
            maintain = getattr(network, "maintain", None)
            if maintain is not None:
                try:
                    maintain()
                except Exception:
                    logger.exception("Falha ao renovar credenciais de %s", name)
        for job in self._store.due_crossposts(self._now()):
            sent += self._run(job)
        return sent

    def _run(self, job: CrosspostJob) -> int:
        network = self._networks.get(job.network)
        if network is None:
            self._store.fail_crosspost(job.id, f"rede {job.network} não está configurada", None)
            return 0
        try:
            clip, publish_at = _load(job.payload)
            if not clip.path.exists():
                self._store.fail_crosspost(job.id, f"arquivo sumiu: {clip.path}", None)
                return 0
            if network.native_schedule and publish_at is not None:
                if publish_at - self._now() < MIN_NATIVE_LEAD:
                    publish_at = None  # horário já passou ou está perto demais: publica agora
            else:
                publish_at = None
            result = network.publish(clip, publish_at=publish_at)
        except Exception as exc:
            attempts = job.attempts + 1
            give_up = attempts >= self._max_attempts
            retry_at = None if give_up else self._now() + self._retry * attempts
            self._store.fail_crosspost(job.id, repr(exc), retry_at, attempts)
            logger.exception(
                "Falha ao publicar em %s (%s) — tentativa %d/%d%s",
                job.network, job.source_id, attempts, self._max_attempts,
                "; desisti" if give_up else f"; nova tentativa às {retry_at:%H:%M}",
            )
            return 0
        self._store.finish_crosspost(job.id, result.url or result.video_id or "")
        logger.info("Publicado em %s: %s", job.network, result.url)
        return 1
