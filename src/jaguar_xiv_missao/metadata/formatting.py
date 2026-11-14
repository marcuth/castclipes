"""Formatação no padrão do canal-alvo: títulos em CAIXA ALTA, preposições em minúsculo."""

from __future__ import annotations

import re

SMALL_WORDS = {
    "a", "o", "as", "os", "ao", "aos", "à", "às", "e", "de", "do", "da", "dos", "das", "em", "no",
    "na", "nos", "nas", "com", "para", "por", "pelo", "pela", "sobre", "contra", "um", "uma", "que",
}

YOUTUBE_TAGS_MAX_CHARS = 500


def format_title(raw: str, max_chars: int = 100) -> str:
    """`arthur do val reage a vídeo bizarro` -> `ARTHUR do VAL REAGE a VÍDEO BIZARRO`."""
    words = re.sub(r"\s+", " ", raw).strip().strip('"“”').split(" ")
    out = []
    for i, word in enumerate(words):
        bare = re.sub(r"\W", "", word).lower()
        out.append(word.lower() if i > 0 and bare in SMALL_WORDS else word.upper())
    title = " ".join(out)
    if len(title) > max_chars:
        title = title[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,:;-") + "…"
    return title


def merge_tags(fixed: list[str], dynamic: list[str]) -> tuple[str, ...]:
    """Fixas primeiro, depois as dinâmicas; sem duplicatas; respeita o limite do YouTube."""
    seen: set[str] = set()
    result: list[str] = []
    total = 0
    for tag in [*fixed, *dynamic]:
        tag = tag.strip().lower().lstrip("#")
        if not tag or tag in seen:
            continue
        cost = len(tag) + (2 if " " in tag else 0) + 1  # aspas implícitas + vírgula
        if total + cost > YOUTUBE_TAGS_MAX_CHARS:
            break
        seen.add(tag)
        result.append(tag)
        total += cost
    return tuple(result)


def hashtags(tags: list[str]) -> str:
    return " ".join(f"#{t.lstrip('#')}" for t in tags if t)
