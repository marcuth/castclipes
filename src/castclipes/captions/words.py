"""Tempo por palavra para as legendas dos shorts (Strategy: `WordAligner`)."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from ..config import Settings
from ..editing.silence import ffmpeg_exe
from ..models import ClipCandidate, Transcript, Word

logger = logging.getLogger(__name__)


class WordAligner(Protocol):
    def align(
        self, source: Path, candidate: ClipCandidate, transcript: Transcript
    ) -> list[Word]:
        """Palavras do corte com tempo RELATIVO ao início dele (t=0 = `candidate.start`).
        Lista vazia = sem como alinhar."""
        ...


def words_from_transcript(transcript: Transcript, start: float, end: float) -> list[Word]:
    """Palavras do trecho a partir da transcrição existente. Segmentos sem tempo por palavra
    (legenda do YouTube) têm o tempo distribuído proporcionalmente ao tamanho de cada palavra."""
    words: list[Word] = []
    for seg in transcript.window(start, end):
        if seg.words:
            words.extend(Word(w.start - start, w.end - start, w.text) for w in seg.words)
            continue
        tokens = seg.text.split()
        if not tokens:
            continue
        total = sum(len(t) + 1 for t in tokens)
        cursor = seg.start
        for token in tokens:
            span = (seg.end - seg.start) * (len(token) + 1) / total
            words.append(Word(cursor - start, cursor + span - start, token))
            cursor += span
    clip_len = end - start
    return [w for w in words if w.end > 0 and w.start < clip_len]


class TranscriptWordAligner:
    """Estima o tempo das palavras pela transcrição (rápido, menos preciso)."""

    def align(self, source: Path, candidate: ClipCandidate, transcript: Transcript) -> list[Word]:
        return words_from_transcript(transcript, candidate.start, candidate.end)


class WhisperWordAligner:
    """Re-transcreve só o áudio do corte com faster-whisper e pega o tempo de cada palavra."""

    def __init__(self, model: str, device: str, compute_type: str, language: str) -> None:
        self._model_name, self._device, self._compute_type = model, device, compute_type
        self._language = language.split("-")[0]
        self._model = None

    def align(self, source: Path, candidate: ClipCandidate, transcript: Transcript) -> list[Word]:
        from faster_whisper import WhisperModel  # ImportError tratado por quem chama

        if self._model is None:
            self._model = WhisperModel(
                self._model_name, device=self._device, compute_type=self._compute_type
            )
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "clip.wav"
            _extract_audio(source, candidate.start, candidate.end, audio)
            segments, _ = self._model.transcribe(
                str(audio), language=self._language, beam_size=1, vad_filter=True,
                word_timestamps=True,
            )
            return [
                Word(w.start, w.end, w.word.strip())
                for seg in segments for w in (seg.words or []) if w.word.strip()
            ]


class FallbackWordAligner:
    """Tenta os alinhadores em ordem; o primeiro que devolver palavras vence."""

    def __init__(self, *aligners: WordAligner) -> None:
        self._aligners = aligners

    def align(self, source: Path, candidate: ClipCandidate, transcript: Transcript) -> list[Word]:
        for aligner in self._aligners:
            try:
                words = aligner.align(source, candidate, transcript)
            except ImportError:
                logger.warning(
                    "faster-whisper não instalado; legendas com tempo estimado "
                    "(pip install -e .[whisper] para o tempo exato)"
                )
                continue
            except Exception:
                logger.exception("%s falhou; tentando o próximo alinhador", type(aligner).__name__)
                continue
            if words:
                return words
        return []


def _extract_audio(source: Path, start: float, end: float, out: Path) -> None:
    cmd = [
        ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou ao extrair áudio:\n{proc.stderr[-500:]}")


def create_word_aligner(settings: Settings) -> WordAligner:
    """Simple Factory conforme SHORT_CAPTIONS_WHISPER."""
    estimated = TranscriptWordAligner()
    if not settings.short_captions_whisper:
        return estimated
    language = settings.transcript_languages[0] if settings.transcript_languages else "pt"
    return FallbackWordAligner(
        WhisperWordAligner(
            settings.whisper_model, settings.whisper_device, settings.whisper_compute_type,
            language,
        ),
        estimated,
    )
