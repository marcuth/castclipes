"""Observer: barramento de eventos do pipeline."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .models import ClipCandidate, PublishResult, RenderedClip, SourceVideo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    pass


@dataclass(frozen=True)
class VideoDiscovered(Event):
    video: SourceVideo


@dataclass(frozen=True)
class VideoSkipped(Event):
    video: SourceVideo
    reason: str


@dataclass(frozen=True)
class VideoWaiting(Event):
    video: SourceVideo
    reason: str


@dataclass(frozen=True)
class TranscriptReady(Event):
    video: SourceVideo
    source: str
    segments: int


@dataclass(frozen=True)
class ClipsSelected(Event):
    video: SourceVideo
    candidates: list[ClipCandidate]


@dataclass(frozen=True)
class ClipRendered(Event):
    clip: RenderedClip


@dataclass(frozen=True)
class ClipPublished(Event):
    clip: RenderedClip
    result: PublishResult


@dataclass(frozen=True)
class PipelineError(Event):
    video: SourceVideo | None
    error: Exception


Handler = Callable[[Any], None]


class EventBus:
    """Handlers que falham não derrubam o pipeline."""

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: Handler) -> None:
        self._handlers[Event].append(handler)

    def publish(self, event: Event) -> None:
        for event_type, handlers in self._handlers.items():
            if isinstance(event, event_type):
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:
                        logger.exception("Observer falhou em %s", type(event).__name__)
