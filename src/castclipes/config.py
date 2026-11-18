"""Configuração central. Tudo vem do `.env` (ver `.env.example`)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Position = Literal[
    "top-left", "top-right", "bottom-left", "bottom-right", "center", "top-center", "bottom-center"
]
OverlayFit = Literal["width", "stretch"]


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---------- Fontes (RSS) ----------
    source_live_playlist_ids: CsvList = Field(default_factory=list)
    """IDs da playlist de LIVES (UULV...) de cada canal monitorado. Aceita também o ID do
    canal (UC...), convertido automaticamente. O projeto só processa lives (regra fixa)."""
    poll_interval_seconds: int = 900
    source_max_age_hours: int = 48
    source_fallback_limit: int = 5
    """Se o RSS do YouTube falhar (404 é comum), lê as N lives mais recentes da playlist via yt-dlp.
    0 = sem reserva."""
    """Ignora vídeos do feed mais antigos que isso."""
    source_min_duration_seconds: int = 600
    """Ignora vídeos-fonte mais curtos (não há o que cortar)."""
    source_max_duration_seconds: int = 10 * 3600
    """Lives do MBL passam de 3 h; ajuste conforme disco e tempo de transcrição."""
    live_caption_wait_minutes: int = 90
    """Live encerrada sem legenda: espera isso antes de recorrer ao Whisper, porque o YouTube
    costuma publicar a legenda automática pouco depois do fim da live."""

    # ---------- Relevância ----------
    triage_min_score: float = 0.7
    """Nota mínima (0-1) para gastar download+Whisper em vídeo sem legenda."""

    # ---------- Formatos de corte ----------
    clip_formats: CsvList = Field(default_factory=lambda: ["long", "short"])
    """Quais formatos gerar de cada live: `long` (16:9), `short` (9:16) ou os dois."""
    clip_edge_padding_seconds: float = 0.5
    """Folga antes/depois do corte longo, ajustada às fronteiras de frase."""
    selection_window_seconds: int = 3600
    selection_window_overlap_seconds: int = 300
    """Transcrições longas são analisadas em janelas para caber no contexto da IA."""

    # Corte longo: um assunto do começo ao fim
    long_min_seconds: int = 600
    long_max_seconds: int = 2400
    long_target_seconds: int = 1320
    long_min_score: float = 0.6
    max_long_per_video: int = 3

    # Short: um gancho forte, vertical
    short_min_seconds: int = 20
    short_max_seconds: int = 85
    short_target_seconds: int = 45
    short_min_score: float = 0.7
    max_shorts_per_video: int = 8
    short_edge_padding_seconds: float = 0.2

    # ---------- Corte de silêncio ----------
    silence_cut_enabled: bool = True
    silence_threshold_db: float = -35.0
    silence_min_duration_seconds: float = 0.8
    """Só pausas maiores que isso são encurtadas (o canal-alvo preserva o ritmo natural)."""
    silence_keep_padding_seconds: float = 0.25
    """Quanto da pausa é mantido em cada ponta."""

    # ---------- Molduras e overlays ----------
    long_frame_path: Path | None = None
    """Moldura PNG com transparência (16:9) sobre os cortes longos, esticada ao vídeo."""
    short_frame_path: Path | None = None
    """Moldura PNG com transparência (9:16) sobre os shorts, esticada ao vídeo."""
    watermark_path: Path | None = None
    """Marca d'água opcional, aplicada por cima da moldura nos dois formatos."""
    watermark_position: Position = "top-right"
    watermark_width_pct: float = 0.14
    watermark_opacity: float = 0.85
    watermark_margin_px: int = 24
    watermark_fit: OverlayFit = "width"
    """stretch = ocupa o vídeo inteiro (esticada à largura e altura do vídeo); ignora
    posição, largura e margem."""
    cta_video_path: Path | None = None
    """Vídeo de CTA/anúncio inserido no meio do corte longo (sem overlays), numa pausa entre frases."""
    cta_position_pct: float = 0.5
    """Ponto do corte (0 a 1) onde o CTA entra; vai para a melhor fronteira de frase perto dele."""
    cta_min_clip_seconds: float = 480.0
    """Cortes longos mais curtos que isso não recebem CTA."""
    outro_path: Path | None = None
    """Vídeo opcional anexado ao fim de cada corte longo."""

    # ---------- Shorts (9:16) ----------
    short_width: int = 1080
    short_height: int = 1920
    short_framing_sample_fps: int = 5
    """Quadros por segundo analisados para achar rostos (mais = mais preciso e mais lento)."""
    short_split_screen: bool = True
    """Divide a tela em dois blocos quando há dois interlocutores na cena."""
    short_split_chance: float = 0.5
    """Probabilidade de usar o split-screen num short em que há dois rostos (0 a 1)."""
    short_captions: bool = True
    """Queima legendas palavra a palavra (ASS) nos shorts."""
    short_captions_whisper: bool = True
    """Re-transcreve cada short com Whisper para ter o tempo exato de cada palavra. Sem o extra
    `whisper` (ou com False), o tempo das palavras é estimado a partir da legenda do vídeo."""
    short_caption_highlight: str = "#FFD400"
    """Cor da palavra que está sendo falada."""
    short_caption_font_path: Path | None = None
    """Vazio = Anton (OFL), embutida no pacote."""
    short_caption_margin_v: int = 520
    """Distância da legenda até a base do vídeo (px, em 1920 de altura)."""

    # ---------- Render ----------
    render_engine: Literal["ffmpeg", "moviepy"] = "ffmpeg"
    """ffmpeg = filter_complex único (rápido). moviepy = reserva, passa frames pelo Python (lento)."""
    render_fps: int = 30
    render_preset: str = "medium"
    render_crf: int = 21
    render_threads: int = 4
    max_source_height: int = 1080
    """Altura máxima do vídeo baixado (os shorts saem em SHORT_WIDTH x SHORT_HEIGHT)."""

    # ---------- IA (AI SDK para Python, pacote `ai`) ----------
    ai_provider: str = "openai"
    """ID de provedor do models.dev: openai, anthropic, groq, openrouter, ..."""
    ai_base_url: str = ""
    """Vazio = padrão do provedor. Preencha para Ollama, vLLM, proxies, etc."""
    ai_api_key: str = ""
    """Vazio = o SDK lê a variável do provedor (ex.: OPENAI_API_KEY)."""
    ai_model: str = "gpt-4.1-mini"
    ai_protocol: Literal["auto", "chat_completions", "responses"] = "auto"
    """auto = chat completions quando AI_BASE_URL está definido (Ollama, vLLM, proxies só
    suportam esse); senão o padrão do provedor (OpenAI usa a Responses API)."""
    ai_temperature: float = 0.3
    ai_max_retries: int = 0
    """Tentativas extras quando a chamada falha (429, 5xx, resposta vazia). 0 = desligado."""
    ai_retry_delay_seconds: float = 5.0
    """Espera antes da 1ª nova tentativa; dobra a cada falha, até o teto abaixo."""
    ai_retry_max_delay_seconds: float = 60.0

    # ---------- Transcrição ----------
    transcript_languages: CsvList = Field(default_factory=lambda: ["pt", "pt-BR"])
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"

    # ---------- Metadados de publicação ----------
    title_max_chars: int = 100
    title_style: Literal["natural", "upper"] = "natural"
    """natural = frase como a IA escreveu (1ª letra maiúscula). upper = CAIXA ALTA com
    preposições em minúsculo."""
    fixed_tags: CsvList = Field(default_factory=lambda: ["podcast", "cortes de podcast"])
    fixed_hashtags: CsvList = Field(default_factory=lambda: ["podcast", "cortes"])
    channel_name: str = ""
    """Nome do SEU canal de cortes (aparece no prompt de metadados)."""
    description_header: str = ""
    description_footer: str = ""
    social_links: CsvList = Field(default_factory=list)
    """Linhas livres `Rótulo: url`, separadas por vírgula."""
    watch_more_label: str = ""
    watch_more_url: str = ""

    # ---------- Publicação ----------
    publish_mode: Literal["youtube", "dry_run"] = "dry_run"
    youtube_privacy_status: Literal["private", "unlisted", "public"] = "private"
    youtube_category_id: str = "22"
    """22 = Pessoas e blogs; 24 = Entretenimento; 25 = Notícias e política."""
    youtube_client_secrets_file: Path = Path("secrets/client_secret.json")
    youtube_token_file: Path = Path("secrets/youtube_token.json")
    max_publish_per_day: int = 5
    """A cota padrão da API (10.000/dia, ~1.600 por upload) comporta cerca de 6 envios/dia."""

    # ---------- Fila de postagem ----------
    publish_schedule_enabled: bool = False
    """True = o corte é enviado já pronto, mas agendado (publishAt) para o próximo horário livre."""
    publish_timezone: str = "America/Sao_Paulo"
    publish_slots: CsvList = Field(default_factory=list)
    """Horários HH:MM fixos. Vazio = distribui MAX_PUBLISH_PER_DAY horários na janela abaixo."""
    publish_window_start: str = "09:00"
    publish_window_end: str = "22:00"
    publish_min_lead_minutes: int = 30
    """Antecedência mínima entre o envio e o horário agendado."""
    publish_queue_days: int = 3
    """Até quantos dias à frente a fila aceita cortes; depois disso o pipeline espera."""

    # ---------- Thumbnails ----------
    thumbnail_provider: Literal["none", "template"] = "none"
    """Só para cortes longos (o YouTube não aceita thumbnail própria em Shorts).
    template = melhor frame (rosto + fundo limpo, via MediaPipe) + texto em template xpict.
    Sem IA generativa."""
    thumbnail_sample_count: int = 24
    thumbnail_face_min_confidence: float = 0.6
    thumbnail_max_zoom: float = 1.6
    thumbnail_accent_color: str = "#FFD400"
    thumbnail_font_path: Path | None = None
    """Vazio = Anton (OFL), embutida no pacote."""
    thumbnail_logo_path: Path | None = None

    # ---------- Armazenamento / notificações ----------
    data_dir: Path = Path("data")
    notify_webhook_url: str = ""
    log_level: str = "INFO"

    @field_validator(
        "source_live_playlist_ids", "transcript_languages", "fixed_tags",
        "fixed_hashtags", "social_links", "publish_slots", "clip_formats",
        mode="before",
    )
    @classmethod
    def _csv(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator(
        "watermark_path", "cta_video_path", "outro_path", "thumbnail_font_path", "thumbnail_logo_path",
        "long_frame_path", "short_frame_path", "short_caption_font_path",
        mode="before",
    )
    @classmethod
    def _empty_path_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @field_validator("clip_formats")
    @classmethod
    def _formats(cls, value: list[str]) -> list[str]:
        formats = [v.lower() for v in value]
        unknown = set(formats) - {"long", "short"}
        if unknown or not formats:
            raise ValueError(f"CLIP_FORMATS aceita long e/ou short (recebido: {value})")
        return list(dict.fromkeys(formats))

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def face_model_path(self) -> Path:
        return self.data_dir / "models" / "blaze_face_short_range.tflite"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "clips"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "state.sqlite3"
