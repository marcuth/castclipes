# Arquitetura

## Visão em camadas

```
cli.py ──> container.py (composition root) ──> Pipeline
                                                  │ usa, via Protocol:
   VideoSource · TranscriptProvider · VideoTriage · ClipSelector (um por formato) · SilenceDetector
   Renderer · ShortRenderer · WordAligner · MetadataGenerator · ThumbnailGenerator · Publisher · StateStore · EventBus
```

- `models.py` não depende de nada externo: são só dataclasses.
- `pipeline.py` conhece apenas **interfaces** (`Protocol`), nunca implementações concretas.
- `container.py::build_pipeline` é o único lugar que escolhe implementações a partir de `Settings`.

## Design patterns

Convenção do projeto: cada ponto de variação é um `Protocol` + implementações + uma factory simples.

| Padrão | Onde |
|---|---|
| **Strategy** | `ClipSelector`, `VideoTriage`, `TranscriptProvider`, `SilenceDetector`, `Renderer`, `ShortRenderer`, `WordAligner`, `Overlay`, `MetadataGenerator`, `Publisher`, `ThumbnailGenerator`, `LLMClient` |
| **Simple Factory** | `ai/factory.py`, `transcription/factory.py`, `editing/render_factory.py`, `editing/overlay.py::create_overlays` (por formato), `captions/words.py::create_word_aligner`, `publishing/youtube.py::create_publisher`, `thumbnails/base.py::create_thumbnail_generator` |
| **Observer** | `events.py::EventBus` + `observers/listeners.py` |
| **Composition root** | `container.py::build_pipeline` |

### Exemplos de Strategy com mais de uma implementação

| Interface | Implementações | Escolha |
|---|---|---|
| `Renderer` | `FfmpegRenderer` (padrão), `ClipRenderer` (moviepy, reserva lenta) | `RENDER_ENGINE` |
| `Publisher` | `YouTubePublisher`, `DryRunPublisher`; `FacebookPublisher`, `InstagramPublisher`, `ThreadsPublisher` (via `CrosspostQueue`) | `PUBLISH_MODE` |
| `ThumbnailGenerator` | `XpictThumbnailGenerator`, `NullThumbnailGenerator` | `THUMBNAIL_PROVIDER` |
| `SilenceDetector` | `FfmpegSilenceDetector`, `NullSilenceDetector` | `SILENCE_CUT_ENABLED` |
| `TranscriptProvider` | `YouTubeTranscriptProvider` (primário), `WhisperTranscriptProvider` (reserva) | fixo no container |
| `ClipSelector` | `LLMClipSelector` por formato, com prompt e regras próprios | `CLIP_FORMATS` |
| `WordAligner` | `WhisperWordAligner`, `TranscriptWordAligner`, `FallbackWordAligner` | `SHORT_CAPTIONS_WHISPER` |

## Observer: eventos

O pipeline só **publica** eventos; quem reage são os observers. Um handler que lança exceção é registrado em log e **não derruba** o pipeline.

| Evento | Quando |
|---|---|
| `VideoDiscovered` | Vídeo entra no processamento |
| `VideoWaiting` | Live ainda não pronta ou aguardando legenda |
| `VideoSkipped` | Descartado, com o motivo |
| `TranscriptReady` | Transcrição obtida (fonte e nº de segmentos) |
| `ClipsSelected` | Candidatos finais depois das regras |
| `ClipRendered` | Arquivo do corte pronto |
| `ClipPublished` | Enviado/agendado (ou dry-run) |
| `PipelineError` | Falha ao processar um vídeo |

Observers incluídos: `LoggingObserver` (log legível em português) e `WebhookObserver` (envia só `ClipPublished` e `PipelineError` para `NOTIFY_WEBHOOK_URL`, formato compatível com Discord e Slack).

## Modelos de domínio (`models.py`)

- `SourceVideo`: id, título, descrição, canal, `published_at`, duração e `live_status`. As propriedades `live_in_progress` (`is_upcoming`, `is_live`, `post_live`) e `live_ended` (`was_live`) guiam as decisões de espera.
- `Transcript` / `TranscriptSegment` / `Word`: segmentos com início e fim em segundos; `words` (tempo por palavra) vem preenchido só quando a fonte entrega. `render()` produz texto com marcadores `[Ns]` a cada 15 s para os prompts; `window()` e `text_between()` recortam.
- `ClipFormat`: `long` (16:9) ou `short` (9:16).
- `ClipCandidate`: `start`, `end`, tema, nota (0 a 1), formato, gancho (`hook`), falantes e resumo.
- `ClipMetadata`: título, descrição, tags e `thumbnail_text`.
- `RenderedClip`: candidato, vídeo-fonte, caminho do arquivo, duração, metadados e thumbnail.
- `PublishResult`: `video_id`, `url` e `dry_run`.

## Tempos absolutos e relativos

Detector de silêncio, renderers e thumbnails recebem tempos **absolutos** do arquivo completo baixado. No short, o alinhador de palavras devolve tempo **relativo ao corte** (t=0 é o início dele), que é o que a legenda do Remotion usa. `plan_keep_ranges` trabalha em tempo **relativo ao corte** e o pipeline soma `candidate.start`. `editing/insertion.py::to_relative` converte o ponto de CTA (absoluto) para o tempo do corte já sem silêncios.

## Decisões de design

- **IA com saída estruturada.** `LLMClient.generate(system, user, output_type)` devolve um modelo Pydantic validado. Os schemas ficam junto de quem usa (`ClipSuggestions`, `TriageVerdict`, `MetadataSuggestion`).
- **Imports tardios.** `mediapipe`, `xpict`, `moviepy` e `faster-whisper` só são importados quando o recurso é usado, para o projeto subir rápido e os testes não exigirem tudo.
- **Falhas isoladas.** Thumbnail e observers nunca derrubam a publicação; falha de um vídeo marca `failed` e a rodada segue para o próximo.
