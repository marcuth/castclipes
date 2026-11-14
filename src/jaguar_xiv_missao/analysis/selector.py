"""Seleção de cortes com IA (Strategy: o selecionador é trocável)."""

from __future__ import annotations

import logging
from typing import Literal, Protocol

import pydantic

from ..ai.base import LLMClient
from ..models import ClipCandidate, ClipPattern, SourceVideo, Transcript
from .constraints import ClipConstraints, enforce, windows

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Você é editor de um canal de cortes políticos brasileiro (estilo "Inevitável Cortes").
O canal publica cortes LONGOS (10 a 40 min) em que UM assunto é tratado do começo ao fim,
quase sempre uma destas formas:
- reaction: o falante reage a um vídeo/fala/polêmica de terceiro ("X REAGE a Y");
- response: o falante responde a ataques ou perguntas ("X RESPONDE Y");
- revelation: fala franca, revelação, bastidores, "a verdade sobre...";
- debate: embate com adversário ou convidado.
Os melhores cortes têm CONFLITO com figura nacional (Bolsonaros, Nikolas Ferreira, Lula, PT,
Centrão...), emoção forte, começo e fim naturais, e envolvem Renan Santos, Arthur do Val,
Kim Kataguiri, MBL ou Partido Missão como protagonistas ou alvo.
Evite: recados genéricos, avisos de live, trechos sem tema claro, propaganda.

QUEM É QUEM: a transcrição NÃO identifica quem fala. O canal-fonte pode ser jornalístico ou de
comentário (um apresentador noticiando, sem a pessoa citada presente). Nesse caso o falante é o
apresentador/canal, e quem é citado é ASSUNTO (`target`), não falante.
- `speakers`: só quem comprovadamente fala no trecho (se o próprio texto mostra isso, ex.: se
  apresenta, é chamado a responder). Na dúvida, devolva lista vazia.
- NUNCA tire falantes ou nomes do título do vídeo: o título cita convidados, pautas e adversários
  que podem nem aparecer no trecho. Use só o que está na transcrição da janela.
- `pattern`: reaction/response/debate só se o texto mostrar isso de fato; senão use "other".

Tempos em segundos, conforme os marcadores [Ns] da transcrição. Sem sobreposição.
"""


class ClipSelector(Protocol):
    def select(self, video: SourceVideo, transcript: Transcript) -> list[ClipCandidate]: ...


class ClipSuggestion(pydantic.BaseModel):
    start: float
    end: float
    topic: str
    pattern: Literal["reaction", "response", "revelation", "debate", "other"]
    speakers: list[str]
    target: str | None
    score: float
    summary: str

    def to_candidate(self) -> ClipCandidate:
        return ClipCandidate(
            start=self.start,
            end=self.end,
            topic=self.topic.strip(),
            score=max(0.0, min(1.0, self.score)),
            pattern=ClipPattern(self.pattern),
            speakers=tuple(self.speakers),
            target=(self.target or "").strip() or None,
            summary=self.summary.strip(),
        )


class ClipSuggestions(pydantic.BaseModel):
    clips: list[ClipSuggestion]


class LLMClipSelector:
    def __init__(
        self,
        llm: LLMClient,
        constraints: ClipConstraints,
        target_seconds: int,
        window_seconds: int,
        window_overlap_seconds: int,
    ) -> None:
        self._llm = llm
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
                data = self._llm.generate(SYSTEM_PROMPT, user, ClipSuggestions)
            except Exception:
                logger.exception("IA falhou na janela %s-%s de %s", start, end, video.id)
                continue
            raw.extend(item.to_candidate() for item in data.clips)
        return enforce(raw, transcript, self._rules)
