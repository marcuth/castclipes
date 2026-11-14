"""Gera título, descrição e tags de cada corte."""

from __future__ import annotations

import logging
from typing import Protocol

import pydantic

from ..ai.base import LLMClient
from ..config import Settings
from ..models import ClipCandidate, ClipMetadata, ClipPattern, SourceVideo
from .formatting import format_title, hashtags, merge_tags

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Você escreve metadados de cortes políticos para YouTube, no padrão do canal "Inevitável Cortes".
TÍTULO: formato `[PESSOA] [VERBO] [ALVO/ASSUNTO] [GATILHO EMOCIONAL]!`, o nome do falante vem
primeiro. Verbos típicos: REAGE a, RESPONDE, FALA A VERDADE sobre, REVELA BASTIDORES de, DEBATE.
FIDELIDADE (regra mais importante): só ponha uma pessoa como autora da fala/reação se a lista de
"Falantes" a trouxer. Se estiver vazia, ou se o canal de origem for jornalístico/de comentário
(o apresentador noticia, a pessoa citada não está falando), NÃO atribua a fala a ninguém: faça o
título sobre o ASSUNTO e o alvo, ex.: `RENAN SANTOS é DESMASCARADO após ...!`, `MBL vira ALVO de ...!`.
Nunca use nomes do título do vídeo original que não estejam no assunto/resumo do corte.
Gatilhos que funcionam: BIZARRO, SURTO, HUMILHADO, DESMASCARA, SEM PALAVRAS, SINCERO ATÉ DEMAIS,
PASSANDO VERGONHA. Use só se o conteúdo justificar (sem inventar fatos nem acusações falsas).
45 a 80 caracteres. Português do Brasil.
RESUMO: 1-2 frases opinativas explicando o que acontece no corte.
TAGS: 8 a 15 tags específicas (falante + variações, alvo, programa/podcast, tema, ano da eleição).
TEXTO DA THUMBNAIL: o gancho do corte em 2 a 4 palavras (máx. 28 caracteres), sem o nome do
falante (o rosto já aparece) e sem pontuação final. Ex.: VÍDEO BIZARRO, SURTO AO VIVO, SEM PALAVRAS.
"""

VERB_BY_PATTERN = {
    ClipPattern.REACTION: "reage a",
    ClipPattern.RESPONSE: "responde",
    ClipPattern.REVELATION: "fala a verdade sobre",
    ClipPattern.DEBATE: "debate",
    ClipPattern.OTHER: "fala sobre",
}


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

    def build(self, video: SourceVideo, summary: str, tags: list[str]) -> str:
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
        blocks.append(f"👀 Vídeo original ({credit}{video.title}): {video.url}")
        if s.social_links:
            blocks.append("\n".join(s.social_links))
        if s.description_footer:
            blocks.append(s.description_footer)
        blocks.append(hashtags(s.fixed_hashtags))
        return "\n\n".join(b for b in blocks if b)[:5000]


class LLMMetadataGenerator:
    def __init__(self, llm: LLMClient, settings: Settings) -> None:
        self._llm = llm
        self._s = settings
        self._description = DescriptionBuilder(settings)

    def generate(self, video: SourceVideo, candidate: ClipCandidate) -> ClipMetadata:
        title_raw, summary, dynamic_tags, thumb_text = self._ask(video, candidate)
        title = format_title(title_raw, self._s.title_max_chars)
        tags = merge_tags(self._s.fixed_tags, dynamic_tags)
        description = self._description.build(video, summary, list(tags))
        return ClipMetadata(title, description, tags, thumb_text.strip().upper()[:40])

    def _ask(self, video: SourceVideo, c: ClipCandidate) -> tuple[str, str, list[str], str]:
        user = (
            f"Vídeo original: {video.title} ({video.channel_title})\n"
            f"Assunto do corte: {c.topic}\nPadrão: {c.pattern.value}\n"
            f"Falantes: {', '.join(c.speakers) or 'desconhecido'}\n"
            f"Alvo: {c.target or 'nenhum'}\nResumo prévio: {c.summary}"
        )
        try:
            data = self._llm.generate(SYSTEM_PROMPT, user, MetadataSuggestion)
            title = data.title.strip()
            if title:
                return title, data.summary or c.summary, data.tags, data.thumbnail_text
        except Exception:
            logger.exception("IA falhou ao gerar metadados; usando template")
        return self._fallback_title(c), c.summary, [*c.speakers, c.target or "", c.topic], ""

    @staticmethod
    def _fallback_title(c: ClipCandidate) -> str:
        subject = c.target or c.topic
        if not c.speakers:
            return f"{subject}!"
        return f"{c.speakers[0]} {VERB_BY_PATTERN[c.pattern]} {subject}!"
