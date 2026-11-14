"""Triagem de vídeos SEM legenda: vale baixar e transcrever?"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from ..ai.base import LLMClient
from ..models import SourceVideo

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Você filtra vídeos para um canal de cortes políticos (MBL, Partido Missão, Renan Santos,
Arthur do Val, Kim Kataguiri). Transcrever custa caro, então só aprove vídeos que
provavelmente tenham conteúdo longo e rico, com esses nomes como protagonistas ou alvo
(entrevistas, lives, debates, reações). Reprove clipes curtos, música, notícias genéricas,
vídeos sem relação.
Responda SOMENTE JSON: {"score":0.0-1.0,"reason":"..."}"""


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
            data = self._llm.complete_json(SYSTEM_PROMPT, user)
            score = max(0.0, min(1.0, float(data.get("score", 0))))
            reason = str(data.get("reason", ""))
        except Exception as exc:
            logger.exception("Triagem falhou para %s", video.id)
            return TriageResult(False, 0.0, f"erro na triagem: {exc}")
        return TriageResult(score >= self._min_score, score, reason)
