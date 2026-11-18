# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

Funcionário virtual que acompanha **lives de podcast** do YouTube, espera cada uma terminar e publica **cortes longos** (16:9, um assunto, 10 a 40 min) e **shorts** (9:16, um gancho de 20 a 85 s, com rosto enquadrado, split-screen e legenda palavra a palavra). Fork do projeto Jaguar XIV (cortes políticos), hoje exclusivo para podcasts; o enquadramento, o split-screen e as legendas dos shorts foram portados de `../video-automation/podcast-clipper`. O README e o `.env.example` (todas as variáveis, comentadas) são a documentação de uso; `docs/` explica o funcionamento por dentro. `PADROES_CANAL.md` e `IDEIA.md` (no `.gitignore`) são resquícios do projeto político e **não** valem mais.

## Comandos

Python 3.13 é obrigatório (usa sintaxe de type parameters, ex.: `def generate[T](...)`). Há um venv em `.venv`.

```powershell
pip install -e .[dev]                     # Whisper local é opcional: .[whisper]
.venv\Scripts\python -m pytest -q         # todos os testes
.venv\Scripts\python -m pytest tests/test_pipeline.py::test_happy_path_publishes_once -q   # um teste
.venv\Scripts\python -m ruff check src tests --fix   # lint (o CI roda `ruff check` + `pytest -q`)
python -m castclipes run | watch | process <url> [--format long|short|both] | resolve-channel @handle | auth-youtube
```

Não há formatador configurado (só `ruff check`). Os testes não precisam de rede nem chave de IA; os de render usam o ffmpeg do `imageio-ffmpeg` (e são pulados se ele não rodar) e trocam `analyze_framing` por um plano sintético para não baixar o modelo do MediaPipe.

## Arquitetura

`container.py::build_pipeline` é o composition root: monta tudo a partir de `config.Settings` (pydantic-settings, lido do `.env`). `pipeline.py::Pipeline` é um dataclass que recebe cada dependência como `Protocol` e orquestra:

RSS (playlist de lives) → `downloader.enrich` (yt-dlp, traz `live_status`) → legenda do YouTube → [sem legenda: triagem por IA → Whisper] → **um seletor por formato** (`CLIP_FORMATS`) → regras do `.env` → download do vídeo **completo** (1x) → render por formato → título/descrição/tags → publicação.

- **long** (`editing/ffmpeg_renderer.py`): corte de silêncio → moldura + vídeo de CTA no meio (`editing/insertion.py` escolhe a fronteira de frase) + outro, tudo num `filter_complex` só (`RENDER_ENGINE=moviepy` é a reserva lenta).
- **short** (`editing/vertical_renderer.py`): `WordAligner` dá o tempo das palavras → `vision/tracking.py::analyze_framing` planeja o enquadramento → `vision/composer.py::VerticalComposer` monta cada quadro 9:16 (bloco único ou split-screen) → os quadros vão por pipe a UM ffmpeg que junta áudio, moldura e legendas ASS (`captions/ass.py`). Sem corte de silêncio nem CTA.

Padrões usados (convenção do projeto: cada ponto de variação é um `Protocol` + implementações + uma factory simples):
- **Strategy**: `ClipSelector` (um por `ClipFormat`), `VideoTriage`, `TranscriptProvider`, `SilenceDetector`, `Renderer`, `ShortRenderer`, `WordAligner`, `Overlay`, `MetadataGenerator`, `Publisher`, `ThumbnailGenerator`, `LLMClient`.
- **Observer**: `events.py::EventBus`; o pipeline só publica eventos e `observers/listeners.py` (log, webhook) reage. Handler que falha não derruba o pipeline.
- **Factories**: `ai/factory.py`, `transcription/factory.py`, `editing/render_factory.py`, `editing/overlay.py::create_overlays(settings, formato)`, `captions/words.py::create_word_aligner`, `publishing/youtube.py::create_publisher`.

### Regras que atravessam vários arquivos

- **Só lives, regra fixa no código.** `SOURCE_LIVE_PLAYLIST_IDS` guarda IDs `UULV…` (a playlist automática de lives; `sources/rss.py::live_playlist_id` converte `UC…` em `UULV…`). `Pipeline._reject_reason` rejeita tudo que não for `live_status == "was_live"`; só o comando `process` usa `force=True` para ignorar isso.
- **Estados de espera.** Live agendada/no ar/`post_live` não é gravada no `StateStore` (a próxima rodada reavalia). Live encerrada sem legenda vira `waiting` por `LIVE_CAPTION_WAIT_MINUTES` antes de ir para triagem + Whisper. `StateStore.seen()` retorna False para `failed` e `waiting`, então esses vídeos voltam a ser processados. Atingir `MAX_PUBLISH_PER_DAY` também sai sem marcar o vídeo.
- **A IA propõe, o código decide.** `analysis/constraints.py` aplica duração mín./máx., fronteira de frase, nota mínima, sem sobreposição e limite por vídeo sobre o que a IA sugere. Cada formato tem as suas regras (`LONG_*`, `SHORT_*`), montadas em `container.py`. Mude regras de corte ali e no `.env`, não só no prompt. Formatos diferentes podem se sobrepor (short dentro de long); a sobreposição só é proibida dentro do mesmo formato. Transcrições longas são analisadas em janelas (`SELECTION_WINDOW_*`).
- **Vídeo completo, corte local.** O YouTube limita a velocidade de baixar trechos, então `downloader.download_video` baixa o vídeo inteiro uma vez e `cleanup(video_id)` apaga tudo no fim (`finally`). Detector de silêncio e renderers recebem tempos **absolutos** do arquivo completo; `plan_keep_ranges` trabalha em tempo relativo ao corte e o pipeline soma `candidate.start`. As palavras das legendas do short são o contrário: tempo **relativo** ao início do corte (o que o ASS usa).
- **Padrão de metadados.** Título conforme `TITLE_STYLE` (`natural` ou `upper`, `metadata/formatting.py::format_title`), prompt próprio por formato, descrição sempre com crédito e link do episódio original, tags fixas + dinâmicas respeitando o limite de 500 caracteres do YouTube. Shorts ganham a tag e a hashtag `shorts`. O prompt exige fidelidade: não atribuir fala a quem não está em `speakers`.
- **Molduras por formato.** `LONG_FRAME_PATH` (1920x1080) e `SHORT_FRAME_PATH` (1080x1920) são PNGs esticados sobre o vídeo (`fit=stretch`); `WATERMARK_*` fica por cima, nos dois. Proporção errada distorce.
- **Estado por formato.** `clips` tem chave `(source_id, format, start, end)`; longos e shorts dividem `MAX_PUBLISH_PER_DAY` e a fila de postagem.

