from __future__ import annotations

from ..config import Settings
from .base import LLMClient
from .openai_compatible import OpenAICompatibleClient


def create_llm_client(settings: Settings) -> LLMClient:
    """Simple Factory: escolhe o cliente conforme AI_PROVIDER."""
    if settings.ai_provider == "openai_compatible":
        return OpenAICompatibleClient(
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            temperature=settings.ai_temperature,
            timeout=settings.ai_timeout_seconds,
        )
    raise ValueError(f"AI_PROVIDER desconhecido: {settings.ai_provider}")
