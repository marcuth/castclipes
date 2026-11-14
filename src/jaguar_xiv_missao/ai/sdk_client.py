"""Cliente de IA sobre o AI SDK para Python (pacote `ai`, da Vercel)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import ai
import pydantic

logger = logging.getLogger(__name__)


class AiSdkClient:
    """Adaptador síncrono do AI SDK.

    Usa um event loop próprio e persistente: o cliente HTTP do provedor fica preso ao loop
    que o criou, então `asyncio.run` a cada chamada quebraria a segunda requisição.
    """

    def __init__(
        self,
        model: ai.Model,
        temperature: float,
        max_retries: int = 0,
        retry_delay_seconds: float = 5.0,
        retry_max_delay_seconds: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._model = model
        self._params = ai.InferenceRequestParams().with_temperature(temperature)
        self._loop = asyncio.new_event_loop()
        self._max_retries = max(0, max_retries)
        self._delay = retry_delay_seconds
        self._max_delay = retry_max_delay_seconds
        self._sleep = sleep

    def generate[T: pydantic.BaseModel](self, system: str, user: str, output_type: type[T]) -> T:
        """Chama o modelo; com `max_retries` > 0, repete falhas (HTTP, resposta vazia/inválida)
        com espera crescente (delay, 2x, 4x... até o teto)."""
        attempt = 0
        while True:
            try:
                return self._loop.run_until_complete(self._generate(system, user, output_type))
            except Exception as exc:
                if attempt >= self._max_retries:
                    raise
                wait = min(self._delay * 2**attempt, self._max_delay)
                attempt += 1
                logger.warning(
                    "IA falhou (%s: %s); tentativa %d/%d em %.0fs",
                    type(exc).__name__, str(exc)[:120].replace("\n", " "), attempt,
                    self._max_retries, wait,
                )
                self._sleep(wait)

    async def _generate[T: pydantic.BaseModel](
        self, system: str, user: str, output_type: type[T]
    ) -> T:
        messages = [ai.system_message(system), ai.user_message(user)]
        async with ai.stream(
            self._model, messages, output_type=output_type, params=self._params
        ) as stream:
            async for _ in stream:
                pass
            return stream.output

    def close(self) -> None:
        self._loop.run_until_complete(self._model.provider.aclose())
        self._loop.close()
