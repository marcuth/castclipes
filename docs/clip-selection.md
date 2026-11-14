# Seleção de cortes

Código: `analysis/selector.py` (IA) e `analysis/constraints.py` (regras fixas).

Princípio: **a IA propõe, o código decide.** O prompt orienta o gosto editorial; as regras do `.env` são aplicadas depois, em código, e nunca dependem de a IA obedecer.

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
| `topic` | Assunto do corte |
| `pattern` | `reaction`, `response`, `revelation`, `debate` ou `other` |
| `speakers` | Quem comprovadamente fala no trecho |
| `target` | Terceiro visado (ex.: uma figura nacional) |
| `score` | Nota de 0 a 1 |
| `summary` | Resumo curto |

### Orientação editorial do prompt

- Cortes longos (10 a 40 min) com **um** assunto do começo ao fim.
- Os melhores têm **conflito** com figura nacional, emoção forte, começo e fim naturais, e envolvem Renan Santos, Arthur do Val, Kim Kataguiri, MBL ou Missão como protagonistas ou alvo.
- Evitar recados genéricos, avisos de live, trechos sem tema claro e propaganda.

### Quem é quem

A transcrição não identifica falantes, e o canal-fonte pode ser jornalístico (apresentador noticiando, sem a pessoa citada presente). Por isso o prompt exige que:
- `speakers` contenha só quem **comprovadamente** fala (lista vazia na dúvida);
- nomes do **título do vídeo** nunca virem falantes (o título cita pautas e adversários que podem nem aparecer no trecho);
- `reaction`, `response` e `debate` só sejam usados se o texto mostrar isso; senão, `other`.

Essa regra existe porque um título já saiu errado ao atribuir a fala a alguém que só aparecia no título da live.

## 3. Regras determinísticas (`enforce`)

Para cada sugestão, `fit_candidate` aplica, em ordem:

1. Limita `start`/`end` à duração da transcrição; descarta se `end <= start`.
2. **Fronteira de frase:** o início vai para o começo do segmento que contém `start`; o fim, para o fim do segmento que contém `end`.
3. **Duração máxima:** se passar de `CLIP_MAX_SECONDS` (descontando a folga), o fim recua para o maior fim de segmento que caiba.
4. **Duração mínima:** se for curto demais, o fim avança até o primeiro fim de segmento que atinja o mínimo; se isso estourar o máximo ou a transcrição acabar, tenta puxar o início para trás; se ainda não couber, o candidato é descartado.
5. **Folga:** soma `CLIP_EDGE_PADDING_SECONDS` (0,5 s) em cada ponta.
6. **Nota mínima:** descarta se `score < CLIP_MIN_SCORE`.

Depois, `enforce` junto de todas as janelas:

1. Ordena por nota, da maior para a menor.
2. Aceita candidatos **sem sobreposição** com os já aceitos, até `MAX_CLIPS_PER_VIDEO`.
3. Devolve os aceitos ordenados por tempo.

Os candidatos que sobraram viram o evento `ClipsSelected`. Lista vazia → vídeo `skipped` com `IA não encontrou cortes bons`.

## Faixa da nota

`score` vai de 0,0 a 1,0 (valores fora disso são cortados). O corte só passa com nota `>= CLIP_MIN_SCORE` (padrão 0,6). A nota é a avaliação da IA sobre o quanto o trecho combina com o padrão do canal; não é uma medida objetiva.

## Variáveis relacionadas

`CLIP_MIN_SECONDS`, `CLIP_MAX_SECONDS`, `CLIP_TARGET_SECONDS`, `CLIP_MIN_SCORE`, `MAX_CLIPS_PER_VIDEO`, `CLIP_EDGE_PADDING_SECONDS`, `SELECTION_WINDOW_SECONDS`, `SELECTION_WINDOW_OVERLAP_SECONDS`.
