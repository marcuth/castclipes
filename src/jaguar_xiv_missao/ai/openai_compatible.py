from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    """Tolera resposta com cercas ```json ou texto em volta."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


class OpenAICompatibleClient:
    """Qualquer provedor com API estilo OpenAI (OpenAI, OpenRouter, Groq, Ollama, vLLM...)."""

    def __init__(
        self, base_url: str, api_key: str, model: str, temperature: float, timeout: float
    ) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key or "none", timeout=timeout)
        self._model = model
        self._temperature = temperature

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return extract_json(response.choices[0].message.content or "{}")
