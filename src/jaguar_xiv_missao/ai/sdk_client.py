"""Cliente de IA sobre o AI SDK para Python (pacote `ai`, da Vercel)."""

from __future__ import annotations

import asyncio

import ai
import pydantic


class AiSdkClient:
    """Adaptador síncrono do AI SDK.

    Usa um event loop próprio e persistente: o cliente HTTP do provedor fica preso ao loop
    que o criou, então `asyncio.run` a cada chamada quebraria a segunda requisição.
    """

    def __init__(self, model: ai.Model, temperature: float) -> None:
        self._model = model
        self._params = ai.InferenceRequestParams().with_temperature(temperature)
        self._loop = asyncio.new_event_loop()

    def generate[T: pydantic.BaseModel](self, system: str, user: str, output_type: type[T]) -> T:
        return self._loop.run_until_complete(self._generate(system, user, output_type))

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
