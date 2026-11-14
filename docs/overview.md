# Visão geral

## O que o projeto faz

1. Lê periodicamente as **playlists de lives** dos canais configurados.
2. Para cada live **já encerrada**, obtém a transcrição (legenda do YouTube ou Whisper local).
3. Verifica se o conteúdo fala dos alvos (Renan Santos, Arthur do Val, MBL, Missão...).
4. Pede a uma IA que sugira **trechos longos de um assunto só** e aplica regras fixas de duração e fronteira de frase.
5. Baixa o vídeo completo uma vez, corta localmente, remove silêncios longos, aplica moldura, insere um vídeo de CTA no meio e anexa um outro, tudo com ffmpeg.
6. Gera título, descrição, tags e (opcionalmente) thumbnail.
7. Envia ao YouTube, de forma imediata ou **agendada** numa fila de horários.

## Regras de produto (fixas no código)

- **Só lives.** Uploads comuns nunca entram. A decisão é por `live_status == "was_live"` (veja [sources.md](sources.md)). Só o comando `process` (manual) ignora essa regra.
- **Só lives encerradas.** Live agendada, no ar ou em `post_live` é reavaliada na rodada seguinte, sem ser marcada no estado.
- **Um assunto por corte**, de 10 a 40 min por padrão, seguindo o padrão do canal analisado (mediana de 22 min).
- **A IA propõe, o código decide.** Duração, fronteira de frase, nota mínima, sobreposição e limite por vídeo são aplicados em `analysis/constraints.py`, não no prompt.
- **Crédito sempre.** A descrição de todo corte cita e linka o vídeo original.
- **Começa seguro.** `PUBLISH_MODE=dry_run` e `YOUTUBE_PRIVACY_STATUS=private` são os padrões do `.env.example`.

## Padrão de conteúdo imitado

O canal-alvo ("Inevitável Cortes") publica cortes longos com título em caixa alta no formato `[PESSOA] [VERBO] [ALVO/ASSUNTO] [GATILHO EMOCIONAL]!`. O resumo detalhado desse padrão fica no `PADROES_CANAL.md` (ignorado pelo git de propósito). Os padrões de corte que a IA reconhece são `reaction`, `response`, `revelation`, `debate` e `other`.

Quando o canal-fonte é jornalístico (um apresentador noticiando), o título **não** atribui a fala à pessoa citada: ela vira assunto/alvo. Veja [metadata.md](metadata.md).

## Glossário

| Termo | Significado |
|---|---|
| Live / `was_live` | Transmissão ao vivo já encerrada e disponível como vídeo |
| Playlist `UULV…` | Playlist automática do YouTube só com as lives de um canal (`UC…` vira `UULV…`) |
| Candidato (`ClipCandidate`) | Trecho sugerido pela IA, já ajustado pelas regras |
| Corte (`RenderedClip`) | Arquivo `.mp4` final renderizado a partir de um candidato |
| Moldura | PNG com transparência esticado sobre o vídeo inteiro |
| CTA | Vídeo curto (chamada para ação/anúncio) inserido no meio do corte |
| Outro | Vídeo de encerramento anexado ao fim |
| Slot | Horário do dia reservado na fila de postagem |
| `dry_run` | Modo em que tudo é feito, menos o envio ao YouTube |
