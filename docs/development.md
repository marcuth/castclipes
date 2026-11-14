# Desenvolvimento

## Comandos

```powershell
pip install -e .[dev]
.venv\Scripts\python -m pytest -q                       # todos os testes
.venv\Scripts\python -m pytest tests/test_pipeline.py::test_happy_path_publishes_once -q
.venv\Scripts\python -m ruff check src tests --fix      # lint
```

O CI roda `ruff check` + `pytest -q`. Não há formatador configurado (só `ruff check`, linha de 100 colunas, alvo Python 3.13). Os testes **não** precisam de rede, chave de IA nem de ffmpeg utilizável (os testes de render são pulados se o ffmpeg não funcionar).

## Testes

| Arquivo | Cobre |
|---|---|
| `test_pipeline.py` | Pipeline inteiro com dublês (`FakeDownloader`, `FakeSelector`, `FakePublisher`...). Novos testes de pipeline devem seguir o helper `build()` |
| `test_constraints.py` | Regras de duração, fronteira de frase, sobreposição |
| `test_silence.py` | Parse do `silencedetect` e plano de trechos |
| `test_ffmpeg_renderer.py` | Render real com ffmpeg (pulado se indisponível) |
| `test_overlay_config_rss.py` | Overlays, configuração e feed RSS |
| `test_source_fallback.py` | Reserva via yt-dlp e filtro de idade |
| `test_ai_client.py` | Sobe um servidor HTTP local que imita chat completions com SSE, exercitando o SDK de verdade |
| `test_ai_retry.py` | Retry com espera crescente |
| `test_llm_consumers.py` | Triagem, seleção e metadados com IA falsa |
| `test_metadata.py` | Título, tags e descrição |
| `test_thumbnails.py` | Nota de frames, composição e template |
| `test_schedule.py` | Fila de postagem: horários, antecedência, fila cheia |

## Convenções

- **Português** em comentários, mensagens de log, prompts e documentação; nomes de arquivos, classes e variáveis em inglês.
- Cada ponto de variação é um `Protocol` + implementações + uma factory simples; o pipeline só conhece o `Protocol`.
- Regras de negócio determinísticas ficam em código (`analysis/constraints.py`), não no prompt.
- Configuração nova entra em `config.py` **e** no `.env.example` (comentada), e é citada no README/docs.
- Imports pesados (`mediapipe`, `xpict`, `moviepy`, `faster-whisper`) são tardios.

## Como estender

### Novo provedor de publicação
1. Implemente `Publisher.publish(clip, publish_at=None) -> PublishResult` em `publishing/`.
2. Adicione o valor em `Settings.publish_mode` e o ramo em `create_publisher`.

### Novo jeito de listar vídeos
Implemente `VideoSource.latest() -> Iterable[SourceVideo]` e troque em `container.py`.

### Novo renderer
Implemente `Renderer.render(source, keep, out, insert_at=None) -> float` (devolve a duração final) e inclua em `editing/render_factory.py`.

### Novo observer
Uma função/objeto chamável que recebe o `Event`; registre com `bus.subscribe(TipoDeEvento, handler)` ou `bus.subscribe_all(handler)` no `container.py`.

### Nova regra de corte
Altere `analysis/constraints.py` (e o `.env`), e cubra em `tests/test_constraints.py`.

## Armadilhas conhecidas

- Os feeds RSS do YouTube deram 404 em desenvolvimento; a playlist `UULV` foi confirmada via yt-dlp. A reserva via yt-dlp cobre isso.
- O AI SDK para Python está em beta; fixe a versão ao atualizar.
- `asyncio.run` por chamada de IA quebra a segunda requisição (cliente HTTP preso ao loop); mantenha o loop persistente do `AiSdkClient`.
- Os limiares de `thumbnails/scoring.py` são chutes sem calibração com frames reais.
- O bundled ffmpeg 9 não aceita `-filter_complex_script`; o renderer tenta `-/filter_complex` primeiro.
- Publicar custa ~1.600 unidades da cota diária de 10.000.
- `PADROES_CANAL.md` e `IDEIA.md` estão no `.gitignore` de propósito.

## Contribuindo

Commits pequenos e descritivos (`feat:`, `fix:`, `docs:`). Rode `ruff check` e `pytest -q` antes de enviar.
