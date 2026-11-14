"""Regras determinísticas aplicadas aos cortes sugeridos pela IA.

A IA propõe; este módulo garante duração mínima/máxima, fronteiras de frase, ausência de
sobreposição e limite de cortes. Assim o `.env` manda, não o prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..models import ClipCandidate, Transcript


@dataclass(frozen=True)
class ClipConstraints:
    min_seconds: float
    max_seconds: float
    min_score: float
    max_clips: int
    edge_padding: float = 0.5


def _snap_start(transcript: Transcript, t: float) -> float:
    """Início do segmento que contém `t` (ou do próximo)."""
    for seg in transcript.segments:
        if seg.end > t:
            return min(seg.start, t) if seg.start <= t else seg.start
    return t


def _snap_end(transcript: Transcript, t: float) -> float:
    """Fim do segmento que contém `t` (ou do anterior)."""
    last = t
    for seg in transcript.segments:
        if seg.start >= t:
            break
        last = seg.end
    return last


def _end_at_most(transcript: Transcript, limit: float, floor: float) -> float:
    """Maior fim de segmento <= limit (e > floor); senão o próprio limit."""
    best = None
    for seg in transcript.segments:
        if seg.end > limit:
            break
        if seg.end > floor:
            best = seg.end
    return best if best is not None else limit


def _end_at_least(transcript: Transcript, target: float) -> float | None:
    for seg in transcript.segments:
        if seg.end >= target:
            return seg.end
    return None


def fit_candidate(
    candidate: ClipCandidate, transcript: Transcript, rules: ClipConstraints
) -> ClipCandidate | None:
    total = transcript.duration
    pad = rules.edge_padding
    max_body = rules.max_seconds - 2 * pad
    min_body = rules.min_seconds - 2 * pad

    start = max(0.0, candidate.start)
    end = min(total, candidate.end)
    if end <= start:
        return None
    start = _snap_start(transcript, start)
    end = _snap_end(transcript, end)

    if end - start > max_body:
        end = _end_at_most(transcript, start + max_body, start)

    if end - start < min_body:
        extended = _end_at_least(transcript, start + min_body)
        if extended is not None and extended - start <= max_body:
            end = extended
        else:  # fim da transcrição: tenta puxar o início para trás
            new_start = _snap_start(transcript, max(0.0, end - min_body))
            if end - new_start < min_body or end - new_start > max_body:
                return None
            start = new_start

    start = max(0.0, start - pad)
    end = min(total, end + pad)
    if candidate.score < rules.min_score:
        return None
    return replace(candidate, start=round(start, 2), end=round(end, 2))


def enforce(
    candidates: list[ClipCandidate], transcript: Transcript, rules: ClipConstraints
) -> list[ClipCandidate]:
    fitted = [c for raw in candidates if (c := fit_candidate(raw, transcript, rules))]
    fitted.sort(key=lambda c: c.score, reverse=True)
    accepted: list[ClipCandidate] = []
    for cand in fitted:
        if len(accepted) >= rules.max_clips:
            break
        if all(cand.end <= a.start or cand.start >= a.end for a in accepted):
            accepted.append(cand)
    return sorted(accepted, key=lambda c: c.start)


def windows(total: float, size: float, overlap: float) -> list[tuple[float, float]]:
    """Janelas [início, fim] cobrindo `total` com sobreposição."""
    if total <= size:
        return [(0.0, total)]
    step = max(size - overlap, 1.0)
    result, start = [], 0.0
    while start < total:
        result.append((start, min(start + size, total)))
        if start + size >= total:
            break
        start += step
    return result
