# Transcrição e relevância

Código: `transcription/`, `analysis/triage.py`, parte de `pipeline.py`.

## Ordem de tentativas

```
1. Legenda do YouTube (youtube-transcript-api)        grátis e rápida
      │ não existe?
2. Live encerrada há pouco?  espera LIVE_CAPTION_WAIT_MINUTES   (marca `waiting`)
      │ passou o prazo?
3. Triagem por IA (só título, canal, duração, descrição)         barata
      │ aprovada?
4. Whisper local (faster-whisper) sobre o áudio baixado           caro
```

## Legenda do YouTube

`YouTubeTranscriptProvider` busca nos idiomas de `TRANSCRIPT_LANGUAGES` (padrão `pt,pt-BR`). Qualquer falha (legenda desativada, bloqueio de IP) é registrada em nível `INFO` e resulta em `None`, sem derrubar o fluxo.

## Espera pela legenda automática

O YouTube costuma publicar a legenda automática pouco depois do fim da live. Por isso, uma live encerrada sem legenda vira `waiting` e só segue para triagem/Whisper depois de `LIVE_CAPTION_WAIT_MINUTES` (padrão 90). O relógio começa na primeira vez em que o vídeo é visto sem legenda e não é reiniciado nas rodadas seguintes. Isso não vale no comando `process` manual.

## Triagem por IA

Só para vídeos **sem legenda**: transcrever com Whisper custa tempo e GPU/CPU, então a IA avalia antes, a partir do título, canal, duração e descrição (1.500 primeiros caracteres), dando nota de 0 a 1. O vídeo só segue se a nota for `>= TRIAGE_MIN_SCORE` (padrão 0,7). Se a chamada de IA falhar, a triagem reprova (`erro na triagem`), por segurança.

## Whisper local

`WhisperTranscriptProvider` baixa o áudio (`.m4a`) pelo yt-dlp, transcreve com `faster-whisper` (com `vad_filter`) e apaga o áudio. É um extra opcional:

```powershell
pip install -e .[whisper]
```

Variáveis: `WHISPER_MODEL` (padrão `small`), `WHISPER_DEVICE` (`auto`), `WHISPER_COMPUTE_TYPE` (`int8`). Sem o pacote instalado, o erro orienta a instalação.

Se nenhuma fonte entregar transcrição, o vídeo é marcado `skipped` com `não foi possível transcrever`.

## Sem identificação de falantes

A legenda do YouTube e o Whisper entregam texto com tempos, **sem dizer quem fala**. Esse limite pesa na seleção e nos títulos; veja [clip-selection.md](clip-selection.md) e [metadata.md](metadata.md).
