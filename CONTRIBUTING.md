# Contributing to AutoResearch V3

Thanks for your interest in AutoResearch V3. This repository contains research-system code and evidence-oriented documentation, so contributions should preserve reproducibility and claim discipline.

## Ground rules

- Never commit API keys, auth tokens, cookies, passwords, service-account JSON files, `.env` files, local Claude settings, logs with headers, or generated private data.
- Use `config.example.json` and `.env.example` as templates. Keep real values in ignored local files or environment variables.
- Keep claims tied to evidence. If a result is protocol-level, tool-level, or workflow-level, label it accordingly.
- Prefer small, reviewable pull requests.

## Development setup

The public source-core setup is being sanitized. For now, start from:

```bash
cp config.example.json config.local.json
cp .env.example .env
export AUTORESEARCH_CONFIG=$PWD/config.local.json
```

Then install the documented dependencies for the specific subsystem you are working on.

## Tests

Before sending a PR, run offline checks that do not require paid provider credentials. Live LLM integration tests should be marked explicitly and should not run by default in CI.

## Security-sensitive changes

Changes touching provider routing, credential loading, Twitter/X collection, remote execution, Docker, or release packaging require extra review.
