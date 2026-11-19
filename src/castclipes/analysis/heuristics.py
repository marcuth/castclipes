"""Seleção de cortes por heurísticas, sem IA (alternativa ao `LLMClipSelector`).

Portado do podcast-clipper (`src/heuristics/`): a transcrição vira unidades (frases), cada uma
recebe uma nota por regras aditivas (gatilhos de atenção, contraste, pergunta, primeira pessoa,
pausa...) e penalidades (CTA/patrocínio, intro da live), com bônus opcional do heatmap "mais
reproduzido" do YouTube. Depois uma janela deslizante procura os trechos de maior nota dentro da
duração do formato. `enforce` (constraints.py) continua mandando nas fronteiras e nos limites.

Limites conhecidos: regex não entende assunto, então nos cortes longos a "coerência" vem só da
densidade de nota; o tópico é uma lista de palavras-chave, não uma frase.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from ..models import ClipCandidate, ClipFormat, SourceVideo, Transcript
from .constraints import ClipConstraints, enforce

# --- pesos (somam por unidade; RAW_CAP satura a nota em 1.0) ---
W_TRIGGER = 1.0
W_CONTRAST = 0.7
W_PERSONAL = 0.5
W_QUESTION = 0.4
W_LENGTH = 0.3
W_EXCLAIM = 0.3
W_LAUGH = 0.3
W_NUMBER = 0.2
W_PAUSE = 0.2
W_HEATMAP = 1.5
RAW_CAP = 3.0

PAUSE_SECONDS = 0.4
GOOD_WORDS = (8, 40)
UNIT_MIN_SECONDS = 6.0
UNIT_MAX_SECONDS = 14.0
UNIT_GAP_SECONDS = 1.0
REFERENCE_FLOOR = 0.25
"""Nota de referência mínima na normalização: vídeo sem sinais fortes não ganha nota alta."""
LONG_BLOCKED_MAX_FRACTION = 0.05

TRIGGERS = re.compile(
    r"presta atencao|olha so|o ponto e|o problema e|ninguem fala sobre|o maior erro|o segredo e|"
    r"o que ninguem (te )?conta|isso muda tudo|isso e importante|voce sabia|a verdade e|"
    r"muita gente|inacreditavel|surpreendente|dica de ouro|conselho|essa historia|"
    r"nunca (te )?contei|vou te contar|aconteceu (uma|um)|a real e|pela primeira vez"
)
CONTRAST = re.compile(r"antes.*agora|todo mundo.*mas|parecia.*mas|achava.*mas")
PERSONAL = re.compile(r"\b(eu|meu|minha|a gente|nos|fiquei|pensei|achei|senti|falei)\b")
LAUGH = re.compile(r"\b(k{3,}|(ha){2,}|(he){2,}|rs{2,})\b|risos|risadas")
NUMBER = re.compile(r"\d|\b(mil|milhao|milhoes|bilhao|bilhoes|por cento)\b")
BLOCKED = re.compile(
    r"inscrev|deixa o like|dar o like|ativa o sininho|segue a gente|compartilha|"
    r"link na (descricao|bio)|aqui nos comentarios|comenta (aqui|ai)|cupom|patrocin|"
    r"codigo de desconto|tchau|ate o proximo|valeu pessoal|nao esquece de|se voce gostou|"
    r"tela final|vou ler (os )?comentarios|super ?chat|manda (o seu )?pix"
)
STOPWORDS = frozenset(
    ["para", "como", "mais", "mas", "isso", "esta", "esse", "essa", "estao", "estava", "foram", "pelo", "pela", "entao", "porque", "quando", "tambem", "muito", "muita", "ainda", "sobre", "depois", "antes", "assim", "aqui", "onde", "quem", "qual", "cada", "outro", "outra", "todo", "toda", "todos", "todas", "coisa", "coisas", "gente", "acho", "vamos", "pode", "fazer", "fiz", "tinha", "tenho", "seria", "ficar", "fica", "falar", "falei", "disse", "vezes", "agora", "ali", "la", "voce", "voces", "eles", "elas", "dele", "dela", "nosso", "nossa", "algum", "alguma", "mesmo", "mesma", "nada", "tudo", "sempre", "nunca", "entre", "ate", "desde", "sem", "seu", "sua", "seus", "suas"]
)


def normalize(text: str) -> str:
    """Minúsculas e sem acentos (as regex acima são escritas sem acento)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


