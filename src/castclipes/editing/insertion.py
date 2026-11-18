"""Onde inserir o vídeo de CTA dentro do corte: uma fronteira de frase, de preferência numa pausa."""

from __future__ import annotations

from ..models import Transcript

MAX_GAP_BONUS = 2.0
"""Pausas acima disso (s) não ganham mais pontos; desempata pela proximidade do alvo."""
WINDOW_PCT = 0.2
"""O CTA procura numa janela de ±20% do corte em volta de `target_pct`."""


def choose_insert_point(
    transcript: Transcript, start: float, end: float, target_pct: float = 0.5
) -> float | None:
    """Tempo absoluto (fim de uma frase) para inserir o CTA, ou None se não houver fronteira."""
    span = end - start
    if span <= 0:
        return None
    target = start + span * min(max(target_pct, 0.0), 1.0)
    segments = transcript.segments
    ends: list[tuple[float, float]] = []  # (fim da frase, pausa depois dela)
    for i, seg in enumerate(segments):
        if seg.end <= start + 1 or seg.end >= end - 1:
            continue
        gap = segments[i + 1].start - seg.end if i + 1 < len(segments) else 0.0
        ends.append((seg.end, max(0.0, gap)))
    if not ends:
        return None
    window = span * WINDOW_PCT
    inside = [e for e in ends if abs(e[0] - target) <= window]
    if inside:  # maior pausa (até o teto); empate = mais perto do alvo
        best = max(inside, key=lambda e: (round(min(e[1], MAX_GAP_BONUS), 1), -abs(e[0] - target)))
        return best[0]
    return min(ends, key=lambda e: abs(e[0] - target))[0]


def to_relative(keep: list[tuple[float, float]], absolute: float) -> float:
    """Converte um tempo absoluto do arquivo no tempo do corte já sem os silêncios removidos."""
    elapsed = 0.0
    for a, b in keep:
        if absolute <= a:
            break
        elapsed += min(absolute, b) - a
        if absolute < b:
            break
    return elapsed
