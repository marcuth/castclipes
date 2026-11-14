from __future__ import annotations

from ..downloader import VideoDownloader
from ..models import SourceVideo, Transcript, TranscriptSegment


class WhisperTranscriptProvider:
    """Baixa o áudio e transcreve localmente com faster-whisper (extra `whisper`)."""

    name = "whisper"

    def __init__(
        self, downloader: VideoDownloader, model: str, device: str, compute_type: str, language: str
    ) -> None:
        self._downloader = downloader
        self._model_name, self._device, self._compute_type = model, device, compute_type
        self._language = language.split("-")[0]
        self._model = None

    def fetch(self, video: SourceVideo) -> Transcript | None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper não instalado. Rode: pip install -e .[whisper]"
            ) from exc
        if self._model is None:
            self._model = WhisperModel(
                self._model_name, device=self._device, compute_type=self._compute_type
            )
        audio = self._downloader.download_audio(video)
        try:
            segments, info = self._model.transcribe(
                str(audio), language=self._language, vad_filter=True
            )
            result = [
                TranscriptSegment(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()
            ]
        finally:
            audio.unlink(missing_ok=True)
        return Transcript(result, source=self.name, language=info.language)