### IA (AI SDK para Python, pacote `ai`, beta)

`LLMClient.generate(system, user, output_type)` devolve um modelo Pydantic (saída estruturada); os schemas ficam junto de quem usa (`ClipSuggestions`, `TriageVerdict`, `MetadataSuggestion`). `AiSdkClient` é um adaptador síncrono sobre a API assíncrona do SDK e mantém **um event loop persistente**: `asyncio.run` por chamada quebra a segunda requisição, porque o cliente HTTP fica preso ao loop. Com `AI_BASE_URL` definido o protocolo vira chat completions automaticamente (`AI_PROTOCOL=auto`), pois o padrão do provedor `openai` é a Responses API, que Ollama/vLLM/proxies não suportam.

## Testes

`tests/test_pipeline.py` testa o pipeline inteiro com dublês (`FakeDownloader`, `FakeSelector`, `FakeShortRenderer`, ...); novos testes de pipeline devem seguir o helper `build()` dali (ele recebe `clip_formats=`; o padrão do helper é só `long`). `tests/test_shorts.py` cobre legendas ASS, tempo por palavra, `VerticalComposer` com imagens sintéticas e o render vertical de ponta a ponta. `tests/test_ai_client.py` sobe um servidor HTTP local que imita chat completions com SSE para exercitar o SDK de verdade.

## Armadilhas

- Shorts: `vision/tracking.py` e `vision/detection.py` são portados do podcast-clipper quase sem mudança (comentários em inglês, parâmetros calibrados lá). O modelo BlazeFace é baixado para `data/models/` no primeiro uso. A nota de "quem fala" vem do movimento da boca e é ruidosa; só desempata. `short_split_chance` é sorteio (o teste injeta `random.Random`).
- Legenda do short: o filtro `subtitles` do ffmpeg quebra com caminho `C:\...`, então o ASS e a fonte vão para um diretório temporário e o ffmpeg roda nele (`cwd`) com nomes relativos. `SHORT_CAPTIONS_WHISPER` precisa do extra `.[whisper]`; sem ele cai para tempo estimado pela legenda do YouTube (impreciso).
- A `moldura_castclipes.png` do podcast-clipper é 16:9: serve ao long, não ao short.
- Os feeds RSS do YouTube deram 404 no ambiente de desenvolvimento e nunca foram validados ali; a playlist `UULV` foi confirmada via yt-dlp. Se o RSS falhar, `RssVideoSource` só registra o erro e segue.
- yt-dlp avisa que falta runtime JavaScript (deno/node); sem ele, formatos podem faltar.
- Thumbnails (`THUMBNAIL_PROVIDER=template`, padrão `none`, só para cortes longos): sem IA generativa. `thumbnails/template.py::FrameSelector` amostra frames do vídeo **completo** (`source_file`, tempos absolutos), `faces.py` detecta rostos (MediaPipe, modelo baixado para `data/models/` na 1ª vez), `scoring.py` pontua rosto + pouca borda fora do rosto + nitidez, `layout.py` decide zoom e lado do texto, e o template xpict.py desenha. O texto vem de `ClipMetadata.thumbnail_text` (IA) ou do fim do título. Falha na thumbnail não derruba a publicação. Os limiares de `scoring.py` são chutes ainda sem calibração com frames reais.
- Fila de postagem (`PUBLISH_SCHEDULE_ENABLED`): `publishing/schedule.py::next_slot` escolhe o horário livre (ocupados ficam em `clips.scheduled_for`) e `YouTubePublisher` envia como privado com `publishAt`; `YOUTUBE_PRIVACY_STATUS` é ignorado nesse caso. Fila cheia (`PUBLISH_QUEUE_DAYS`) faz o pipeline parar sem marcar o vídeo.
- Publicar custa ~1.600 unidades da cota de 10.000/dia da API do YouTube. `PUBLISH_MODE` começa em `dry_run` e `YOUTUBE_PRIVACY_STATUS` em `private`.
