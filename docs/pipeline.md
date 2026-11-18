# Pipeline

`pipeline.py::Pipeline` orquestra tudo. `run_once()` percorre os vídeos da fonte e chama `process()` para cada um que o estado ainda não considera concluído.

## Fluxo de um vídeo

```
source.latest()                       (RSS, ou yt-dlp se o RSS falhar)
  └─ store.seen(id)?  sim → pula (exceto failed/waiting)
  └─ process(video)
       1. downloader.enrich      duração, descrição, data, live_status
       2. live em andamento?     → VideoWaiting, SEM gravar no estado
       3. _reject_reason         não é live / antigo demais / curto / longo → skipped
       4. _transcribe            legenda → (espera) → triagem → Whisper
       5. _select                um seletor por formato (long, short): IA sugere + regras fixas
       6. para cada candidato:
            limite diário atingido?     → retorna sem marcar o vídeo
            fila de postagem cheia?     → retorna sem marcar o vídeo
            já feito (clip_done)?       → pula
            baixa o vídeo completo (1x)
            _make_clip                  render do formato, metadados, thumbnail (long), publicação
       7. cleanup do download; marca o vídeo como done
```

Qualquer exceção em `process` marca o vídeo como `failed`, publica `PipelineError` e a rodada segue para o próximo.

## Etapas em detalhe

### 1. `enrich`
O RSS não traz duração nem estado de live. O `yt-dlp` (sem baixar) completa `duration`, `description`, `channel`, `live_status` e a data de publicação (`release_timestamp` ou `timestamp`) quando a fonte não a trouxe.

### 2. Live em andamento
`is_upcoming`, `is_live` e `post_live` retornam sem gravar nada: a próxima rodada reavalia sozinha.

### 3. Filtros de elegibilidade (`_reject_reason`)
Aplicados na ordem. Com `force=True` (comando `process`) as duas primeiras regras são ignoradas.

| Regra | Motivo registrado |
|---|---|
| `live_status != was_live` | `não é uma live` |
| Mais velho que `SOURCE_MAX_AGE_HOURS` | `antigo demais (Nh)` |
| Duração < `SOURCE_MIN_DURATION_SECONDS` | `muito curto (Ns)` |
| Duração > `SOURCE_MAX_DURATION_SECONDS` | `muito longo (Ns)` |

### 4. Transcrição
Detalhes em [transcription-and-relevance.md](transcription-and-relevance.md). Resumo: tenta a legenda do YouTube; se não existir e a live acabou há pouco, espera `LIVE_CAPTION_WAIT_MINUTES`; depois a IA faz triagem e só então o Whisper local transcreve.

### 5. Seleção
Um seletor por formato em `CLIP_FORMATS` (ou `--format` no comando `process`), cada um com prompt e regras próprios; os cortes longos vêm primeiro, depois os shorts. Detalhes em [clip-selection.md](clip-selection.md).

### 6. Fabricação de cada corte (`_make_clip`)
O arquivo sai em `data/clips/<id>_<formato>_<ini>_<fim>.mp4`.

**Corte longo** (`_render_long`):
1. **Silêncio:** se `SILENCE_CUT_ENABLED`, detecta pausas no trecho e planeja os trechos a manter. Senão, mantém o trecho inteiro.
2. **CTA:** se há `CTA_VIDEO_PATH` e o corte tem pelo menos `CTA_MIN_CLIP_SECONDS`, escolhe o ponto de inserção ([video-editing.md](video-editing.md)).
3. **Render:** `renderer.render(source, keep, out, insert_at)`.

**Short** (`_render_short`):
1. **Palavras:** `aligner.align` dá o tempo de cada palavra (Whisper no trecho, ou estimativa pela transcrição). Pulado com `SHORT_CAPTIONS=false`.
2. **Render:** `short_renderer.render(source, start, end, out, words)` enquadra, aplica moldura e legendas ([shorts.md](shorts.md)). Sem corte de silêncio nem CTA.

Depois, para os dois:
4. **Metadados:** título, descrição, tags e texto da thumbnail ([metadata.md](metadata.md)). Shorts ganham `#shorts`.
5. **Thumbnail:** opcional e **só no corte longo**; uma falha é registrada e a publicação segue sem ela.
6. **Publicação:** pede o próximo horário livre se a fila estiver ligada, envia, grava o corte em `clips` (com o formato) e publica `ClipPublished`.

## Estados de um vídeo

| Estado | Significado | `seen()` | Volta a ser processado? |
|---|---|---|---|
| (nenhum) | Live em andamento ou limite diário/fila cheia | falso | Sim, na próxima rodada |
| `waiting` | Live encerrada sem legenda, aguardando | falso | Sim, até passar `LIVE_CAPTION_WAIT_MINUTES` |
| `skipped` | Descartado com motivo | verdadeiro | Não |
| `done` | Todos os cortes processados | verdadeiro | Não |
| `failed` | Exceção durante o processamento | falso | Sim, na próxima rodada |

`mark_waiting` não altera `updated_at` se o vídeo já estava esperando, então o relógio da espera não é reiniciado a cada rodada.

## Limites que interrompem sem marcar o vídeo

- `MAX_PUBLISH_PER_DAY` (contado pelos **envios** feitos hoje, protege a cota da API).
- Fila de postagem cheia dentro de `PUBLISH_QUEUE_DAYS`.

Nos dois casos o loop de candidatos para, o vídeo não é marcado como `done`, e a rodada seguinte retoma os cortes que ainda faltam (`clip_done`, por vídeo + formato + tempos, evita repetir os já publicados). Longos e shorts dividem o mesmo limite diário e a mesma fila.

## Download e limpeza

O vídeo é baixado **inteiro uma vez** (até `MAX_SOURCE_HEIGHT`), pois baixar trechos é muito mais lento pelo limite de velocidade do YouTube. Os cortes são locais. O bloco `finally` chama `cleanup(video_id)`, que apaga o vídeo, o áudio e partes. Consequência: se o envio falhar, uma nova tentativa baixa e renderiza tudo de novo.

## Reprocessamento manual

`python -m castclipes process <url-ou-id> [--format long|short|both]` marca o vídeo como `failed` ("reprocessamento manual") para liberá-lo e roda `process(force=True)`, ignorando as regras de live e de idade.
