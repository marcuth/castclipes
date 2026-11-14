<p align="center">
  <img src="docs/images/jaugar-circle.png" alt="Jaguar XIV" width="200">
</p>

# Jaguar XIV - Clipador da Missão/MBL

📺 Canal no YouTube: [@jaguarxiv](https://www.youtube.com/@jaguarxiv)

Funcionário virtual que monitora canais do YouTube (RSS), acompanha **lives** (RSS), espera cada uma terminar, encontra trechos em que Renan Santos, Arthur do Val, membros do MBL ou o Partido Missão são protagonistas ou alvo, gera cortes e os publica. O formato segue o padrão: cortes longos (10 a 40 min), um assunto por corte, título em caixa alta e descrição com crédito à fonte.

## Fluxo

```
RSS -> yt-dlp (metadados + live_status)
   live agendada/no ar/recém-encerrada -> espera, sem marcar no estado
   upload comum -> ignorado (regra fixa no código)
   live encerrada -> legenda do YouTube ──┐
   (sem legenda: espera LIVE_CAPTION_WAIT_MINUTES)
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
copy .env.example .env           # preencha AI_API_KEY e SOURCE_LIVE_PLAYLIST_IDS

python -m jaguar_xiv_missao resolve-channel @TVdoMBL   # descobre o ID da playlist de lives
python -m jaguar_xiv_missao process <url-ou-id>        # processa um vídeo (ignora as regras de live)
python -m jaguar_xiv_missao run                        # uma verificação dos feeds
python -m jaguar_xiv_missao watch                      # loop contínuo
python -m jaguar_xiv_missao auth-youtube               # login OAuth (PUBLISH_MODE=youtube)
```

Requisitos: ffmpeg no PATH (o moviepy traz um próprio, usado no corte de silêncio).
Comece com `PUBLISH_MODE=dry_run` e confira os arquivos em `data/clips/`.

## Como descobrir o ID da playlist de lives

O projeto só processa **lives** (regra fixa no código). Cada canal tem uma playlist automática só com as lives, cujo ID começa com `UULV`, e o feed RSS dela é `https://www.youtube.com/feeds/videos.xml?playlist_id=<ID>`.

- Pelo site: https://newskeeper.pages.dev/tools/youtube-rss
- Pelo terminal: `python -m jaguar_xiv_missao resolve-channel @TVdoMBL`
- À mão: pegue o ID do canal (`UC...`) e troque `UC` por `UULV`. O projeto também aceita o ID do canal e faz essa troca sozinho.

Coloque o resultado em `SOURCE_LIVE_PLAYLIST_IDS` (vários IDs separados por vírgula).

## Variáveis de ambiente principais

Veja `.env.example` (todas comentadas). Destaques:

- `CLIP_MIN_SECONDS`, `CLIP_MAX_SECONDS`, `CLIP_TARGET_SECONDS`, `CLIP_MIN_SCORE`, `MAX_CLIPS_PER_VIDEO`: forma dos cortes.
- `SOURCE_LIVE_PLAYLIST_IDS`: playlists de lives monitoradas (veja abaixo). `LIVE_CAPTION_WAIT_MINUTES`: só lives encerradas entram; sem legenda, espera antes de gastar Whisper.
- `SOURCE_MIN_DURATION_SECONDS`, `SOURCE_MAX_DURATION_SECONDS`, `SOURCE_MAX_AGE_HOURS`: quais vídeos-fonte entram.
- `MIN_KEYWORD_MENTIONS`, `TARGET_KEYWORDS`, `TRIAGE_MIN_SCORE`: relevância e gasto com Whisper.
- `SILENCE_*`: sensibilidade do corte de silêncio (limiar em dB, pausa mínima, folga mantida).
- `WATERMARK_*`, `OUTRO_PATH`: overlay (PNG com transparência) e vídeo de encerramento. `WATERMARK_FIT=stretch` faz o PNG ocupar o vídeo inteiro (moldura), em qualquer resolução.
- `CTA_VIDEO_PATH`, `CTA_POSITION_PCT`, `CTA_MIN_CLIP_SECONDS`: vídeo de CTA/anúncio inserido no meio do corte, numa pausa entre frases perto de `CTA_POSITION_PCT` (sem overlays). Cortes curtos não recebem.
- `AI_PROVIDER`, `AI_MODEL`, `AI_BASE_URL`, `AI_API_KEY`: modelo via [AI SDK para Python](https://pypi.org/project/ai/) (Vercel). Qualquer provedor do models.dev; `AI_BASE_URL` serve para Ollama, vLLM e proxies. `AI_MAX_RETRIES` (opcional, padrão 0) repete chamadas que falham (429, 5xx, resposta vazia) com espera crescente a partir de `AI_RETRY_DELAY_SECONDS`.
- `MAX_PUBLISH_PER_DAY`, `YOUTUBE_PRIVACY_STATUS`, `PUBLISH_MODE`: publicação.

## Limitações conhecidas

- **Lives são processadas depois que terminam**, não em tempo real. Uma live de 3 h baixada em 1080p ocupa vários GB; reduza `MAX_SOURCE_HEIGHT` se faltar disco.
- **yt-dlp** precisa de um runtime JavaScript (deno ou node) para extrair o YouTube sem formatos faltando. Veja https://github.com/yt-dlp/yt-dlp/wiki/EJS.
- **Cota do YouTube**: o upload custa ~1.600 unidades; a cota padrão (10.000/dia) comporta ~6 envios/dia. Projetos de API novos e não auditados publicam como privado até passarem pela auditoria do Google.
- **Direitos autorais**: os cortes reaproveitam conteúdo de terceiros. A descrição sempre credita e linka o vídeo original, mas confirme a política de cada canal-fonte.
- **Render**: o padrão é ffmpeg puro (`RENDER_ENGINE=ffmpeg`), bem mais rápido que o moviepy (`RENDER_ENGINE=moviepy`, reserva: passa cada frame pelo Python e leva dezenas de minutos por corte longo). Ajuste `RENDER_PRESET` para trocar tempo por tamanho de arquivo.
- **Thumbnails**: desligadas por padrão (`THUMBNAIL_PROVIDER=none`). Com `template`, o pipeline amostra frames do corte, detecta rostos (MediaPipe/BlazeFace, do Google), escolhe o frame com rosto bem enquadrado e fundo limpo, dá zoom no rosto e escreve o gancho em Anton via template [xpict.py](https://pypi.org/project/xpict.py/). Sem IA generativa; os limiares de nota (`thumbnails/scoring.py`) ainda não foram calibrados com frames reais das lives.
- O AI SDK para Python (`ai` 0.9) está em beta público; a API pode mudar entre versões.

## Aviso

Este é um projeto independente e não oficial. O autor, Marcuth, não tem nenhuma ligação com o MBL ou com o Partido Missão: é apenas um apoiador.

## Licença

[MIT](LICENSE)
