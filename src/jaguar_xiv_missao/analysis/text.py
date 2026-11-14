from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """Minúsculas, sem acento, espaços colapsados."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def count_mentions(text: str, keywords: list[str]) -> int:
    haystack = normalize(text)
    total = 0
    for keyword in keywords:
        needle = normalize(keyword)
        if not needle:
            continue
        total += len(re.findall(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack))
    return total
