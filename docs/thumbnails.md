# Thumbnails

Código: `thumbnails/` (`base.py`, `frames.py`, `faces.py`, `scoring.py`, `layout.py`, `template.py`).

**Sem IA generativa.** A thumbnail é montada com um frame real do corte, detecção de rosto e um template de imagem. Desligada por padrão (`THUMBNAIL_PROVIDER=none`, o YouTube escolhe um frame); ligue com `THUMBNAIL_PROVIDER=template`.

## Etapas

```
1. amostra N frames do corte (THUMBNAIL_SAMPLE_COUNT, padrão 24)
2. detecta rostos em cada frame (MediaPipe / BlazeFace, do Google)
3. dá nota a cada frame: rosto bem enquadrado, pouca poluição, nitidez
4. pega o melhor frame em resolução original
5. decide recorte (zoom no rosto) e lado do texto
6. desenha o template com o texto (xpict.py) e salva JPEG ≤ 2 MB
```

## 1. Amostragem (`frames.py`)

`sample_times` distribui os instantes igualmente dentro do corte, longe das pontas (5% de margem de cada lado). Os frames são extraídos do **vídeo completo** (`source_file`, tempos absolutos) e reduzidos a 640 px de largura para a detecção, o que é rápido.

## 2. Detecção de rostos (`faces.py`)

`MediaPipeFaceDetector` usa o modelo BlazeFace de curto alcance (`blaze_face_short_range.tflite`), baixado na primeira vez para `data/models/`. Cada rosto vira um `FaceBox` em frações do frame, com confiança. Confiança mínima: `THUMBNAIL_FACE_MIN_CONFIDENCE` (0,6).

## 3. Nota do frame (`scoring.py`)

Funções puras sobre numpy e Pillow. Primeiro `usable_faces` mantém só os rostos principais (até 2): altura mínima de 12% do frame e pelo menos metade do maior rosto, para ignorar público ao fundo.

A nota total é `(0,45·enquadramento + 0,35·limpeza + 0,20·nitidez) × exposição`; **zero se não há rosto utilizável**.

| Componente | O que mede |
|---|---|
| Enquadramento | Tamanho do rosto (ideal ~26% da altura, penaliza acima de 60%), rosto inteiro dentro do frame, olhos na metade de cima, confiança da detecção |
| Limpeza | Densidade de bordas (gradiente) **fora** dos rostos; fundo liso = 1, muita poluição = 0 |
| Nitidez | Variância do laplaciano na região do rosto principal |
| Exposição | 1,0 se a luminância média está entre 45 e 215; senão 0,4 |

Os frames abaixo de nota 0,2 são rejeitados: nesse caso o corte sai **sem thumbnail**.

> Os limiares de `scoring.py` são pontos de partida e **ainda não foram calibrados** com frames reais das lives. Ajuste depois de ver resultados.

## 4 e 5. Composição (`layout.py`)

`compose()` calcula:

- **Recorte 16:9** com zoom no rosto, até `THUMBNAIL_MAX_ZOOM` (1,6). Um rosto ocupa ~52% da altura; dois, ~42%.
- **Posição:** um rosto fica num terço lateral (30% ou 70%) para o texto ocupar o lado oposto; dois rostos ficam ao centro.
- **Lado do texto:** `left` ou `right` se sobrar pelo menos 36% da largura livre ao lado do rosto; senão `bottom`.

`fit_text` encontra o maior tamanho de fonte em que o texto, quebrado em linhas, cabe na área.

## 6. Template (`template.py`)

Template [xpict.py](https://pypi.org/project/xpict.py/) de 1280×720 com camadas:

1. frame recortado e redimensionado;
2. gradiente escuro do lado do texto, para contraste sem esconder o rosto;
3. linhas de texto em **Anton** (fonte OFL embutida), branco com contorno preto; **a última linha usa a cor de destaque** (`THUMBNAIL_ACCENT_COLOR`, padrão `#FFD400`);
4. logo opcional (`THUMBNAIL_LOGO_PATH`) no canto oposto ao do texto.

O JPEG tenta qualidades 92, 85, 78 e 70 até ficar abaixo de 2 MB (limite do YouTube).

## Texto da thumbnail

`thumbnail_text`: usa o campo `thumbnail_text` sugerido pela IA; se vazio, usa as últimas 4 palavras do título (onde fica o gatilho), tirando preposições do começo. Sempre em caixa alta.

## Falhas

Qualquer erro na thumbnail é registrado e a publicação segue sem ela. Para o YouTube aceitar thumbnail personalizada, o canal precisa estar **verificado**.

## Variáveis

`THUMBNAIL_PROVIDER`, `THUMBNAIL_SAMPLE_COUNT`, `THUMBNAIL_FACE_MIN_CONFIDENCE`, `THUMBNAIL_MAX_ZOOM`, `THUMBNAIL_ACCENT_COLOR`, `THUMBNAIL_FONT_PATH` (vazio = Anton), `THUMBNAIL_LOGO_PATH`.
