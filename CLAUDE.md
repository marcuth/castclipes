# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

Funcionário virtual que acompanha **lives** do YouTube (MBL, Renan Santos, Arthur do Val, Missão), espera cada uma terminar e publica cortes longos (10 a 40 min, um assunto por corte), imitando o canal Inevitável Cortes. O README e o `.env.example` (todas as variáveis, comentadas) são a documentação de uso. `PADROES_CANAL.md` registra o padrão do canal-alvo (formato, título, descrição, tags) e é a fonte das decisões de produto; `IDEIA.md` é o briefing original. Os dois estão no `.gitignore` de propósito.

## Comandos

Python 3.13 é obrigatório (usa sintaxe de type parameters, ex.: `def generate[T](...)`). Há um venv em `.venv`.

```powershell
pip install -e .[dev]                     # Whisper local é opcional: .[whisper]
.venv\Scripts\python -m pytest -q         # todos os testes
.venv\Scripts\python -m pytest tests/test_pipeline.py::test_happy_path_publishes_once -q   # um teste
.venv\Scripts\python -m ruff check src tests --fix   # lint (o CI roda `ruff check` + `pytest -q`)
python -m jaguar_xiv_missao run | watch | process <url> | resolve-channel @handle | auth-youtube
```

Não há formatador configurado (só `ruff check`). Os testes não precisam de rede, ffmpeg nem chave de IA.

## Arquitetura

`container.py::build_pipeline` é o composition root: monta tudo a partir de `config.Settings` (pydantic-settings, lido do `.env`). `pipeline.py::Pipeline` é um dataclass que recebe cada dependência como `Protocol` e orquestra:

RSS (playlist de lives) → `downloader.enrich` (yt-dlp, traz `live_status`) → legenda do YouTube → [sem legenda: triagem por IA → Whisper] → pré-filtro de menções → IA escolhe cortes → regras do `.env` → download do vídeo **completo** (1x) → corte de silêncio → overlays + vídeo de CTA no meio (`editing/insertion.py` escolhe a fronteira de frase) + outro (`editing/ffmpeg_renderer.py`: um `filter_complex` só; `RENDER_ENGINE=moviepy` é a reserva lenta) → título/descrição/tags → publicação.

Padrões usados (convenção do projeto: cada ponto de variação é um `Protocol` + implementações + uma factory simples):
- **Strategy**: `ClipSelector`, `VideoTriage`, `TranscriptProvider`, `SilenceDetector`, `Overlay`, `MetadataGenerator`, `Publisher`, `ThumbnailGenerator`, `LLMClient`.
- **Observer**: `events.py::EventBus`; o pipeline só publica eventos e `observers/listeners.py` (log, webhook) reage. Handler que falha não derruba o pipeline.
- **Factories**: `ai/factory.py`, `transcription/factory.py`, `editing/overlay.py::create_overlays`, `publishing/youtube.py::create_publisher`.

### Regras que atravessam vários arquivos

- **Só lives, regra fixa no código.** `SOURCE_LIVE_PLAYLIST_IDS` guarda IDs `UULV…` (a playlist automática de lives; `sources/rss.py::live_playlist_id` converte `UC…` em `UULV…`). `Pipeline._reject_reason` rejeita tudo que não for `live_status == "was_live"`; só o comando `process` usa `force=True` para ignorar isso.
- **Estados de espera.** Live agendada/no ar/`post_live` não é gravada no `StateStore` (a próxima rodada reavalia). Live encerrada sem legenda vira `waiting` por `LIVE_CAPTION_WAIT_MINUTES` antes de ir para triagem + Whisper. `StateStore.seen()` retorna False para `failed` e `waiting`, então esses vídeos voltam a ser processados. Atingir `MAX_PUBLISH_PER_DAY` também sai sem marcar o vídeo.
- **A IA propõe, o código decide.** `analysis/constraints.py` aplica duração mín./máx., fronteira de frase, nota mínima, sem sobreposição e limite por vídeo sobre o que a IA sugere. Mude regras de corte ali e no `.env`, não só no prompt. Transcrições longas são analisadas em janelas (`SELECTION_WINDOW_*`).
- **Vídeo completo, corte local.** O YouTube limita a velocidade de baixar trechos, então `downloader.download_video` baixa o vídeo inteiro uma vez e `cleanup(video_id)` apaga tudo no fim (`finally`). Detector de silêncio e renderer recebem tempos **absolutos** do arquivo completo; `plan_keep_ranges` trabalha em tempo relativo ao corte e o pipeline soma `candidate.start`.
- **Padrão de metadados.** Título em CAIXA ALTA com preposições em minúsculo (`metadata/formatting.py::format_title`), descrição sempre com crédito e link do vídeo original, tags fixas + dinâmicas respeitando o limite de 500 caracteres do YouTube.

### IA (AI SDK para Python, pacote `ai`, beta)

`LLMClient.generate(system, user, output_type)` devolve um modelo Pydantic (saída estruturada); os schemas ficam junto de quem usa (`ClipSuggestions`, `TriageVerdict`, `MetadataSuggestion`). `AiSdkClient` é um adaptador síncrono sobre a API assíncrona do SDK e mantém **um event loop persistente**: `asyncio.run` por chamada quebra a segunda requisição, porque o cliente HTTP fica preso ao loop. Com `AI_BASE_URL` definido o protocolo vira chat completions automaticamente (`AI_PROTOCOL=auto`), pois o padrão do provedor `openai` é a Responses API, que Ollama/vLLM/proxies não suportam.

## Testes

`tests/test_pipeline.py` testa o pipeline inteiro com dublês (`FakeDownloader`, `FakeSelector`, ...); novos testes de pipeline devem seguir o helper `build()` dali. `tests/test_ai_client.py` sobe um servidor HTTP local que imita chat completions com SSE para exercitar o SDK de verdade.

## Armadilhas

- Os feeds RSS do YouTube deram 404 no ambiente de desenvolvimento e nunca foram validados ali; a playlist `UULV` foi confirmada via yt-dlp. Se o RSS falhar, `RssVideoSource` só registra o erro e segue.
- yt-dlp avisa que falta runtime JavaScript (deno/node); sem ele, formatos podem faltar.
- Thumbnails (`THUMBNAIL_PROVIDER=template`, padrão `none`): sem IA generativa. `thumbnails/template.py::FrameSelector` amostra frames do vídeo **completo** (`source_file`, tempos absolutos), `faces.py` detecta rostos (MediaPipe, modelo baixado para `data/models/` na 1ª vez), `scoring.py` pontua rosto + pouca borda fora do rosto + nitidez, `layout.py` decide zoom e lado do texto, e o template xpict.py desenha. O texto vem de `ClipMetadata.thumbnail_text` (IA) ou do fim do título. Falha na thumbnail não derruba a publicação. Os limiares de `scoring.py` são chutes ainda sem calibração com frames reais.
- Fila de postagem (`PUBLISH_SCHEDULE_ENABLED`): `publishing/schedule.py::next_slot` escolhe o horário livre (ocupados ficam em `clips.scheduled_for`) e `YouTubePublisher` envia como privado com `publishAt`; `YOUTUBE_PRIVACY_STATUS` é ignorado nesse caso. Fila cheia (`PUBLISH_QUEUE_DAYS`) faz o pipeline parar sem marcar o vídeo.
- Publicar custa ~1.600 unidades da cota de 10.000/dia da API do YouTube. `PUBLISH_MODE` começa em `dry_run` e `YOUTUBE_PRIVACY_STATUS` em `private`.
