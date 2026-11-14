# Metadados de publicação

Código: `metadata/generator.py` e `metadata/formatting.py`.

Cada corte recebe título, descrição, tags e um texto curto para a thumbnail. A IA escreve o texto bruto; o código formata e garante os limites.

## Pedido à IA

`LLMMetadataGenerator` envia: título e canal do vídeo original, assunto do corte, padrão, falantes, alvo e resumo prévio, e recebe um `MetadataSuggestion` com `title`, `summary`, `tags` e `thumbnail_text`.

### Fórmula do título
`[PESSOA] [VERBO] [ALVO/ASSUNTO] [GATILHO EMOCIONAL]!`, em português do Brasil, de 45 a 80 caracteres. Verbos típicos: REAGE a, RESPONDE, FALA A VERDADE sobre, REVELA BASTIDORES de, DEBATE. Gatilhos aceitos (só se o conteúdo justificar, sem inventar fatos nem acusações): BIZARRO, SURTO, HUMILHADO, DESMASCARA, SEM PALAVRAS, SINCERO ATÉ DEMAIS, PASSANDO VERGONHA.

### Regra de fidelidade
É a regra mais importante do prompt: **só se atribui fala ou reação a uma pessoa se ela estiver na lista de "Falantes"**. Se a lista está vazia, ou se o canal de origem é jornalístico/de comentário, o título fala do **assunto e do alvo** (ex.: `MBL vira ALVO de ...!`), sem dizer que alguém falou. Nomes que só aparecem no título do vídeo original não podem ser usados.

### Texto da thumbnail
O gancho do corte, de 2 a 4 palavras (máx. 28 caracteres), **sem** o nome do falante (o rosto já aparece) e sem pontuação final.

## Formatação do título (`format_title`)

Padrão do canal-alvo: caixa alta com preposições e artigos em minúsculo.

```
arthur do val reage a vídeo bizarro  →  ARTHUR do VAL REAGE a VÍDEO BIZARRO
```

- A primeira palavra é sempre em caixa alta; as palavras de `SMALL_WORDS` (a, o, de, do, da, em, com, para, por, sobre, contra, que...) ficam em minúsculo nas demais posições.
- Aspas externas são removidas e espaços colapsados.
- Acima de `TITLE_MAX_CHARS` (padrão 100), corta na última palavra inteira e termina com `…`.

## Tags

`merge_tags` junta as `FIXED_TAGS` (primeiro) e as tags sugeridas pela IA (depois), em minúsculas, sem `#`, sem duplicatas, e para antes de estourar o limite de **500 caracteres** do YouTube (conta aspas implícitas de tags com espaço e a vírgula).

## Descrição (`DescriptionBuilder`)

Blocos separados por linha em branco, na ordem, omitindo os vazios:

1. `DESCRIPTION_HEADER`
2. `➡️ <resumo>` (resumo da IA, ou o da seleção)
3. `👉 <WATCH_MORE_LABEL> <WATCH_MORE_URL>` (só se houver URL)
4. `👀 Vídeo original (<canal>: <título>): <url>`: **crédito sempre presente**
5. `SOCIAL_LINKS` (uma por linha)
6. `DESCRIPTION_FOOTER`
7. Hashtags de `FIXED_HASHTAGS`

Limitada a 5.000 caracteres, o máximo do YouTube.

## Se a IA falhar

O erro é registrado e o título vem de um modelo fixo: `<falante> <verbo do padrão> <alvo ou assunto>!`. Sem falante, vira só `<alvo ou assunto>!`. Isso evita inventar um falante.

## Variáveis relacionadas

`TITLE_MAX_CHARS`, `FIXED_TAGS`, `FIXED_HASHTAGS`, `DESCRIPTION_HEADER`, `DESCRIPTION_FOOTER`, `WATCH_MORE_LABEL`, `WATCH_MORE_URL`, `SOCIAL_LINKS`.
