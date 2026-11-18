# Visão geral

## O que o projeto faz

1. Lê periodicamente as **playlists de lives** dos canais de podcast configurados.
2. Para cada live **já encerrada**, obtém a transcrição (legenda do YouTube ou Whisper local).
3. Pede a uma IA que sugira, para cada formato configurado, os melhores trechos, e aplica regras fixas de duração e fronteira de frase:
   - **long (16:9):** um assunto do começo ao fim, 10 a 40 min por padrão.
   - **short (9:16):** um gancho forte, 20 a 85 s por padrão.
4. Baixa o vídeo completo uma vez e corta localmente:
   - **long:** remove silêncios longos, aplica a moldura, insere um vídeo de CTA no meio e anexa um outro (tudo com ffmpeg).
   - **short:** enquadra o rosto de quem fala em 9:16 (ou divide a tela em dois), aplica a moldura vertical e queima legendas palavra a palavra ([shorts.md](shorts.md)).
5. Gera título, descrição, tags e (só para o long, opcionalmente) thumbnail.
6. Envia ao YouTube, de forma imediata ou **agendada** numa fila de horários.

## Regras de produto (fixas no código)

- **Só lives.** Uploads comuns nunca entram. A decisão é por `live_status == "was_live"` (veja [sources.md](sources.md)). Só o comando `process` (manual) ignora essa regra.
- **Só lives encerradas.** Live agendada, no ar ou em `post_live` é reavaliada na rodada seguinte, sem ser marcada no estado.
- **A IA propõe, o código decide.** Duração, fronteira de frase, nota mínima, sobreposição e limite por vídeo são aplicados em `analysis/constraints.py`, não no prompt. Cada formato tem as suas regras.
- **Formatos independentes.** Long e short usam seletores, prompts, regras e renderers próprios. Cortes de formatos diferentes podem se sobrepor (um short pode sair de dentro de um corte longo); dentro de um formato, nunca.
- **Crédito sempre.** A descrição de todo corte cita e linka o episódio original.
- **Começa seguro.** `PUBLISH_MODE=dry_run` e `YOUTUBE_PRIVACY_STATUS=private` são os padrões do `.env.example`.

## Glossário

| Termo | Significado |
|---|---|
| Live / `was_live` | Transmissão ao vivo já encerrada e disponível como vídeo |
| Playlist `UULV…` | Playlist automática do YouTube só com as lives de um canal (`UC…` vira `UULV…`) |
| Formato (`ClipFormat`) | `long` (16:9, um assunto) ou `short` (9:16, um gancho) |
| Candidato (`ClipCandidate`) | Trecho sugerido pela IA, já ajustado pelas regras, com seu formato |
| Corte (`RenderedClip`) | Arquivo `.mp4` final renderizado a partir de um candidato |
| Moldura | PNG com transparência esticado sobre o vídeo inteiro (uma por formato) |
| CTA | Vídeo curto (chamada para ação/anúncio) inserido no meio do corte longo |
| Outro | Vídeo de encerramento anexado ao fim do corte longo |
| Split-screen | Layout do short com dois blocos empilhados, um por interlocutor |
| Slot | Horário do dia reservado na fila de postagem |
| `dry_run` | Modo em que tudo é feito, menos o envio ao YouTube |
