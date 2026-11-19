"""Legendas animadas (estilo CapCut) renderizadas pelo projeto Remotion em `remotion/`.

Gera um WebM transparente (VP8 + alfa) com a duração do short; o ffmpeg do renderer o
sobrepõe ao vídeo. Toda falha é não fatal: devolve `None` e o chamador cai para o ASS.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ..models import Word
from .ass import normalize_words

logger = logging.getLogger(__name__)

REMOTION_DIR = Path(__file__).resolve().parents[3] / "remotion"
RENDER_TIMEOUT_S = 600


def _npm(name: str) -> str | None:
    # No Windows são scripts .cmd; shutil.which resolve a extensão.
    return shutil.which(name)


def _ensure_dependencies(npm: str) -> bool:
    if (REMOTION_DIR / "node_modules").is_dir():
        return True
    logger.info("Instalando dependências do Remotion (primeira execução)...")
    result = subprocess.run(
        [npm, "install"], check=False, cwd=REMOTION_DIR, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=RENDER_TIMEOUT_S,
    )
    if result.returncode != 0:
        logger.warning("npm install falhou: %s", result.stderr[-500:])
        return False
    return True


def render_remotion_captions(
    words: Sequence[Word],
    duration: float,
    out: Path,
    center_ranges: Sequence[tuple[float, float]] = (),
    highlight: str = "#FFD400",
    bottom_offset: int = 520,
) -> Path | None:
    """Renderiza o overlay transparente em `out` (.webm). `words` em tempo relativo ao corte.
    Devolve `out`, ou `None` se algo falhar."""
    clean = normalize_words(words)
    if not clean:
        return None
    npx, npm = _npm("npx"), _npm("npm")
    if not npx or not npm or not REMOTION_DIR.is_dir():
        logger.warning("Node/npx ou a pasta remotion/ não foram encontrados; usando legendas ASS.")
        return None

    props = out.with_suffix(".props.json")
    try:
        if not _ensure_dependencies(npm):
            return None
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
            logger.warning("Remotion falhou: %s", (result.stderr or result.stdout)[-500:])
            return None
        return out
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Remotion falhou: %s", exc)
        return None
    finally:
        props.unlink(missing_ok=True)
