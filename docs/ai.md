# Inteligência artificial

Código: `ai/base.py`, `ai/factory.py`, `ai/sdk_client.py`.

A IA é usada em três lugares, sempre por **saída estruturada** (o modelo devolve JSON validado por Pydantic):

| Uso | Schema | Onde |
|---|---|---|
| Triagem de vídeo sem legenda | `TriageVerdict` | `analysis/triage.py` |
| Sugestão de cortes | `ClipSuggestions` | `analysis/selector.py` |
| Título, resumo, tags e texto de thumbnail | `MetadataSuggestion` | `metadata/generator.py` |

## Interface

```python
class LLMClient(Protocol):
    def generate[T: BaseModel](self, system: str, user: str, output_type: type[T]) -> T: ...
```

Quem usa a IA depende só dessa interface; nos testes entram dublês.

## Implementação: AI SDK para Python

`AiSdkClient` adapta o pacote [`ai`](https://pypi.org/project/ai/) (Vercel, **beta público**: a API pode mudar entre versões). O SDK é assíncrono; o adaptador o expõe de forma síncrona.

**Um event loop persistente.** O cliente HTTP do provedor fica preso ao loop que o criou, então `asyncio.run` a cada chamada quebraria a segunda requisição. O adaptador cria um loop próprio no construtor e o reutiliza; `close()` encerra o provedor e o loop.

## Escolha do provedor (`create_llm_client`)

| Variável | Papel |
|---|---|
| `AI_PROVIDER` | ID de provedor do models.dev (`openai`, `anthropic`, `groq`...) |
| `AI_MODEL` | Modelo (padrão `gpt-4.1-mini`) |
| `AI_API_KEY` | Chave; vazia = o SDK lê a variável do provedor (ex.: `OPENAI_API_KEY`) |
| `AI_BASE_URL` | Endpoint alternativo: Ollama, vLLM, proxies, OpenRouter |
| `AI_PROTOCOL` | `auto`, `chat_completions` ou `responses` |
| `AI_TEMPERATURE` | Padrão 0,3 |

### Protocolo
Com `auto`, se `AI_BASE_URL` está definido o projeto usa **chat completions** (o padrão do provedor `openai` é a Responses API, que Ollama, vLLM e a maioria dos proxies não suportam). Sem `AI_BASE_URL`, vale o padrão do provedor.

O provedor `anthropic` exige o extra: `pip install "ai[anthropic]"`.

## Usando o OpenRouter (inclusive modelos gratuitos)

O SDK não aceita `AI_PROVIDER=openrouter` diretamente. Use o OpenRouter como provedor compatível com OpenAI:

```
AI_PROVIDER=openai
AI_BASE_URL=https://openrouter.ai/api/v1
AI_API_KEY=<sua chave>
AI_MODEL=openrouter/free
AI_PROTOCOL=auto
```

`openrouter/free` escolhe um modelo gratuito disponível. Modelos gratuitos são mais fracos e instáveis: erram mais em regras negativas ("não use...") e às vezes respondem 200 com texto vazio. Por isso o retry abaixo é recomendado nesse caso.

## Retry com espera crescente

Opcional (`AI_MAX_RETRIES=0` por padrão). Falhas de HTTP (429, 5xx), resposta vazia e resposta inválida são repetidas:

```
espera = min(AI_RETRY_DELAY_SECONDS × 2^tentativa, AI_RETRY_MAX_DELAY_SECONDS)
```

Com `AI_MAX_RETRIES=3`, `AI_RETRY_DELAY_SECONDS=5` e teto de 60: esperas de 5 s, 10 s e 20 s. Cada tentativa é registrada como aviso (`IA falhou (...); tentativa N/M em Ns`). Esgotadas as tentativas, a exceção sobe e cada consumidor trata a sua:

- **Seleção:** a janela falha e as demais continuam.
- **Triagem:** reprova o vídeo.
- **Metadados:** cai no título de reserva.

## Segurança da chave

`AI_API_KEY` fica só no `.env` (ignorado pelo git). Não a cole em logs, issues ou conversas; se vazar, revogue e gere outra.
