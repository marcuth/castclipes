# Operação

## Instalação

Python **3.13** é obrigatório (o código usa sintaxe de type parameters, como `def generate[T](...)`).

```powershell
python -m venv .venv; .venv\Scripts\activate
pip install -e .[dev]            # Whisper local é opcional: pip install -e .[whisper]
copy .env.example .env           # preencha AI_API_KEY e SOURCE_LIVE_PLAYLIST_IDS
```

Requisitos externos:
- **ffmpeg:** o projeto usa o binário embutido do `imageio-ffmpeg` e cai para o `ffmpeg` do PATH.
- **Runtime JavaScript** (deno ou node) para o yt-dlp.

## Comandos

```powershell
python -m castclipes resolve-channel @canal       # imprime o ID da playlist de lives
python -m castclipes run                        # uma verificação dos feeds
python -m castclipes watch                      # loop contínuo (POLL_INTERVAL_SECONDS)
python -m castclipes process <url-ou-id>        # um vídeo específico (ignora regras de live)
python -m castclipes process <url-ou-id> --format short   # só shorts (long | short | both)
python -m castclipes auth-youtube               # login OAuth (PUBLISH_MODE=youtube)
```

O script instalado também responde como `castclipes`.

- `run` serve para testar e para agendadores externos (cron, Agendador de Tarefas).
- `watch` é o modo "funcionário virtual": repete `run` sem parar; `Ctrl+C` encerra e fecha o banco.
- `process` aceita URL (`watch?v=`, `youtu.be/`, `/live/`, `/shorts/`) ou o ID de 11 caracteres.

**Depois de mudar código ou `.env`, reinicie o processo** para ele carregar as alterações.

## Primeira execução recomendada

1. `PUBLISH_MODE=dry_run`, `THUMBNAIL_PROVIDER=none`.
2. `python -m castclipes process <url de uma live recente>`.
3. Confira em `data/clips/` os `.mp4`: no longo, moldura, CTA e qualidade do corte; no short, enquadramento do rosto, split-screen, legendas e moldura vertical. Veja também o log do título/descrição.
4. Ligue a thumbnail e confira o `.jpg`.
5. Rode `auth-youtube`, mude para `PUBLISH_MODE=youtube` com `YOUTUBE_PRIVACY_STATUS=private` e publique um corte de teste.
6. Só então use `public` ou a fila de postagem.

## Lendo o log

Mensagens principais (logger `castclipes`):

| Mensagem | Significado |
|---|---|
| `Novo vídeo: ...` | Vídeo entrou no processamento |
| `Aguardando <id>: ...` | Live não pronta ou esperando legenda |
| `Ignorado <id>: <motivo>` | Descartado (`antigo demais`, `muito curto`, `não é uma live`, etc.) |
| `Transcrição <fonte> de <id>: N segmentos` | Transcrição obtida |
| `Corte <formato> <id> [ini-fim s, N min, nota X]: tema` | Candidato aprovado |
| `Renderizado (<formato>): <arquivo> (N min)` | Corte pronto |
| `Agendado para <horário> (<título>)` | Fila de postagem |
| `Publicado: <url>` | Enviado |
| `Erro em <id>: ...` | Falha; o vídeo será tentado de novo |

## Solução de problemas

### `Feed RSS da playlist ... indisponível (404)`
Os feeds RSS do YouTube falham de vez em quando. O projeto cai sozinho para o yt-dlp (`Playlist ... lida via yt-dlp`). Nada a fazer.

### Muitos `Ignorado ...: antigo demais`
Esperado quando a reserva via yt-dlp traz lives antigas: o filtro de idade (`SOURCE_MAX_AGE_HOURS`) as descarta depois do `enrich`.

### Resposta vazia da IA / `Empty response`
Comum em modelos gratuitos. Ative `AI_MAX_RETRIES=3` (veja [ai.md](ai.md)).

### `ConnectionAbortedError [Errno 10053]` no upload
A conexão foi encerrada por algo no seu computador ou rede (antivírus/firewall, VPN, proxy, Wi-Fi). O corte já foi renderizado, mas o vídeo é marcado `failed` e refeito na rodada seguinte. Verifique antivírus e VPN.

### Título atribuindo fala à pessoa errada
O prompt exige fidelidade ([metadata.md](metadata.md)), mas modelos fracos podem errar. Troque `AI_MODEL` por um mais forte ou revise antes de publicar (`private` ou fila).

### `faster-whisper não instalado`
`pip install -e .[whisper]`.

### yt-dlp avisa de runtime JavaScript
Instale deno ou node. Sem ele, alguns formatos podem faltar.

### Disco cheio
`data/work/` guarda o vídeo completo durante o processamento; reduza `MAX_SOURCE_HEIGHT`. `data/clips/` acumula cortes e thumbnails, apague os antigos.

### Thumbnail não saiu
Verifique o log: `Nenhum frame com rosto bem enquadrado` (nota abaixo de 0,2) ou erro do MediaPipe. A publicação segue sem thumbnail. O canal precisa estar verificado para thumbnails personalizadas.

## Segurança

- `.env` e `secrets/*.json` ficam fora do git. Não os compartilhe.
- Se uma chave de API aparecer em log, chat ou commit, revogue e gere outra.
