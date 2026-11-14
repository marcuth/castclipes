from __future__ import annotations

from typing import Protocol

from ..models import PublishResult, RenderedClip


class Publisher(Protocol):
    def publish(self, clip: RenderedClip) -> PublishResult: ...
