# Estado e dados

Código: `storage/state.py`, propriedades de `config.py`.

## Pastas (sob `DATA_DIR`, padrão `data/`)

| Caminho | Conteúdo | Ciclo de vida |
|---|---|---|
| `data/state.sqlite3` | Banco de estado | Permanente |
| `data/clips/` | Cortes renderizados `<id>_<início>_<fim>.mp4` e thumbnails `.jpg` | **Ficam** depois da publicação; apague à mão se precisar de espaço |
| `data/work/` | Vídeo completo baixado, áudio do Whisper | Apagado no fim de cada vídeo (`cleanup`) |
| `data/models/` | Modelo de rosto `blaze_face_short_range.tflite` | Baixado na 1ª vez |

`data/` está no `.gitignore`. O mesmo vale para `.env`, `secrets/*.json`, `*.mp4` e PNGs em `assets/`.

> Uma live de 3 h em 1080p ocupa vários GB em `data/work/` durante o processamento. Reduza `MAX_SOURCE_HEIGHT` se faltar disco.

## Banco SQLite

Duas tabelas, criadas automaticamente.

### `videos`
Estado de cada vídeo-fonte.

| Coluna | Descrição |
|---|---|
| `id` | ID do vídeo (chave) |
| `status` | `waiting`, `skipped`, `done` ou `failed` |
| `reason` | Motivo (descarte ou exceção) |
| `updated_at` | Data/hora UTC da última mudança |

### `clips`
Cada corte feito, para não repetir e para a cota e a fila.

| Coluna | Descrição |
|---|---|
| `source_id`, `start`, `end` | Chave: vídeo-fonte e tempos do corte |
| `title` | Título gerado |
| `youtube_id` | ID no YouTube (nulo em `dry_run`) |
| `published_at` | Quando o envio foi feito (UTC) |
| `scheduled_for` | Horário agendado (UTC); nulo se sem fila ou em `dry_run` |

Bancos criados antes da fila ganham a coluna `scheduled_for` automaticamente na abertura.

## Operações do `StateStore`

| Método | Uso |
|---|---|
| `seen(id)` | Já foi concluído/descartado? Falso para `failed` e `waiting` |
| `mark(id, status, reason)` | Grava o estado |
| `mark_waiting` / `waiting_since` | Controla a espera pela legenda sem reiniciar o relógio |
| `clip_done(id, start, end)` | O corte já foi feito? |
| `record_clip(...)` | Registra o corte (e o horário agendado) |
| `published_today()` | Envios feitos hoje (UTC), para `MAX_PUBLISH_PER_DAY` |
| `scheduled_times()` | Horários ocupados na fila (de ontem em diante) |

## Reiniciar do zero

Para reprocessar tudo, pare o processo e apague `data/state.sqlite3`. Para reprocessar um vídeo só, use `python -m jaguar_xiv_missao process <url-ou-id>`.
