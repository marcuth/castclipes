"""Legendas ASS palavra a palavra (estilo karaokê): o grupo de palavras aparece com um "pop"
e a palavra que está sendo falada acende na cor de destaque.

Cada palavra falada vira um evento `Dialogue` com o grupo inteiro e só aquela palavra colorida.
Só o primeiro evento do grupo tem a animação de entrada, então o texto não "pisca" a cada palavra.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from ..models import Word

PLAY_RES_X = 1080
PLAY_RES_Y = 1920
FONT_SIZE = 110
SIDE_MARGIN = 50
OUTLINE = 6
POP_PEAK_PCT = 118
POP_GROW_MS = 90
POP_SETTLE_MS = 160
MAX_CHUNK_WORDS = 3
MAX_CHUNK_CHARS = 18
PAUSE_BREAK_SECONDS = 0.6
MIN_WORD_SECONDS = 0.08
FALLBACK_CHAR_WIDTH = 0.50  # largura média de glifo por unidade de fonte, sem o arquivo da fonte
SENTENCE_END = (".", "!", "?", "…")
WHITE = "&H00FFFFFF&"


@dataclass(frozen=True)
class CaptionStyle:
    font_name: str = "Anton"
    font_file: Path | None = None
    highlight: str = "#FFD400"
    margin_v: int = 520
    """Distância da base do vídeo até a legenda (1920 de altura)."""


def ass_color(hex_color: str) -> str:
    """`#RRGGBB` -> `&H00BBGGRR&` (formato do ASS)."""
    value = hex_color.lstrip("#")
    r, g, b = value[0:2], value[2:4], value[4:6]
    return f"&H00{b}{g}{r}&".upper()


def format_time(seconds: float) -> str:
    cs = round(max(0.0, seconds) * 100)
    hours, cs = divmod(cs, 360000)
    minutes, cs = divmod(cs, 6000)
    secs, cs = divmod(cs, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


@lru_cache(maxsize=4)
def _load_font(path: str | None) -> ImageFont.FreeTypeFont | None:
    if not path:
        return None
    try:
        return ImageFont.truetype(path, FONT_SIZE)
    except OSError:
        return None


def width_per_size(text: str, font_file: Path | None) -> float:
    """Largura em px por unidade de tamanho ASS (o libass usa a altura da linha, não o em)."""
    font = _load_font(str(font_file) if font_file else None)
    if font is None:
        return len(text) * FALLBACK_CHAR_WIDTH
    ascent, descent = font.getmetrics()
    return font.getlength(text) / (ascent + descent)


def fit_font_size(text: str, font_file: Path | None) -> int:
    """Maior tamanho (até FONT_SIZE) em que `text` cabe numa linha no pico do pop."""
    available = (PLAY_RES_X - 2 * SIDE_MARGIN) / (POP_PEAK_PCT / 100) - 2 * OUTLINE
    size = int(available / max(width_per_size(text, font_file), 1e-6))
    return max(1, min(FONT_SIZE, size))


def normalize_words(words: Sequence[Word]) -> list[Word]:
    """Descarta palavras vazias, ordena e garante duração mínima e ausência de sobreposição."""
    clean = sorted((w for w in words if w.text.strip()), key=lambda w: w.start)
    out: list[Word] = []
    for i, word in enumerate(clean):
        end = max(word.end, word.start + MIN_WORD_SECONDS)
        if i + 1 < len(clean):
            end = min(end, max(clean[i + 1].start, word.start + 0.01))
        out.append(Word(word.start, end, word.text.strip()))
    return out


def chunk_words(words: Sequence[Word]) -> list[list[Word]]:
    """Agrupa em até MAX_CHUNK_WORDS palavras; quebra em pausas e no fim de frases."""
    chunks: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current and word.start - current[-1].end >= PAUSE_BREAK_SECONDS:
            chunks.append(current)
            current = []
        current.append(word)
        size = len(" ".join(w.text for w in current))
        if (
            len(current) >= MAX_CHUNK_WORDS
            or size > MAX_CHUNK_CHARS
            or word.text.endswith(SENTENCE_END)
        ):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _pop_tag(font_size: int) -> str:
    peak = POP_PEAK_PCT
    return (
        f"\\fs{font_size}\\fscx0\\fscy0"
        f"\\t(0,{POP_GROW_MS},\\fscx{peak}\\fscy{peak})"
        f"\\t({POP_GROW_MS},{POP_SETTLE_MS},\\fscx100\\fscy100)"
    )


def _in_ranges(t: float, ranges: Sequence[tuple[float, float]]) -> bool:
    return any(a <= t < b for a, b in ranges)


def generate_ass(
    words: Sequence[Word],
    style: CaptionStyle,
    center_ranges: Sequence[tuple[float, float]] = (),
) -> str:
    """Documento ASS completo. `words` em tempo relativo ao corte (t=0 = início do short).
    Em `center_ranges` (split-screen) a legenda vai para o centro vertical, sobre a divisória."""
    highlight = ass_color(style.highlight)
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {PLAY_RES_X}\nPlayResY: {PLAY_RES_Y}\nWrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,{style.font_name},{FONT_SIZE},{WHITE},{highlight},&H00000000&,"
        f"&H80000000&,0,0,0,0,100,100,0,0,1,{OUTLINE},0,2,{SIDE_MARGIN},{SIDE_MARGIN},"
        f"{style.margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    )
    lines = [header]
    center = f"\\an5\\pos({PLAY_RES_X // 2},{PLAY_RES_Y // 2})"
    for chunk in chunk_words(normalize_words(words)):
        texts = [w.text.upper() for w in chunk]
        size = fit_font_size(" ".join(texts), style.font_file)
        for i, word in enumerate(chunk):
            start = word.start
            end = chunk[i + 1].start if i + 1 < len(chunk) else word.end
            end = max(end, start + 0.02)
            parts = [
                f"{{\\c{highlight}}}{t}{{\\c{WHITE}}}" if j == i else t
                for j, t in enumerate(texts)
            ]
            tags = center if _in_ranges(start, center_ranges) else ""
            tags += _pop_tag(size) if i == 0 else f"\\fs{size}"
            lines.append(
                f"Dialogue: 0,{format_time(start)},{format_time(end)},Caption,,0,0,0,,"
                f"{{{tags}}}{' '.join(parts)}"
            )
    return "\n".join(lines) + "\n"
