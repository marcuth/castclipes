from __future__ import annotations

import ai

from ..config import Settings
from .base import LLMClient
from .sdk_client import AiSdkClient


def create_llm_client(settings: Settings) -> LLMClient:
    """Simple Factory: monta o modelo do AI SDK a partir do .env.

    `AI_PROVIDER` é um ID do models.dev (openai, anthropic, groq, openrouter, ...).
    `AI_BASE_URL` e `AI_API_KEY` são opcionais: vazios, o SDK usa os padrões do provedor
    (inclusive as variáveis de ambiente dele, como OPENAI_API_KEY).
    """
    provider = ai.get_provider(
        settings.ai_provider,
        base_url=settings.ai_base_url or None,
        api_key=settings.ai_api_key or None,
        protocol=_protocol(settings),
    )
    model = ai.Model(id=settings.ai_model, provider=provider)
    return AiSdkClient(model, settings.ai_temperature)


def _protocol(settings: Settings):
    use_chat = settings.ai_protocol == "chat_completions" or (
        settings.ai_protocol == "auto" and bool(settings.ai_base_url)
    )
    if use_chat:
        return ai.providers.openai.OpenAIChatCompletionsProtocol()
    if settings.ai_protocol == "responses":
        return ai.providers.openai.OpenAIResponsesProtocol()
    return None
