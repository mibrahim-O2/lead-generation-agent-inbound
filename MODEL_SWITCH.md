# Switching the model provider

The agent can run on OpenAI (the default) or on another provider. Switching is
done **only in `.env`**. No code changes.

```
LLM_PROVIDER=<provider>
LLM_MODEL=<model name>
<THAT_PROVIDER'S_KEY>=<your key>
```

Never put a key in a command, a commit or a chat. Keys live only in `.env`,
which is git-ignored.

## How it works

All provider code is in one file, `src/leadgen/llm.py`. The function
`resolve_llm` reads `LLM_PROVIDER` and `LLM_MODEL` and returns the model the
agent uses. Nothing else in the code base knows which provider is in use.

There are three routes, all part of the OpenAI Agents SDK (checked against the
installed `openai-agents` 0.24 source):

| Route | Providers | Extra install |
| --- | --- | --- |
| SDK default (OpenAI Responses API) | `openai` | none |
| The SDK's LiteLLM extension (`LitellmModel`) | `anthropic`, `gemini`, `mistral`, `deepseek`, `groq`, `openrouter`, `ollama` | `pip install -e ".[providers]"` |
| The SDK's Chat Completions model with a custom base URL | `openai_compatible` | none |

Install the extra once if you use any provider on the LiteLLM route:

```bash
pip install -e ".[providers]"
```

## Quick reference

| `LLM_PROVIDER` | Key variable | Other variables | Where to get the key |
| --- | --- | --- | --- |
| `openai` (default) | `OPENAI_API_KEY` | `LLM_MODEL` optional | https://platform.openai.com/api-keys |
| `anthropic` | `ANTHROPIC_API_KEY` | `LLM_MODEL` required | https://console.anthropic.com/ |
| `gemini` | `GEMINI_API_KEY` | `LLM_MODEL` required | https://aistudio.google.com/apikey |
| `mistral` | `MISTRAL_API_KEY` | `LLM_MODEL` required | https://console.mistral.ai/ |
| `deepseek` | `DEEPSEEK_API_KEY` | `LLM_MODEL` required | https://platform.deepseek.com/ |
| `groq` | `GROQ_API_KEY` | `LLM_MODEL` required | https://console.groq.com/keys |
| `openrouter` | `OPENROUTER_API_KEY` | `LLM_MODEL` required | https://openrouter.ai/keys |
| `ollama` | none | `LLM_MODEL` required, `OLLAMA_BASE_URL` optional | runs on your own machine |
| `openai_compatible` | `LLM_API_KEY` | `LLM_MODEL` and `LLM_BASE_URL` required | your provider or server |

`LLM_MODEL` must be a model name from that provider's own model list. Model
names change often, so the examples below use a placeholder. Copy the exact name
from the provider's documentation.

## Per provider

For every provider the answer to "which file changes?" is the same: **only
`.env`**. The code that reads it is the `PROVIDERS` table in
`src/leadgen/llm.py`; you do not need to edit it.

### OpenAI (default)

```
LLM_PROVIDER=openai
LLM_MODEL=your-openai-model-name
OPENAI_API_KEY=sk-REPLACE-ME
```

- `LLM_MODEL` may be left empty; the SDK then uses its own default model.
- Uses the OpenAI Responses API. Tool calling and structured output are
  supported by the SDK on this route.
- Tracing: the SDK uploads run traces to your OpenAI account. Set
  `OPENAI_AGENTS_DISABLE_TRACING=1` to turn that off.
- This is the only route that has been run with a real key in this project.

### Anthropic

```
LLM_PROVIDER=anthropic
LLM_MODEL=your-anthropic-model-name
ANTHROPIC_API_KEY=REPLACE-ME
```

Sent to LiteLLM as `anthropic/<LLM_MODEL>`.

### Google Gemini

```
LLM_PROVIDER=gemini
LLM_MODEL=your-gemini-model-name
GEMINI_API_KEY=REPLACE-ME
```

Sent to LiteLLM as `gemini/<LLM_MODEL>`. This is the Google AI Studio key, not a
Google Cloud service account.

### Mistral

```
LLM_PROVIDER=mistral
LLM_MODEL=your-mistral-model-name
MISTRAL_API_KEY=REPLACE-ME
```

Sent to LiteLLM as `mistral/<LLM_MODEL>`.

### DeepSeek

```
LLM_PROVIDER=deepseek
LLM_MODEL=your-deepseek-model-name
DEEPSEEK_API_KEY=REPLACE-ME
```

Sent to LiteLLM as `deepseek/<LLM_MODEL>`.

### Groq

```
LLM_PROVIDER=groq
LLM_MODEL=your-groq-model-name
GROQ_API_KEY=REPLACE-ME
```

Sent to LiteLLM as `groq/<LLM_MODEL>`.

### OpenRouter

```
LLM_PROVIDER=openrouter
LLM_MODEL=vendor/model-name
OPENROUTER_API_KEY=REPLACE-ME
```

Sent to LiteLLM as `openrouter/<LLM_MODEL>`. OpenRouter model names contain a
slash of their own; paste the name exactly as OpenRouter shows it.

