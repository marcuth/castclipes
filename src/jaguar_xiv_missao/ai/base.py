from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        """Chama o modelo e devolve o JSON da resposta já parseado."""
