"""Triagem de vídeos SEM legenda: vale baixar e transcrever?"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import pydantic

from ..ai.base import LLMClient
from ..models import SourceVideo

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você filtra vídeos para um canal de cortes de PODCAST. Transcrever custa caro, então só aprove
vídeos que provavelmente sejam uma conversa longa e rica (podcast, entrevista, bate-papo,
debate, mesa-redonda) com momentos que rendam cortes. Reprove clipes curtos, música, jogos
sem conversa, avisos, vídeos de espera/contagem regressiva e qualquer coisa que não seja
conversa.
Dê uma nota de 0.0 a 1.0 e uma justificativa curta."""


class TriageVerdict(pydantic.BaseModel):
    score: float
    reason: str


@dataclass(frozen=True)
class TriageResult:
    approved: bool
    score: float
    reason: str


class VideoTriage(Protocol):
    def evaluate(self, video: SourceVideo) -> TriageResult: ...


class LLMVideoTriage:
    def __init__(self, llm: LLMClient, min_score: float) -> None:
        self._llm = llm
        self._min_score = min_score

    def evaluate(self, video: SourceVideo) -> TriageResult:
        minutes = round((video.duration_seconds or 0) / 60)
        user = (
            f"Título: {video.title}\nCanal: {video.channel_title}\nDuração: {minutes} min\n"
            f"Descrição:\n{video.description[:1500]}"
        )
        try:
            data = self._llm.generate(SYSTEM_PROMPT, user, TriageVerdict)
            score = max(0.0, min(1.0, data.score))
            reason = data.reason
        except Exception as exc:
            logger.exception("Triagem falhou para %s", video.id)
            return TriageResult(False, 0.0, f"erro na triagem: {exc}")
        return TriageResult(score >= self._min_score, score, reason)
