# Shorts (9:16)

Código: `vision/` (detecção e rastreamento de rostos, composição do quadro), `captions/` (legenda Remotion e tempo por palavra) e `editing/vertical_renderer.py`. A detecção e o rastreamento foram portados do podcast-clipper.

## Visão geral

```
candidato short [start, end] do vídeo completo
  → alinhador de palavras  (tempo de cada palavra, relativo ao corte)
  → analyze_framing        (rostos, planos de câmera, quem fala)
  → VerticalComposer       (cada quadro: bloco único ou split-screen)  → pipe raw BGR
  → UM ffmpeg: áudio do trecho + moldura + marca d'água + legenda Remotion (overlay) → libx264/aac
```

Shorts **não** passam pelo corte de silêncio (as legendas dependem do tempo original), nem recebem CTA ou outro.

## Enquadramento (`vision/`)

`analyze_framing(source, start, end, sample_fps)` amostra o trecho `SHORT_FRAMING_SAMPLE_FPS` vezes por segundo e produz um `FramingPlan`:

1. **Detecção** (`detection.py`): BlazeFace do MediaPipe, no quadro inteiro e em blocos quadrados sobrepostos (o modelo vê só 128 px, então rostos pequenos somem em 16:9). O modelo é baixado para `data/models/` na primeira vez.
2. **Planos de câmera:** cortes de câmera são detectados por histograma de cor, diferença de pixels e emendas verticais (layouts lado a lado).
3. **Trilhas:** os rostos de cada plano são ligados em uma trilha por pessoa; rostos pequenos de fundo são descartados.
4. **Quem fala:** o movimento da região da boca entre quadros dá uma nota de fala por pessoa. A câmera segue o falante com histerese (não troca a cada ruído).
5. **Suavização:** zona morta e interpolação evitam tremor; troca de falante é um corte seco, não um *pan*.
6. **Zoom:** fixo por plano e por pessoa (o quadro não "respira"), mais fechado quando a pessoa está longe.

`VerticalComposer` (`composer.py`) transforma cada quadro horizontal em `SHORT_WIDTH x SHORT_HEIGHT`:

- **Bloco único:** recorte 9:16 seguindo o falante, sempre dentro do painel da câmera dele (nunca mostra a emenda de um layout lado a lado).
- **Split-screen:** dois recortes empilhados (esquerda em cima, direita embaixo) com uma divisória de 4 px.

O split-screen só é considerado se houver dois rostos em pelo menos 20% do corte; aí `SHORT_SPLIT_CHANCE` decide por sorteio (padrão 50%, para variar). `SHORT_SPLIT_SCREEN=false` desliga.

## Legendas (`captions/`)

Duas etapas independentes:

**1. Tempo por palavra** (`words.py`, Strategy `WordAligner`):

| Implementação | Como | Quando |
|---|---|---|
| `WhisperWordAligner` | Re-transcreve só o áudio do corte com faster-whisper (`word_timestamps`) | `SHORT_CAPTIONS_WHISPER=true` e o extra `.[whisper]` instalado |
| `TranscriptWordAligner` | Distribui o tempo de cada segmento da transcrição entre as palavras, proporcional ao tamanho | Reserva automática; é impreciso com a legenda automática do YouTube |

`FallbackWordAligner` tenta o Whisper e cai para a estimativa se faltar o pacote, houver erro ou nenhuma palavra.

**2. Remotion** (`captions/remotion.py` + projeto `remotion/`): as palavras viram páginas de até 2 palavras (Poppins 800 em caixa alta, contorno preto); a palavra falada acende na cor de destaque (`SHORT_CAPTION_HIGHLIGHT`) com *pop*, e cada página entra com *spring*. O tamanho da fonte é ajustado para a página caber na tela. O Remotion renderiza um WebM transparente (VP8 + alfa) com a duração do short, e o ffmpeg o sobrepõe (decoder `libvpx` explícito: o vp8 nativo descarta o alfa). Durante o split-screen a legenda vai para o centro, sobre a divisória; fora dele fica a `SHORT_CAPTION_MARGIN_V` px da base. Exige Node/npm (a 1ª execução faz `npm install` em `remotion/`); se o Remotion falhar, o short falha (não há legenda alternativa).

## Moldura

`SHORT_FRAME_PATH` (PNG com transparência, **1080x1920**) é esticada sobre o vídeo vertical, **antes** das legendas, e a marca d'água (`WATERMARK_*`) vai por cima da moldura. Uma moldura 16:9 esticada num short fica distorcida: use a proporção do formato.

## Render

Os quadros compostos seguem por pipe (BGR cru) para um único ffmpeg, que lê o áudio do trecho direto do arquivo-fonte, aplica moldura, sobrepõe a legenda e codifica. O OpenCV lê o arquivo-fonte em sequência e reamostra para `RENDER_FPS` (repete ou pula quadros se o fps de origem for diferente). Se o ffmpeg falhar, o erro traz o final do stderr.

## Variáveis relacionadas

`SHORT_*`, `MAX_SHORTS_PER_VIDEO`, `SHORT_FRAME_PATH`, `WATERMARK_*`, `WHISPER_*`, `RENDER_*`.

## Limites conhecidos

- A nota de "quem fala" vem do movimento da boca; perfis, mãos no rosto e quem mastiga podem enganá-la (por isso ela só desempata entre participantes).
- Todos os parâmetros de rastreamento (`vision/tracking.py`) são os do podcast-clipper, calibrados lá.
- O split-screen vale para até dois interlocutores por vez; em mesas grandes escolhe o par que mais fala.
- Sem rostos detectados (ilustração, tela compartilhada), o recorte fica no centro do quadro.
