# Documentação do Jaguar XIV

Funcionário virtual que acompanha **lives** do YouTube (MBL, Renan Santos, Arthur do Val, Partido Missão), espera cada uma terminar e publica **cortes longos** (10 a 40 minutos, um assunto por corte), no padrão do canal "Inevitável Cortes".

Esta pasta explica como a aplicação funciona por dentro, um domínio por arquivo. Para começar a usar, o `README.md` da raiz e o `.env.example` bastam; aqui está o "porquê" e o "como".

## Índice

| Arquivo | Assunto |
|---|---|
| [overview.md](overview.md) | O que o projeto faz, regras de produto e glossário |
| [architecture.md](architecture.md) | Camadas, design patterns, composition root, modelos de domínio |
| [pipeline.md](pipeline.md) | Fluxo completo de um vídeo, estados de espera e tratamento de falhas |
| [sources.md](sources.md) | Descoberta de lives: RSS, reserva via yt-dlp, `enrich`, filtros |
| [transcription-and-relevance.md](transcription-and-relevance.md) | Legenda do YouTube, triagem por IA, Whisper e pré-filtro de menções |
| [clip-selection.md](clip-selection.md) | Como a IA sugere cortes e como o código decide |
| [video-editing.md](video-editing.md) | Corte de silêncio, moldura, CTA no meio, outro e renderização com ffmpeg |
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
src/jaguar_xiv_missao/
  cli.py, __main__.py        comandos (run, watch, process, resolve-channel, auth-youtube)
  config.py                  Settings (pydantic-settings, lê o .env)
  container.py               composition root: monta o Pipeline
  pipeline.py                orquestra todas as etapas
  models.py                  modelos de domínio
  events.py, observers/      Observer: eventos e listeners (log, webhook)
  sources/                   RSS e reserva via yt-dlp
  downloader.py              yt-dlp: metadados, vídeo completo, áudio
  transcription/             legenda do YouTube e Whisper
  analysis/                  triagem, seleção, regras determinísticas
  editing/                   silêncio, CTA, overlays, renderers
  metadata/                  título, descrição, tags
  thumbnails/                frame + rosto + template
  publishing/                YouTube, dry-run, fila de postagem
  storage/state.py           SQLite
  ai/                        cliente do AI SDK
```

## Aviso

Projeto independente e não oficial. O autor, Marcuth, não tem ligação com o MBL nem com o Partido Missão: é apenas um apoiador.
