# Jaguar XIV - Clipador da Missão/MBL

Funcionário virtual que monitora canais do YouTube (RSS), encontra trechos em que Renan Santos, Arthur do Val, membros do MBL ou o Partido Missão são protagonistas ou alvo, gera cortes e os publica. O formato segue o padrão: cortes longos (10 a 40 min), um assunto por corte, título em caixa alta e descrição com crédito à fonte.

## Fluxo

```
RSS -> yt-dlp (metadados) -> legenda do YouTube ──┐
                                 sem legenda ──> triagem por IA ──> Whisper
                                                                       │
 pré-filtro de menções <───────────────────────────────────────────────┘
 -> IA escolhe cortes (janelas) -> regras do .env (min/max, sem sobreposição)
 -> yt-dlp baixa o vídeo completo (1x) -> corte local + silêncio -> overlays/outro (moviepy)
 -> título/descrição/tags -> YouTube Data API v3
```

A IA propõe os cortes, mas `analysis/constraints.py` aplica as regras do `.env` (duração mínima/máxima, fronteira de frase, nota mínima, limite por vídeo).

## Design patterns

| Padrão | Onde |
|---|---|
| Simple Factory | `ai/factory.py`, `transcription/factory.py`, `editing/overlay.py::create_overlays`, `publishing/youtube.py::create_publisher`, `thumbnails/base.py` |
| Strategy | `ClipSelector`, `VideoTriage`, `TranscriptProvider`, `SilenceDetector`, `Overlay`, `MetadataGenerator`, `Publisher`, `ThumbnailGenerator` (todos `Protocol`) |
| Observer | `events.py` (`EventBus`) + `observers/listeners.py` (log, webhook) |
| Composition root | `container.py` monta o `Pipeline` a partir de `Settings` |

## Uso

```powershell
python -m venv .venv; .venv\Scripts\activate
pip install -e .[dev]            # Whisper local é opcional: pip install -e .[whisper]
copy .env.example .env           # preencha AI_API_KEY e SOURCE_CHANNEL_IDS

python -m jaguar_xiv_missao resolve-channel @TVdoMBL   # descobre o channel_id
python -m jaguar_xiv_missao process <url-ou-id>        # processa um vídeo (teste)
python -m jaguar_xiv_missao run                        # uma verificação dos feeds
python -m jaguar_xiv_missao watch                      # loop contínuo
python -m jaguar_xiv_missao auth-youtube               # login OAuth (PUBLISH_MODE=youtube)
```

Requisitos: ffmpeg no PATH (o moviepy traz um próprio, usado no corte de silêncio).
Comece com `PUBLISH_MODE=dry_run` e confira os arquivos em `data/clips/`.

## Variáveis de ambiente principais

Veja `.env.example` (todas comentadas). Destaques:

- `CLIP_MIN_SECONDS`, `CLIP_MAX_SECONDS`, `CLIP_TARGET_SECONDS`, `CLIP_MIN_SCORE`, `MAX_CLIPS_PER_VIDEO`: forma dos cortes.
- `SOURCE_MIN_DURATION_SECONDS`, `SOURCE_MAX_DURATION_SECONDS`, `SOURCE_MAX_AGE_HOURS`: quais vídeos-fonte entram.
- `MIN_KEYWORD_MENTIONS`, `TARGET_KEYWORDS`, `TRIAGE_MIN_SCORE`: relevância e gasto com Whisper.
- `SILENCE_*`: sensibilidade do corte de silêncio (limiar em dB, pausa mínima, folga mantida).
- `WATERMARK_*`, `CTA_*`, `OUTRO_PATH`: overlays (PNG com transparência) e vídeo de encerramento.
- `AI_PROVIDER`, `AI_MODEL`, `AI_BASE_URL`, `AI_API_KEY`: modelo via [AI SDK para Python](https://pypi.org/project/ai/) (Vercel). Qualquer provedor do models.dev; `AI_BASE_URL` serve para Ollama, vLLM e proxies.
- `MAX_PUBLISH_PER_DAY`, `YOUTUBE_PRIVACY_STATUS`, `PUBLISH_MODE`: publicação.

## Limitações conhecidas

- **Cota do YouTube**: o upload custa ~1.600 unidades; a cota padrão (10.000/dia) comporta ~6 envios/dia. Projetos de API novos e não auditados publicam como privado até passarem pela auditoria do Google.
- **Direitos autorais**: os cortes reaproveitam conteúdo de terceiros. A descrição sempre credita e linka o vídeo original, mas confirme a política de cada canal-fonte.
- **moviepy** é lento em vídeos longos (um corte de 20 min em 1080p leva vários minutos). Ajuste `RENDER_PRESET`.
- **Thumbnails**: `NullThumbnailGenerator` por enquanto (provedor e prompt em aberto).
- O AI SDK para Python (`ai` 0.9) está em beta público; a API pode mudar entre versões.

## Licença

[MIT](LICENSE)
