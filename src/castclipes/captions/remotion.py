"""Legendas animadas (estilo CapCut) renderizadas pelo projeto Remotion em `remotion/`.

Gera um WebM transparente (VP8 + alfa) com a duração do short; o ffmpeg do renderer o
sobrepõe ao vídeo. Falhas levantam `CaptionError` (não há legenda alternativa).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ..models import Word

logger = logging.getLogger(__name__)

REMOTION_DIR = Path(__file__).resolve().parents[3] / "remotion"
RENDER_TIMEOUT_S = 600
MIN_WORD_SECONDS = 0.08


class CaptionError(RuntimeError):
    """O Remotion não conseguiu gerar a legenda."""


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


def _npm(name: str) -> str | None:
    # No Windows são scripts .cmd; shutil.which resolve a extensão.
    return shutil.which(name)


def _ensure_dependencies(npm: str) -> None:
    if (REMOTION_DIR / "node_modules").is_dir():
        return
    logger.info("Instalando dependências do Remotion (primeira execução)...")
    result = subprocess.run(
        [npm, "install"], check=False, cwd=REMOTION_DIR, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=RENDER_TIMEOUT_S,
    )
    if result.returncode != 0:
        raise CaptionError(f"npm install falhou em remotion/: {result.stderr[-500:]}")


def render_remotion_captions(
    words: Sequence[Word],
    duration: float,
    out: Path,
    center_ranges: Sequence[tuple[float, float]] = (),
    highlight: str = "#FFD400",
    bottom_offset: int = 520,
) -> Path | None:
    """Renderiza o overlay transparente em `out` (.webm). `words` em tempo relativo ao corte.
    Devolve `out`, ou `None` se não há palavras; levanta `CaptionError` se o render falhar."""
    clean = normalize_words(words)
    if not clean:
        return None
    npx, npm = _npm("npx"), _npm("npm")
    if not npx or not npm or not REMOTION_DIR.is_dir():
        raise CaptionError("Node/npm ou a pasta remotion/ não foram encontrados (legendas exigem Remotion)")

    props = out.with_suffix(".props.json")
    try:
        _ensure_dependencies(npm)
        props.write_text(
            json.dumps(
                {
                    "words": [{"word": w.text, "start": w.start, "end": w.end} for w in clean],
                    "durationInSeconds": duration,
                    "centerRanges": [{"start": a, "end": b} for a, b in center_ranges],
                    "activeColor": highlight,
                    "bottomOffset": bottom_offset,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                npx, "remotion", "render", "src/index.ts", "Captions", str(out.resolve()),
                f"--props={props.resolve()}", "--codec=vp8", "--image-format=png",
                "--pixel-format=yuva420p", "--log=error",
            ],
            check=False, cwd=REMOTION_DIR, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=RENDER_TIMEOUT_S,
        )
        if result.returncode != 0 or not out.exists():
            raise CaptionError(f"Remotion falhou: {(result.stderr or result.stdout)[-500:]}")
        return out
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise CaptionError(f"Remotion falhou: {exc}") from exc
    finally:
        props.unlink(missing_ok=True)