@dataclass(frozen=True)
class Unit:
    """Uma frase (ou grupo de segmentos curtos) com a nota por regras."""

    start: float
    end: float
    text: str
    score: float = 0.0
    blocked: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start


def build_units(transcript: Transcript) -> list[tuple[float, float, str]]:
    """Agrupa segmentos em frases: fecha em pontuação final, pausa longa ou duração máxima.
    A legenda automática do YouTube vem em pedaços curtos e sem pontuação, daí o agrupamento."""
    units: list[tuple[float, float, str]] = []
    start = end = 0.0
    parts: list[str] = []

    def flush() -> None:
        nonlocal parts
        if parts:
            units.append((start, end, " ".join(parts)))
            parts = []

    for seg in transcript.segments:
        text = seg.text.strip()
        if not text:
            continue
        if parts and seg.start - end >= UNIT_GAP_SECONDS:
            flush()
        if not parts:
            start = seg.start
        parts.append(text)
        end = seg.end
        length = end - start
        if length >= UNIT_MAX_SECONDS or (
            length >= UNIT_MIN_SECONDS and text.endswith((".", "!", "?", "…"))
        ):
            flush()
    flush()
    return units


def heat_at(heatmap: tuple[tuple[float, float, float], ...], start: float, end: float) -> float:
    """Intensidade média (0 a 1) das janelas do heatmap que tocam [start, end]."""
    values = [v for a, b, v in heatmap if min(end, b) > max(start, a)]
    return sum(values) / len(values) if values else 0.0


def score_units(
    raw: list[tuple[float, float, str]],
    skip_intro_seconds: float,
    heatmap: tuple[tuple[float, float, float], ...] = (),
) -> list[Unit]:
    units: list[Unit] = []
    previous_end: float | None = None
    for start, end, text in raw:
        norm = normalize(text)
        blocked = start < skip_intro_seconds or bool(BLOCKED.search(norm))
        score = 0.0
        if not blocked:
            words = len(text.split())
            raw_score = 0.0
            raw_score += W_TRIGGER if TRIGGERS.search(norm) else 0.0
            raw_score += W_CONTRAST if CONTRAST.search(norm) else 0.0
            raw_score += W_PERSONAL if PERSONAL.search(norm) else 0.0
            raw_score += W_QUESTION if "?" in text else 0.0
            raw_score += W_LENGTH if GOOD_WORDS[0] <= words <= GOOD_WORDS[1] else 0.0
            raw_score += W_EXCLAIM if "!" in text else 0.0
            raw_score += W_LAUGH if LAUGH.search(norm) else 0.0
            raw_score += W_NUMBER if NUMBER.search(norm) else 0.0
            if previous_end is not None and start - previous_end > PAUSE_SECONDS:
                raw_score += W_PAUSE
            raw_score += W_HEATMAP * heat_at(heatmap, start, end)
            score = min(raw_score, RAW_CAP) / RAW_CAP
        units.append(Unit(start, end, text, score, blocked))
        previous_end = end
    return units


