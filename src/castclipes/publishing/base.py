from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..models import PublishResult, RenderedClip


class Publisher(Protocol):
    def publish(
        self, clip: RenderedClip, publish_at: datetime | None = None
    ) -> PublishResult: ...
