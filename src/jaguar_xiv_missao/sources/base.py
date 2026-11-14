from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..models import SourceVideo


class VideoSource(Protocol):
    def latest(self) -> Iterable[SourceVideo]: ...
