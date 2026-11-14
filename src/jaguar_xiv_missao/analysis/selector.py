"""Seleção de cortes com IA (Strategy: o selecionador é trocável)."""

from __future__ import annotations

import logging
from typing import Any, Protocol

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

Responda SOMENTE JSON: {"clips":[{"start":<seg>,"end":<seg>,"topic":"...","pattern":
"reaction|response|revelation|debate|other","speakers":["..."],"target":"terceiro visado ou null",
"score":0.0-1.0,"summary":"1-2 frases opinativas, tom do canal"}]}
Tempos em segundos, conforme os marcadores [Ns] da transcrição. Sem sobreposição."""


class ClipSelector(Protocol):
    def select(self, video: SourceVideo, transcript: Transcript) -> list[ClipCandidate]: ...


def _parse_candidate(raw: dict[str, Any]) -> ClipCandidate | None:
    try:
        pattern = raw.get("pattern", "other")
        return ClipCandidate(
            start=float(raw["start"]),
            end=float(raw["end"]),
            topic=str(raw.get("topic", "")).strip(),
            score=max(0.0, min(1.0, float(raw.get("score", 0)))),
            pattern=ClipPattern(pattern) if pattern in ClipPattern._value2member_map_ else ClipPattern.OTHER,
            speakers=tuple(str(s) for s in raw.get("speakers") or []),
            target=(str(raw["target"]).strip() or None) if raw.get("target") else None,
            summary=str(raw.get("summary", "")).strip(),
        )
    except (KeyError, TypeError, ValueError):
        return None


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
                f"{self._rules.min_score}. Se nada prestar, devolva {{\"clips\":[]}}.\n\n"
                f"TRANSCRIÇÃO:\n{excerpt}"
            )
            try:
                data = self._llm.complete_json(SYSTEM_PROMPT, user)
            except Exception:
                logger.exception("IA falhou na janela %s-%s de %s", start, end, video.id)
                continue
            raw.extend(c for item in data.get("clips", []) if (c := _parse_candidate(item)))
        return enforce(raw, transcript, self._rules)