### Ollama (local model)

```
LLM_PROVIDER=ollama
LLM_MODEL=your-local-model-name
# OLLAMA_BASE_URL=http://localhost:11434
```

- No key. Ollama must be installed and running, and the model pulled.
- Sent to LiteLLM as `ollama_chat/<LLM_MODEL>`, which uses Ollama's chat API.
- `OLLAMA_BASE_URL` defaults to `http://localhost:11434`. Do not add `/v1`.
- Nothing leaves your machine, and it costs nothing.

### Any OpenAI-compatible server

```
LLM_PROVIDER=openai_compatible
LLM_MODEL=your-model-name
LLM_BASE_URL=https://your-server.example.com/v1
LLM_API_KEY=REPLACE-ME
```

For a provider or self-hosted server that speaks the OpenAI Chat Completions
API. No extra install. If the server needs no key, set `LLM_API_KEY` to any
non-empty text such as `none`.

## Known limits

These apply to every provider other than OpenAI:

- **Not tested live.** No provider other than OpenAI has been called from this
  project. The wiring is covered by tests that run without keys or network, and
  the model classes come from the SDK, but real behaviour with each provider is
  unverified. Follow "After switching" below before relying on one.
- **Tool calling is required.** The agent has eight tools. A model that cannot
  call functions will not work.
- **Structured output.** The agent's final answer is requested as a strict JSON
  schema (the SDK sends a `json_schema` response format on these routes). A
  model or provider that does not support that will fail or return an invalid
  answer. Such a lead ends as a human handover with the error recorded; nothing
  is lost and nothing is sent.
- **Tracing is switched off.** SDK traces are uploaded to OpenAI. With another
  provider that would send lead data to a second company, so this project
  disables tracing for every non-OpenAI provider.
- **Quality varies.** Smaller and local models follow long instructions less
  reliably. Expect more rejected drafts and more handovers. The code-level
  rules still hold whatever the model does.
- **Cost estimates** use the prices in `config/client.yaml`. Update them when
  you switch.
- **Dependencies.** The `providers` extra installs LiteLLM, which is a large
  package.

## After switching

1. Run a single lead as a dry run. This costs a few thousand tokens and writes
   nothing:

```bash
python -m leadgen --source sample --dry-run --limit 1
```

   A wrong provider name, a missing key or a missing install stops here with a
   one-line error that says what to fix, before any API call is made.

2. Run one eval case on the new model (costs tokens):

```bash
make evals-live-case CASE=21_sample_s001_hot_home
```

3. If that passes, run the full set (costs more tokens):

```bash
make evals-live
```

   The table shows the reason for every handover and every rejected draft.

## What NOT to change

- Do not add provider imports, API calls or keys anywhere outside
  `src/leadgen/llm.py`. A test fails if another module imports a provider class.
- Do not put a key in code, in `presets/`, in `config/`, in a `VITE_*` variable
  or in a command. Keys go in `.env` only.
- Do not edit the agent instructions, tools or guardrails to make a weaker model
  pass. The hard rules (drafts only, no price or date promises, handover rules,
  lead text is data) do not depend on the provider and must stay as they are.
- Do not change the pinned `openai-agents` version casually. The provider
  routes were checked against 0.24.
- Do not re-enable tracing for a non-OpenAI provider without deciding that lead
  data may be sent to OpenAI as well.
- Do not remove `LEADGEN_MOCK_LLM`. Tests, CI and the demo depend on it.

## Adding a provider that is not listed

If LiteLLM supports it, add one line to the `PROVIDERS` table in
`src/leadgen/llm.py`:

```python
"newprovider": ProviderSpec("litellm", "NEWPROVIDER_API_KEY", "litellm-prefix"),
```

Then document its key in `example.env` and in this file (a test checks both).
If it speaks the OpenAI API, you do not need to add anything: use
`openai_compatible`.

## Troubleshooting

| What you see | What to do |
| --- | --- |
| `Unknown LLM_PROVIDER '...'` | Use one of the names in the quick reference table. |
| `Missing API key: LLM_PROVIDER=... needs ..._API_KEY in .env` | Set that variable in `.env`. The placeholder `REPLACE-ME` counts as missing. |
| `LLM_MODEL is required when LLM_PROVIDER=...` | Set `LLM_MODEL` to a model name from the provider's list. |
| `This provider needs the optional LiteLLM extra` | Run `pip install -e ".[providers]"`. |
| `LLM_BASE_URL is required` | Set `LLM_BASE_URL` for `openai_compatible`. |
| Every lead ends in handover with "Agent run failed" | Read the error after it. A "model not found" error means `LLM_MODEL` is wrong. An error about tools or response format means the model lacks tool calling or JSON-schema output; choose another model. |
| Ollama: connection refused | Start Ollama, and check `OLLAMA_BASE_URL`. |
| It still uses the mock | Set `LEADGEN_MOCK_LLM=0` in `.env`. |
| It still uses OpenAI | Check `LLM_PROVIDER` is spelled correctly and not commented out. Real environment variables win over `.env`. |
