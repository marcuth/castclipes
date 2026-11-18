"""Seleção de cortes com IA (Strategy: o selecionador é trocável), um por formato."""

from __future__ import annotations

import logging
from typing import Protocol

import pydantic

from ..ai.base import LLMClient
from ..models import ClipCandidate, ClipFormat, SourceVideo, Transcript
from .constraints import ClipConstraints, enforce, windows

logger = logging.getLogger(__name__)

PODCAST_CONTEXT = """\
Você é editor de um canal de cortes de PODCAST no YouTube. A fonte é a gravação de uma live
de podcast: conversa entre apresentador(es) e convidado(s).

A transcrição NÃO identifica quem fala. Em `speakers` ponha só quem comprovadamente fala no
trecho (o próprio texto mostra: se apresenta, é chamado pelo nome, responde a uma pergunta
dirigida). Na dúvida, lista vazia. NUNCA tire falantes do título do vídeo: ele cita convidados
e pautas que podem nem aparecer no trecho.

Tempos em segundos, conforme os marcadores [Ns] da transcrição. Sem sobreposição entre cortes.
"""

LONG_PROMPT = PODCAST_CONTEXT + """
FORMATO: corte LONGO. UM assunto tratado do começo ao fim, com abertura, desenvolvimento e
fechamento naturais, que se entenda sem ter visto o resto da live. Bons cortes: uma história
completa, um debate/discordância, uma explicação aprofundada, uma polêmica, uma revelação.
Evite: recados e avisos da live, propaganda, leitura de comentários sem tema, trechos que
dependem de contexto anterior, pedaços que misturam vários assuntos.
`hook`: a frase de abertura do corte. `topic`: o assunto em uma frase.
"""

SHORT_PROMPT = PODCAST_CONTEXT + """
FORMATO: SHORT vertical (YouTube Shorts/TikTok/Reels), de poucos segundos. Procure o momento
mais forte, não o mais longo:
- GANCHO IMEDIATO: o corte começa numa fala de impacto, pergunta provocativa, afirmação
  surpreendente ou início de uma história. Nunca no meio de uma frase que dependa do que veio antes.
- FECHAMENTO: termina depois da conclusão, punchline ou lição; nunca no meio de uma frase.
- Funciona sozinho, sem contexto. Humor, revelação, opinião forte, número chocante, conflito.
- Espalhe os cortes pela live; não escolha trechos repetidos nem sobrepostos.
`hook`: a primeira frase falada. `topic`: a ideia central, concreta (cite pessoa, número,
situação dita no trecho; nada de "o segredo de...").
"""

PROMPTS = {ClipFormat.LONG: LONG_PROMPT, ClipFormat.SHORT: SHORT_PROMPT}


class ClipSelector(Protocol):
    def select(self, video: SourceVideo, transcript: Transcript) -> list[ClipCandidate]: ...


class ClipSuggestion(pydantic.BaseModel):
    start: float
    end: float
    topic: str
    hook: str = ""
    speakers: list[str] = pydantic.Field(default_factory=list)
    score: float
    summary: str = ""

    def to_candidate(self, fmt: ClipFormat) -> ClipCandidate:
        return ClipCandidate(
            start=self.start,
            end=self.end,
            topic=self.topic.strip(),
            score=max(0.0, min(1.0, self.score)),
            format=fmt,
            hook=self.hook.strip(),
            speakers=tuple(self.speakers),
            summary=self.summary.strip(),
        )


class ClipSuggestions(pydantic.BaseModel):
    clips: list[ClipSuggestion]


class LLMClipSelector:
    def __init__(
        self,
        llm: LLMClient,
        fmt: ClipFormat,
        constraints: ClipConstraints,
        target_seconds: int,
        window_seconds: int,
        window_overlap_seconds: int,
    ) -> None:
        self._llm = llm
        self._format = fmt
        self._rules = constraints
        self._target = target_seconds
        self._window = window_seconds
        self._overlap = window_overlap_seconds

    def select(self, video: SourceVideo, transcript: Transcript) -> list[ClipCandidate]:
        raw: list[ClipCandidate] = []
        for start, end in windows(transcript.duration, self._window, self._overlap):
            excerpt = transcript.render(start, end)
            if not excerpt:
                continue
            user = (
                f"Vídeo: {video.title}\nCanal: {video.channel_title}\n"
                f"Janela analisada: {int(start)}s a {int(end)}s\n"
                f"Regras: cada corte entre {int(self._rules.min_seconds)}s e "
                f"{int(self._rules.max_seconds)}s (ideal ~{self._target}s). "
                f"No máximo {self._rules.max_clips} cortes. Só inclua cortes com score >= "
                f"{self._rules.min_score}. Se nada prestar, devolva a lista de cortes vazia.\n\n"
                f"TRANSCRIÇÃO:\n{excerpt}"
            )
            try:
                data = self._llm.generate(PROMPTS[self._format], user, ClipSuggestions)
            except Exception:
                logger.exception(
                    "IA falhou (%s) na janela %s-%s de %s", self._format, start, end, video.id
                )
                continue
            raw.extend(item.to_candidate(self._format) for item in data.clips)
        return enforce(raw, transcript, self._rules)
