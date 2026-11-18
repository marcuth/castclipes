# Publicação

Código: `publishing/youtube.py`, `publishing/schedule.py`, `publishing/base.py`.

## Modos (`PUBLISH_MODE`)

| Modo | Comportamento |
|---|---|
| `dry_run` (padrão) | Renderiza tudo, **não envia nada**; registra título, caminho, tags e o horário que seria agendado |
| `youtube` | Envia ao YouTube pela Data API v3 |

Comece em `dry_run`, confira os arquivos em `data/clips/`, depois passe a `youtube` com `YOUTUBE_PRIVACY_STATUS=private` antes de ir para `public`.

## Autenticação (OAuth)

1. No Google Cloud, ative a **YouTube Data API v3** e crie um OAuth client do tipo **"Aplicativo para computador"** (desktop). Não use "Aplicativo da Web".
2. Salve o JSON em `secrets/client_secret.json` (`YOUTUBE_CLIENT_SECRETS_FILE`).
3. Rode `python -m castclipes auth-youtube`. O navegador abre, você autoriza, e o token fica em `secrets/youtube_token.json` (`YOUTUBE_TOKEN_FILE`), renovado sozinho depois.

Escopos: `youtube.upload` e `youtube` (este necessário para definir thumbnail).

## Upload (`YouTubePublisher`)

- `videos.insert` com **upload resumível** em blocos de 8 MB; o progresso aparece no log.
- Corpo: título, descrição, tags, categoria (`YOUTUBE_CATEGORY_ID`, padrão 22 = Pessoas e blogs), idioma `pt-BR`, `selfDeclaredMadeForKids=false`.
- Se há thumbnail, ela é enviada logo depois com `thumbnails.set`.
- Não há retry automático em erro de conexão: um `ConnectionAbortedError` no meio do upload derruba aquele vídeo (marcado `failed`) e ele é tentado de novo na rodada seguinte, refazendo download e render.

## Cota da API

O upload custa ~1.600 unidades de uma cota padrão de 10.000/dia, o que comporta cerca de 6 envios por dia. `MAX_PUBLISH_PER_DAY` limita os **envios feitos no dia** (cortes longos e shorts somados) e protege essa cota. Quem posta muitos shorts precisa pedir aumento de cota ao YouTube. Projetos de API novos e não auditados pelo Google publicam como privado até passarem pela auditoria.

## Fila de postagem

Distribui as publicações ao longo do dia em horários fixos, usando o **agendamento nativo do YouTube** (`publishAt`). O corte é enviado assim que fica pronto, entra como privado, e o YouTube o torna público no horário. Não depende de o processo ficar ligado nem de guardar arquivos.

### Ligar

```
PUBLISH_SCHEDULE_ENABLED=true
MAX_PUBLISH_PER_DAY=3
PUBLISH_TIMEZONE=America/Sao_Paulo
PUBLISH_SLOTS=                    # vazio = distribuição automática
PUBLISH_WINDOW_START=09:00
PUBLISH_WINDOW_END=22:00
PUBLISH_MIN_LEAD_MINUTES=30
PUBLISH_QUEUE_DAYS=3
```

### Horários do dia (`day_times`)

- **Fixos:** `PUBLISH_SLOTS=12:00,18:00,21:00` usa esses horários (ordenados, sem repetição), limitados a `MAX_PUBLISH_PER_DAY`.
- **Automáticos:** com `PUBLISH_SLOTS` vazio, espalha `MAX_PUBLISH_PER_DAY` horários igualmente entre início e fim da janela. Com 3 por dia e janela 09:00–22:00: **09:00, 15:30, 22:00**. Com 1 por dia, usa o início da janela.

### Escolha do próximo horário (`next_slot`)

1. `earliest = agora + PUBLISH_MIN_LEAD_MINUTES`.
2. Percorre os dias a partir de hoje (no fuso `PUBLISH_TIMEZONE`), até `PUBLISH_QUEUE_DAYS` dias.
3. Devolve o primeiro horário `>= earliest` que **não esteja ocupado**. Os ocupados vêm da coluna `clips.scheduled_for`, comparados no minuto.
4. Se nenhum horário livre existir na janela de dias, devolve `None`: a fila está cheia.

Fila cheia faz o pipeline parar **sem marcar o vídeo**, e ele retoma quando um horário abrir.

### O que muda no envio

- O vídeo sobe com `privacyStatus=private` e `publishAt` em UTC (`...000Z`). **`YOUTUBE_PRIVACY_STATUS` é ignorado** enquanto a fila está ligada: no horário marcado o vídeo vira público.
- O horário só é gravado em `scheduled_for` se o envio devolveu um `video_id` (em `dry_run` o horário não ocupa a fila).
- O log registra `Agendado para <horário local> (<título>)`.

### Observações

- Fuso horário no Windows exige o pacote `tzdata`, já listado nas dependências.
- Os "melhores horários" por padrão são só uma distribuição uniforme. Depois de algumas semanas, use o YouTube Studio (Audiência → "Quando seus espectadores estão no YouTube") para escolher os horários e colocá-los em `PUBLISH_SLOTS`.
- A cota é consumida no dia do envio, não no dia da publicação.

## Webhook de notificação

Com `NOTIFY_WEBHOOK_URL`, cada corte publicado e cada erro de pipeline geram uma mensagem (`content` e `text` no JSON, compatível com Discord e Slack).

## Direitos autorais

Os cortes reaproveitam conteúdo de terceiros. A descrição sempre credita e linka o vídeo original, mas confira a política de cada canal-fonte.
