# Fontes: como as lives são descobertas

Código: `sources/rss.py`, `sources/base.py`, `downloader.py::enrich`.

## Playlist de lives (`UULV…`)

Cada canal do YouTube tem uma playlist automática só com as lives, cujo ID é o ID do canal (`UC…`) com o prefixo trocado por `UULV`. O projeto monitora essas playlists, definidas em `SOURCE_LIVE_PLAYLIST_IDS` (vários IDs separados por vírgula).

- `live_playlist_id()` aceita os dois formatos: um ID `UC…` é convertido sozinho.
- Para descobrir o ID: `python -m castclipes resolve-channel @canal`.

## Leitura da lista

`RssVideoSource.latest()` percorre cada playlist e devolve os vídeos publicados dentro de `SOURCE_MAX_AGE_HOURS`.

1. **RSS (primeira tentativa):** `GET https://www.youtube.com/feeds/videos.xml?playlist_id=<ID>`, lido com `feedparser`. Traz id, título, descrição, canal e data.
2. **Reserva via yt-dlp:** se o RSS falhar por qualquer motivo (404 é comum), `ytdlp_playlist()` lista as `SOURCE_FALLBACK_LIMIT` lives mais recentes da playlist, sem baixar nada. Essa listagem "rasa" não traz data nem descrição; o `enrich` completa e o pipeline descarta o que passou da idade máxima.
3. Se as duas falharem, o erro é registrado e a rodada segue para a próxima playlist.

`SOURCE_FALLBACK_LIMIT=0` desliga a reserva.

### Por que o RSS falha

Os feeds `videos.xml` do YouTube são um recurso legado e sem garantia: já foram observados 404 em todos os tipos de feed (por canal, `UULV`, `UULP`, `UU`) enquanto a página normal da playlist respondia 200 e o yt-dlp funcionava. Não é problema de User-Agent nem do código. A reserva via yt-dlp existe por isso; quando o RSS volta, ele continua sendo a primeira tentativa.

## Enriquecimento

`VideoDownloader.enrich()` usa o yt-dlp (`skip_download`) para completar:

- duração, descrição, nome do canal;
- `live_status` (`is_upcoming`, `is_live`, `post_live`, `was_live`, `not_live`);
- `published_at`, a partir de `release_timestamp` ou `timestamp`, quando a fonte não trouxe.

## O que entra e o que não entra

Veja a tabela de filtros em [pipeline.md](pipeline.md). Em resumo: só `was_live`, dentro da idade máxima e da faixa de duração (`SOURCE_MIN_DURATION_SECONDS` a `SOURCE_MAX_DURATION_SECONDS`).

## Requisito: runtime JavaScript

O yt-dlp precisa de um runtime JavaScript (deno ou node) para extrair o YouTube sem formatos faltando. Sem ele aparece um aviso e alguns formatos podem sumir. Veja a página do EJS na wiki do yt-dlp.
