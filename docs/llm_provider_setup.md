# LLM provider and credential setup

This project is designed for user-provided credentials. Do not commit real API keys, auth tokens, cookies, passwords, service-account JSON files, or `.env` files.

## Quickest path: one API, one endpoint

If you only have a single OpenAI-compatible endpoint (your own gateway, or any commercial provider that speaks the OpenAI Chat Completions protocol), you don't need `config.local.json` at all. Set three environment variables:

```bash
export AUTORESEARCH_API_BASE_URL=https://your-provider.example.com/v1
export AUTORESEARCH_API_KEY=your_api_key_here
export AUTORESEARCH_API_MODEL=your-model-name   # optional, defaults to gpt-4o-mini
```

When both `AUTORESEARCH_API_BASE_URL` and `AUTORESEARCH_API_KEY` are set, every model role in the pipeline (idea generation, cross-review, planning) routes to this one endpoint — you do not need separate Anthropic/Gemini/DeepSeek credentials to run the full pipeline end to end.

**Trade-off to know before you rely on this:** the pipeline's idea-review step is designed as a 3-model cross-validation panel (each model reviews the others' ideas to reduce single-model bias). In this single-endpoint mode, all three "reviewer" roles route to the same model, so you get 3 review passes from one model rather than genuinely independent cross-model review. This is expected behavior, not a bug — see `docs/open_source_scope_notes.md` for the full list of behavior differences in this mode.

Everything below this section describes the advanced, multi-provider setup — skip it if the quickest path above is enough for you.

## Safe setup flow (multi-provider)

1. Copy the public templates:

```bash
cp config.example.json config.local.json
cp .env.example .env
```

2. Fill `.env` or export variables in your shell. Keep `.env` and `config.local.json` untracked.

3. Point the runtime at your local config:

```bash
export AUTORESEARCH_CONFIG=/path/to/AutoResearch_V3/config.local.json
```

4. Run a smoke test with an offline fixture before spending LLM tokens.

## Main AutoResearch provider surface

The main Python pipeline uses `src/llm_client.py`. Its public config template is `config.example.json`; your private copy can define provider presets.

Supported request-method families in the current codebase:

| Request method | Typical providers | Required variables | Notes |
|---|---|---|---|
| Anthropic Messages API | Claude first-party or compatible gateway | `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`, optional `ANTHROPIC_BASE_URL` | Use exact Claude model IDs supported by your provider. |
| OpenAI Chat Completions | OpenAI, DeepSeek, DashScope/Qwen, SiliconFlow, OpenRouter, private gateways | provider API key + base URL | Most third-party providers use this shape. |
| OpenAI Responses API | GPT-style private gateways | provider API key + base URL | Only use if the endpoint explicitly supports `/v1/responses`. |
| Google Gemini OpenAI-compatible API | Gemini API key path | `GEMINI_API_KEY` | Uses Google OpenAI-compatible `/chat/completions`. |
| Vertex Gemini `generateContent` | Google Vertex AI | `GOOGLE_APPLICATION_CREDENTIALS`, `GEMINI_VERTEX_PROJECT_ID`, `GEMINI_VERTEX_LOCATION` | Idea Forge currently routes Gemini through this path. |

## Idea Forge multi-model setup

The main multi-model logic is in `src/idea_forge/forge.py`:

- `IDEA_MODELS` controls the idea-generation/review panel.
- `PLAN_MODEL` controls plan generation.
- Gemini models currently go through `src/idea_forge/gemini_vertex.py`.
- Non-Gemini models go through `src/llm_client.py`.

To add or swap a model:

1. Add a provider preset to your private config.
2. Add a safe alias if you want a short model name.
3. Ensure `call_model()` knows how to route that provider shape.
4. Add the short model name to `IDEA_MODELS` or `PLAN_MODEL`.
5. Run a small paid integration test and record the provider/model used in the output metadata.

## Provider examples

### Anthropic / Claude

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_BASE_URL=https://api.anthropic.com
```

Recommended current public Claude model IDs for new Anthropic API integrations include `claude-opus-4-8`, `claude-sonnet-5`, and `claude-haiku-4-5`. If you use another gateway, confirm its model list and request surface.

### OpenAI

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1
```

### DeepSeek

```bash
export DEEPSEEK_API_KEY=...
# Base URL: https://api.deepseek.com/v1
# Example model: deepseek-chat
```

### Qwen / DashScope

```bash
export DASHSCOPE_API_KEY=...
# Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1
# Example model: qwen-max
```

### SiliconFlow

```bash
export SILICONFLOW_API_KEY=...
# Base URL: https://api.siliconflow.cn/v1
# Pick a model from your SiliconFlow account and put it in config.local.json.
```

### Gemini API key path

```bash
export GEMINI_API_KEY=...
```

### Vertex Gemini

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
export GEMINI_VERTEX_PROJECT_ID=your-gcp-project
export GEMINI_VERTEX_LOCATION=global
```

Never commit the service-account JSON file.

## Scope of this release

This repository ships only the core AutoResearch Python pipeline (`src/`, `config/`, root entrypoints). It does not include a bundled research-report generator or an agentic coding runtime. If you integrate this pipeline with other tools that have their own provider systems, configure those tools separately — their settings do not automatically change the provider panel described above.

## Secret hygiene checklist

Before publishing, run a secret scan and verify that these are absent from tracked files and release archives:

- `sk-...` provider keys
- `AIza...` Google API keys
- `tvly-...` Tavily keys
- Twitter/X passwords and auth tokens
- `Authorization:` and `Bearer` headers
- service-account JSON files
- `.env`, `config.local.json`, `settings.local.json`, cookies, and session DBs

If a real key ever appeared in a file that might be shared, rotate it. Removing it from Git history is not enough.
