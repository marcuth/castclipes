"""Gera título, descrição e tags de cada corte."""

from __future__ import annotations

import logging
from typing import Protocol

import pydantic

from ..ai.base import LLMClient
from ..config import Settings
from ..models import ClipCandidate, ClipFormat, ClipMetadata, SourceVideo
from .formatting import format_title, hashtags, merge_tags

logger = logging.getLogger(__name__)

COMMON_PROMPT = """\
Você escreve metadados de cortes de PODCAST para YouTube em português do Brasil.
FIDELIDADE (regra mais importante): só atribua uma fala a uma pessoa se ela estiver na lista de
"Falantes". Se a lista estiver vazia, escreva sobre o ASSUNTO, sem inventar autoria. Nunca use
nomes do título do vídeo original que não estejam no assunto/resumo do corte. Não invente fatos
nem faça acusações que o conteúdo não sustente.
RESUMO: 1-2 frases explicando o que acontece no corte.
TAGS: 8 a 15 tags específicas (falantes, tema, nome do podcast, palavras que as pessoas buscariam).
"""

LONG_PROMPT = COMMON_PROMPT + """
TÍTULO: 45 a 80 caracteres, específico e curioso, ancorado no que é dito (pessoa, situação,
número, polêmica). Proibido o genérico: "o segredo de...", "você não vai acreditar", "isso mudou tudo".
TEXTO DA THUMBNAIL: o gancho em 2 a 4 palavras (máx. 28 caracteres), sem pontuação final.
"""

SHORT_PROMPT = COMMON_PROMPT + """
TÍTULO: até 60 caracteres, direto, que gere curiosidade a partir do gancho do corte. Proibido o
genérico: "o segredo de...", "você não vai acreditar", "veja o que aconteceu".
TEXTO DA THUMBNAIL: deixe vazio (Shorts não têm thumbnail própria).
"""

PROMPTS = {ClipFormat.LONG: LONG_PROMPT, ClipFormat.SHORT: SHORT_PROMPT}


class MetadataSuggestion(pydantic.BaseModel):
    title: str
    summary: str
    tags: list[str]
    thumbnail_text: str = ""


class MetadataGenerator(Protocol):
    def generate(self, video: SourceVideo, candidate: ClipCandidate) -> ClipMetadata: ...


class DescriptionBuilder:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def build(
        self, video: SourceVideo, summary: str, extra_hashtags: tuple[str, ...] = ()
    ) -> str:
        s = self._s
        blocks: list[str] = []
        if s.description_header:
            blocks.append(s.description_header)
        if summary:
            blocks.append(f"➡️ {summary}")
        if s.watch_more_url:
            label = s.watch_more_label or "Quer saber mais?"
            blocks.append(f"👉 {label} {s.watch_more_url}")
        credit = f"{video.channel_title}: " if video.channel_title else ""
        blocks.append(f"👀 Episódio completo ({credit}{video.title}): {video.url}")
        if s.social_links:
            blocks.append("\n".join(s.social_links))
        if s.description_footer:
            blocks.append(s.description_footer)
        blocks.append(hashtags([*extra_hashtags, *s.fixed_hashtags]))
        return "\n\n".join(b for b in blocks if b)[:5000]


class LLMMetadataGenerator:
    def __init__(self, llm: LLMClient, settings: Settings) -> None:
        self._llm = llm
        self._s = settings
        self._description = DescriptionBuilder(settings)

    def generate(self, video: SourceVideo, candidate: ClipCandidate) -> ClipMetadata:
        title_raw, summary, dynamic_tags, thumb_text = self._ask(video, candidate)
        title = format_title(title_raw, self._s.title_max_chars, self._s.title_style)
        is_short = candidate.format is ClipFormat.SHORT
        tags = merge_tags([*self._s.fixed_tags, *(["shorts"] if is_short else [])], dynamic_tags)
        description = self._description.build(video, summary, ("shorts",) if is_short else ())
        return ClipMetadata(title, description, tags, thumb_text.strip().upper()[:40])

    def _ask(self, video: SourceVideo, c: ClipCandidate) -> tuple[str, str, list[str], str]:
        user = (
            f"Podcast/live original: {video.title} ({video.channel_title})\n"
            f"Meu canal de cortes: {self._s.channel_name or 'não informado'}\n"
            f"Assunto do corte: {c.topic}\n"
            f"Gancho (primeira frase): {c.hook or 'n/d'}\n"
            f"Falantes: {', '.join(c.speakers) or 'desconhecido'}\n"
            f"Resumo prévio: {c.summary}"
        )
        try:
            data = self._llm.generate(PROMPTS[c.format], user, MetadataSuggestion)
            title = data.title.strip()
            if title:
                return title, data.summary or c.summary, data.tags, data.thumbnail_text
        except Exception:
            logger.exception("IA falhou ao gerar metadados; usando template")
        return self._fallback_title(c), c.summary, [*c.speakers, c.topic], ""

    @staticmethod
    def _fallback_title(c: ClipCandidate) -> str:
        return c.topic or c.hook or "Corte do podcast"
