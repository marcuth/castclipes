# Seleção de cortes

Código: `analysis/selector.py` (IA), `analysis/heuristics.py` (alternativa sem IA) e `analysis/constraints.py` (regras fixas).

Princípio: **a IA propõe, o código decide.** O prompt orienta o gosto editorial; as regras do `.env` são aplicadas depois, em código, e nunca dependem de a IA obedecer.

## Um seletor por formato

`container.py` cria dois `LLMClipSelector`, um por `ClipFormat`, cada um com **prompt**, **regras** (`ClipConstraints`) e duração ideal próprios. O pipeline usa só os formatos de `CLIP_FORMATS`.

| | long | short |
|---|---|---|
| Objetivo | Um assunto do começo ao fim, que se entende sem ver o resto da live | O momento mais forte: gancho imediato, fechamento limpo, funciona sozinho |
| Duração | `LONG_MIN_SECONDS` a `LONG_MAX_SECONDS` (600 a 2400) | `SHORT_MIN_SECONDS` a `SHORT_MAX_SECONDS` (20 a 85) |
| Ideal (dica à IA) | `LONG_TARGET_SECONDS` | `SHORT_TARGET_SECONDS` |
| Nota mínima | `LONG_MIN_SCORE` (0,6) | `SHORT_MIN_SCORE` (0,7) |
| Máximo por vídeo | `MAX_LONG_PER_VIDEO` (3) | `MAX_SHORTS_PER_VIDEO` (8) |
| Folga nas pontas | `CLIP_EDGE_PADDING_SECONDS` (0,5 s) | `SHORT_EDGE_PADDING_SECONDS` (0,2 s) |

Cortes de formatos diferentes **podem se sobrepor**: um short pode sair de dentro de um corte longo. A regra de não sobreposição vale dentro de cada formato.

## 1. Janelas

Lives passam de 3 horas e não cabem no contexto da IA de uma vez. `windows()` divide a transcrição em janelas de `SELECTION_WINDOW_SECONDS` (padrão 3600) com `SELECTION_WINDOW_OVERLAP_SECONDS` (padrão 300) de sobreposição. Transcrições menores que uma janela vão inteiras.

Para cada janela, a IA recebe:
- título e canal do vídeo;
- os limites da janela;
- as regras (duração mínima/máxima, ideal, máximo de cortes, nota mínima);
- a transcrição com marcadores `[Ns]` a cada 15 segundos.

Se a chamada de uma janela falhar, o erro é registrado e as demais continuam.

## 2. O que a IA devolve

Uma lista de `ClipSuggestion`:

| Campo | Significado |
|---|---|
| `start`, `end` | Tempos em segundos |
| `topic` | Assunto do corte (no short, a ideia central, concreta) |
| `hook` | Frase de abertura do corte; alimenta o título dos shorts |
| `speakers` | Quem comprovadamente fala no trecho |
| `score` | Nota de 0 a 1 |
| `summary` | Resumo curto |

### Quem é quem

A transcrição não identifica falantes. Por isso os dois prompts exigem que:
- `speakers` contenha só quem **comprovadamente** fala (lista vazia na dúvida);
- nomes do **título do vídeo** nunca virem falantes (o título cita convidados e pautas que podem nem aparecer no trecho).

Essa regra existe porque um título já saiu errado ao atribuir a fala a alguém que só aparecia no título da live.

## 3. Regras determinísticas (`enforce`)

Para cada sugestão, `fit_candidate` aplica, em ordem:

1. Limita `start`/`end` à duração da transcrição; descarta se `end <= start`.
2. **Fronteira de frase:** o início vai para o começo do segmento que contém `start`; o fim, para o fim do segmento que contém `end`.
3. **Duração máxima:** se passar do máximo do formato (descontando a folga), o fim recua para o maior fim de segmento que caiba.
4. **Duração mínima:** se for curto demais, o fim avança até o primeiro fim de segmento que atinja o mínimo; se isso estourar o máximo ou a transcrição acabar, tenta puxar o início para trás; se ainda não couber, o candidato é descartado.
5. **Folga:** soma a folga do formato em cada ponta.
6. **Nota mínima:** descarta se `score` ficar abaixo da nota mínima do formato.

Depois, `enforce` junto de todas as janelas:

1. Ordena por nota, da maior para a menor.
2. Aceita candidatos **sem sobreposição** com os já aceitos, até o máximo por vídeo do formato.
3. Devolve os aceitos ordenados por tempo.

Os candidatos que sobraram viram o evento `ClipsSelected`. Lista vazia → vídeo `skipped` com `IA não encontrou cortes bons`.

## Faixa da nota

`score` vai de 0,0 a 1,0 (valores fora disso são cortados). O corte só passa com nota maior ou igual à mínima do formato. A nota é a avaliação da IA sobre o quanto o trecho funciona como corte; não é uma medida objetiva.

## Variáveis relacionadas

`CLIP_FORMATS`, `LONG_*`, `MAX_LONG_PER_VIDEO`, `SHORT_MIN_SECONDS`, `SHORT_MAX_SECONDS`, `SHORT_TARGET_SECONDS`, `SHORT_MIN_SCORE`, `MAX_SHORTS_PER_VIDEO`, `SHORT_EDGE_PADDING_SECONDS`, `CLIP_EDGE_PADDING_SECONDS`, `SELECTION_WINDOW_SECONDS`, `SELECTION_WINDOW_OVERLAP_SECONDS`.

## Alternativa sem IA: `SELECTOR_ENGINE=heuristics`

`HeuristicClipSelector` (`analysis/heuristics.py`) troca só a escolha dos cortes; triagem e metadados continuam na IA. Portado do `podcast-clipper`:

1. **Unidades:** os segmentos viram frases (fecha em pontuação final, pausa ≥ 1 s ou 14 s). A legenda automática do YouTube vem em pedaços curtos e sem pontuação, então as regras de "frase" funcionam melhor com Whisper.
2. **Nota por unidade (0 a 1):** soma de gatilhos de atenção (+1,0), contraste (+0,7), primeira pessoa (+0,5), pergunta (+0,4), tamanho de frase (+0,3), exclamação (+0,3), risada (+0,3), número (+0,2), pausa antes (+0,2) e heatmap do YouTube (+1,5 × intensidade); satura em 3,0. CTA/patrocínio e os primeiros `HEURISTIC_SKIP_INTRO_SECONDS` e os últimos `HEURISTIC_SKIP_OUTRO_SECONDS` zeram a nota e **bloqueiam** a unidade. O fim usa a duração do vídeo ou, se indisponível, o fim da transcrição; `0` desliga esse bloqueio.
3. **Janelas:** uma janela deslizante procura trechos dentro de `*_MIN/MAX_SECONDS`, com leve preferência pela duração ideal. Short: nenhuma unidade bloqueada e o gancho (primeiras frases) pesa 40%. Long: tolera até 5% de tempo bloqueado e usa a densidade média de nota.
4. **Nota final:** normalizada pelo percentil 95 das janelas do próprio vídeo (com piso), para que `*_MIN_SCORE` continue fazendo sentido. Depois `enforce` aplica as regras de sempre.
5. **Texto:** `hook` é a primeira frase; `topic` do short é essa frase, e o do long é "Conversa sobre palavra, palavra e palavra" (palavras-chave das frases de maior nota). Sem `speakers` nem `summary`.

Limites: regex não entende assunto, então nos cortes **longos** a coerência vem só da densidade de nota (qualidade menor que a da IA). O heatmap ("mais reproduzido") quase nunca existe logo após a live acabar; é só um bônus quando vem no `yt-dlp`. As regras são em português do Brasil.
