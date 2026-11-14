from __future__ import annotations

from typing import Protocol

import pydantic


class LLMClient(Protocol):
    def generate[T: pydantic.BaseModel](self, system: str, user: str, output_type: type[T]) -> T:
        """Chama o modelo e devolve a resposta validada como `output_type`."""
        ...
