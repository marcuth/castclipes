# Metadados de publicação

Código: `metadata/generator.py` e `metadata/formatting.py`.

Cada corte recebe título, descrição, tags e um texto curto para a thumbnail. A IA escreve o texto bruto; o código formata e garante os limites.

## Pedido à IA

`LLMMetadataGenerator` envia: título e canal do episódio original, nome do **seu** canal (`CHANNEL_NAME`), assunto do corte, gancho, falantes e resumo prévio, e recebe um `MetadataSuggestion` com `title`, `summary`, `tags` e `thumbnail_text`. Há um prompt por formato.

### Título
- **long:** 45 a 80 caracteres, específico e curioso, ancorado no que é dito (pessoa, situação, número, polêmica).
- **short:** até 60 caracteres, direto, gerando curiosidade a partir do gancho.
- Os dois proíbem o genérico ("o segredo de...", "você não vai acreditar", "isso mudou tudo").

### Regra de fidelidade
É a regra mais importante dos prompts: **só se atribui fala a uma pessoa se ela estiver na lista de "Falantes"**. Se a lista está vazia, o título fala do **assunto**, sem dizer que alguém falou. Nomes que só aparecem no título do episódio original não podem ser usados, e a IA não pode inventar fatos nem acusações.

### Texto da thumbnail
O gancho do corte longo, de 2 a 4 palavras (máx. 28 caracteres), sem pontuação final. Para shorts fica vazio (o YouTube não aceita thumbnail própria neles).

## Formatação do título (`format_title`)

`TITLE_STYLE` escolhe:

```
natural (padrão)  o dia em que ele quebrou 3 vezes   →  O dia em que ele quebrou 3 vezes
upper             fulano reage a vídeo bizarro       →  FULANO REAGE a VÍDEO BIZARRO
```

- `natural` mantém a frase da IA e só garante a primeira letra maiúscula.
- `upper` põe tudo em caixa alta; as palavras de `SMALL_WORDS` (a, o, de, do, da, em, com, para, por, sobre, contra, que...) ficam em minúsculo, menos na primeira posição.
- Nos dois: aspas externas removidas, espaços colapsados e, acima de `TITLE_MAX_CHARS` (padrão 100), corte na última palavra inteira terminando com `…`.

## Tags

`merge_tags` junta as `FIXED_TAGS` (e `shorts`, nos shorts; primeiro) e as tags sugeridas pela IA (depois), em minúsculas, sem `#`, sem duplicatas, e para antes de estourar o limite de **500 caracteres** do YouTube (conta aspas implícitas de tags com espaço e a vírgula).

## Descrição (`DescriptionBuilder`)

Blocos separados por linha em branco, na ordem, omitindo os vazios:

1. `DESCRIPTION_HEADER`
2. `➡️ <resumo>` (resumo da IA, ou o da seleção)
3. `👉 <WATCH_MORE_LABEL> <WATCH_MORE_URL>` (só se houver URL)
4. `👀 Episódio completo (<canal>: <título>): <url>`: **crédito sempre presente**
5. `SOCIAL_LINKS` (uma por linha)
6. `DESCRIPTION_FOOTER`
7. Hashtags: `#shorts` (só nos shorts) e as de `FIXED_HASHTAGS`

Limitada a 5.000 caracteres, o máximo do YouTube.

## Se a IA falhar

O erro é registrado e o título vem do assunto do corte (ou do gancho). Isso evita inventar um falante.

## Variáveis relacionadas

`TITLE_MAX_CHARS`, `TITLE_STYLE`, `CHANNEL_NAME`, `FIXED_TAGS`, `FIXED_HASHTAGS`, `DESCRIPTION_HEADER`, `DESCRIPTION_FOOTER`, `WATCH_MORE_LABEL`, `WATCH_MORE_URL`, `SOCIAL_LINKS`.
