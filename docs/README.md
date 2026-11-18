# Documentação do CastClipes

Funcionário virtual que acompanha **lives de podcast** do YouTube, espera cada uma terminar e publica **cortes longos** (16:9, um assunto por corte) e **shorts** (9:16, um gancho, com rosto enquadrado e legenda animada).

Esta pasta explica como a aplicação funciona por dentro, um domínio por arquivo. Para começar a usar, o `README.md` da raiz e o `.env.example` bastam; aqui está o "porquê" e o "como".

## Índice

| Arquivo | Assunto |
|---|---|
| [overview.md](overview.md) | O que o projeto faz, regras de produto e glossário |
| [architecture.md](architecture.md) | Camadas, design patterns, composition root, modelos de domínio |
| [pipeline.md](pipeline.md) | Fluxo completo de um vídeo, estados de espera e tratamento de falhas |
| [sources.md](sources.md) | Descoberta de lives: RSS, reserva via yt-dlp, `enrich`, filtros |
| [transcription-and-relevance.md](transcription-and-relevance.md) | Legenda do YouTube, triagem por IA e Whisper |
| [clip-selection.md](clip-selection.md) | Como a IA sugere cortes (long e short) e como o código decide |
| [video-editing.md](video-editing.md) | Corte longo: silêncio, moldura, CTA no meio, outro e renderização com ffmpeg |
| [shorts.md](shorts.md) | Short 9:16: rastreamento de rostos, split-screen, legendas palavra a palavra e moldura vertical |
| [metadata.md](metadata.md) | Título, descrição, tags e hashtags |
| [thumbnails.md](thumbnails.md) | Geração de thumbnail sem IA generativa |
| [publishing.md](publishing.md) | Upload no YouTube, OAuth, cota e fila de postagem |
| [ai.md](ai.md) | Cliente de IA, provedores, OpenRouter, retry |
| [state-and-data.md](state-and-data.md) | Banco SQLite, pastas de dados e limpeza |
| [configuration.md](configuration.md) | Todas as variáveis do `.env`, por grupo |
| [operations.md](operations.md) | Instalação, comandos, produção e solução de problemas |
| [development.md](development.md) | Testes, convenções e como estender o projeto |

## Mapa rápido do código

```
src/castclipes/
  cli.py, __main__.py        comandos (run, watch, process, resolve-channel, auth-youtube)
  config.py                  Settings (pydantic-settings, lê o .env)
  container.py               composition root: monta o Pipeline
  pipeline.py                orquestra todas as etapas
  models.py                  modelos de domínio
  events.py, observers/      Observer: eventos e listeners (log, webhook)
  sources/                   RSS e reserva via yt-dlp
  downloader.py              yt-dlp: metadados, vídeo completo, áudio
  transcription/             legenda do YouTube e Whisper
  analysis/                  triagem, seleção por formato, regras determinísticas
  editing/                   silêncio, CTA, overlays, renderers (long e vertical)
  vision/                    rostos, rastreamento e composição do quadro vertical
  captions/                  tempo por palavra e legendas ASS dos shorts
  metadata/                  título, descrição, tags
  thumbnails/                frame + rosto + template (só long)
  publishing/                YouTube, dry-run, fila de postagem
  storage/state.py           SQLite
  ai/                        cliente do AI SDK
```

## Créditos

O enquadramento por rosto, o split-screen e as legendas dos shorts vêm do [podcast-clipper](https://github.com/marcuth/podcast-clipper).