def keywords(texts: list[str], limit: int = 3) -> list[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        for word in re.findall(r"[a-zà-ú]{5,}", text.lower()):
            if normalize(word) not in STOPWORDS:
                counts[word] += 1
    return [word for word, n in counts.most_common(limit) if n >= 2]


def _clip_text(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


class HeuristicClipSelector:
    """`ClipSelector` sem IA: pontua frases por regras e escolhe as janelas de maior nota."""

    def __init__(
        self,
        fmt: ClipFormat,
        constraints: ClipConstraints,
        target_seconds: int,
        skip_intro_seconds: int = 120,
    ) -> None:
        self._format = fmt
        self._rules = constraints
        self._target = target_seconds
        self._skip_intro = skip_intro_seconds

    def select(self, video: SourceVideo, transcript: Transcript) -> list[ClipCandidate]:
        units = score_units(build_units(transcript), self._skip_intro, video.heatmap)
        if not units:
            return []
        scored = self._windows(units)
        if not scored:
            return []
        ordered = sorted((s for s in scored if s[0] > 0), reverse=True)
        if not ordered:
            return []
        values = sorted(s for s, _, _ in ordered)
        reference = max(values[int(0.95 * (len(values) - 1))], REFERENCE_FLOOR)

        picked: list[tuple[float, int, int]] = []
        for score, i, j in ordered:
            if len(picked) >= self._rules.max_clips * 2:
                break
            a, b = units[i].start, units[j].end
            if all(b <= units[pi].start or a >= units[pj].end for _, pi, pj in picked):
                picked.append((score, i, j))
        raw = [self._candidate(units, i, j, min(1.0, s / reference)) for s, i, j in picked]
        return enforce(raw, transcript, self._rules)

    # ---------- partes ----------
    def _windows(self, units: list[Unit]) -> list[tuple[float, int, int]]:
        """Todas as janelas [i, j] dentro da duração do formato, com a nota de cada uma."""
        rules = self._rules
        is_short = self._format is ClipFormat.SHORT
        stride = 2.0 if is_short else max(10.0, rules.min_seconds / 20)
        starts = [u.start for u in units]
        ends = [u.end for u in units]
        weighted = [0.0]
        blocked = [0.0]
        for u in units:
            weighted.append(weighted[-1] + u.score * u.duration)
            blocked.append(blocked[-1] + (u.duration if u.blocked else 0.0))
        span = max(rules.max_seconds - rules.min_seconds, 1.0)

        out: list[tuple[float, int, int]] = []
        last_start = -stride
        for i, start in enumerate(starts):
            if units[i].blocked or start - last_start < stride:
                continue
            last_start = start
            j = bisect.bisect_left(ends, start + rules.min_seconds)
            limit = bisect.bisect_right(ends, start + rules.max_seconds)
            while j < min(limit, len(units)):
                duration = ends[j] - start
                dead = blocked[j + 1] - blocked[i]
                ok = dead == 0 if is_short else dead <= LONG_BLOCKED_MAX_FRACTION * duration
                if ok:
                    density = (weighted[j + 1] - weighted[i]) / duration
                    if is_short:  # o gancho (primeiras frases) pesa muito num short
                        hook = max(u.score for u in units[i : min(i + 2, j + 1)])
                        density = 0.6 * density + 0.4 * hook
                    fit = 1 - 0.25 * min(abs(duration - self._target) / span, 1.0)
                    out.append((density * fit, i, j))
                j = bisect.bisect_left(ends, ends[j] + stride, j + 1)
        return out

    def _candidate(self, units: list[Unit], i: int, j: int, score: float) -> ClipCandidate:
        chunk = units[i : j + 1]
        hook = _clip_text(chunk[0].text, 140)
        if self._format is ClipFormat.SHORT:
            topic = _clip_text(chunk[0].text, 100)
        else:
            mean = sum(u.score for u in chunk) / len(chunk)
            # só as frases acima da média: o enchimento da conversa não vira "assunto"
            words = keywords([u.text for u in chunk if u.score > mean])
            topic = (
                "Conversa sobre " + ", ".join(words[:-1]) + (" e " if len(words) > 1 else "")
                + words[-1]
                if words
                else _clip_text(chunk[0].text, 100)
            )
        return ClipCandidate(
            start=chunk[0].start, end=chunk[-1].end, topic=topic, score=score,
            format=self._format, hook=hook,
        )
