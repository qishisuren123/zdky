# AutoResearch V3 (core pipeline)

AutoResearch V3's core pipeline turns multi-source research signals (papers, forums, blogs, AI media, trending repos) into candidate research ideas, then cross-validates and expands the strongest ones with multiple LLMs.

This repository contains the **idea-generation pipeline only** — signal collection, filtering, and multi-model idea forging. It does not include the (separate, private) downstream execution runtime that turns an idea into code/experiments/results — that component has not been open-sourced yet.

## What's actually in this repository

```text
.
├── daily_full.py              # main daily pipeline entrypoint
├── run_pending_forge.py       # resume/retry pending Idea Forge jobs
├── check_idea.py              # review one idea against your own knowledge base (CLI)
├── run_daily.sh               # example cron wrapper for daily_full.py
├── config/settings.py         # collector-level settings (RSS feeds, keywords, thresholds)
├── config.example.json        # provider/model config template — copy to config.local.json
├── .env.example                # environment variable template — copy to .env
├── src/
│   ├── pipeline_v4.py          # signal collection + filtering orchestration
│   ├── llm_client.py           # multi-provider LLM request client
│   ├── generate_dashboard.py   # renders a static dashboard from pipeline output
│   ├── generate_idea_page.py   # renders a static per-idea page
│   ├── scheduler.py             # simple run scheduling helper
│   ├── collectors/              # one module per signal source (see below)
│   └── idea_forge/              # multi-model idea generation + cross-validation
├── docs/
│   ├── llm_provider_setup.md   # how to configure each LLM provider
│   ├── open_source_scope_notes.md  # what differs from the private system, and why
│   └── secrets.md               # credential handling policy
└── scripts/
    ├── secret_scan.py            # redacted secret-pattern scan for a release tree
    └── check_release_tree.py     # checks a release tree doesn't contain blocked paths
```

There is no `data/`, `knowledge_base/`, `claude-code/`, `gpt-researcher/`, `AR-in-CC/`, or `showcase/` directory in this repository. If you see any documentation, code comment, or design note that references one of those, treat it as describing a larger private system this pipeline was extracted from, not something you need to have here.

## Signal collectors (`src/collectors/`)

| Collector | Source | Notes |
|---|---|---|
| `arxiv_collector.py` | arXiv API | Official API. |
| `hf_papers_collector.py` | HuggingFace Daily Papers API | Official API. |
| `openreview_collector.py` | OpenReview | Uses `openreview-py`. |
| `rss_collector.py`, `paper_digest_collector.py` | RSS feeds | Standard RSS polling. |
| `hackernews_collector.py` | HN Firebase API | Official, unauthenticated public API. |
| `github_trending_collector.py` | github.com/trending | HTML scraping; no official API exists for this page. |
| `influential_voices.py` | Mixed (RSS + HN) | Aggregates influential-researcher content. |
| `jiqizhixin_collector.py` | 机器之心 | Returns empty by design — this site blocks scraping and requires a paid data service; kept as documentation of that fact. |
| `jina_chinese_media.py` | Chinese AI media, via Jina Reader | **Read the module docstring before using.** This works around anti-scraping measures on some target sites and may violate their Terms of Service. Use at your own risk. |
| `twitter_collector.py`, `try.py` | X/Twitter, via Scweet/twikit | **Disabled by default** (`config.example.json` → `twitter.enabled: false`). Requires your own X account/cookies, used at your own risk under X's Terms of Service. Not an officially sanctioned integration. |

None of the official-API collectors (arXiv, HN, HuggingFace, OpenReview, RSS) raise ToS concerns. The scraping-based ones are called out above — read their docstrings before enabling them.

## Idea Forge (`src/idea_forge/`)

Multi-model idea generation and cross-validation:

- `forge.py` — orchestrates idea generation across `IDEA_MODELS` (default: a Gemini model, GPT-5.5, and Claude Opus) and plan generation via `PLAN_MODEL`.
- `b_library.py` — maps research directions to knowledge files under an optional `knowledge_base/` directory (not included in this repo; if that directory doesn't exist, domain-knowledge context is simply empty — nothing breaks).
- `consensus_check.py`, `freshness.py`, `influential_people.py` — supporting filters used during idea generation.
- `gemini_vertex.py` — Vertex AI Gemini client, configured entirely through environment variables (see below).

## Setup — quickest path (one API, one endpoint)

If you only have a single OpenAI-compatible endpoint (your own gateway or any commercial provider that speaks the OpenAI Chat Completions protocol), this is all you need:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export AUTORESEARCH_API_BASE_URL=https://your-provider.example.com/v1
export AUTORESEARCH_API_KEY=your_api_key_here
export AUTORESEARCH_API_MODEL=your-model-name   # optional, defaults to gpt-4o-mini

python daily_full.py
```

This routes every model role in the pipeline (idea generation, cross-review, planning) to your one endpoint. **Trade-off:** the pipeline's review step is designed as a 3-independent-model cross-validation panel; in this mode all three reviewer roles are the same underlying model, so you get 3 review passes from one model rather than genuine cross-model review. See `docs/open_source_scope_notes.md` for the full list of behavior differences in this mode.

## Setup — advanced (multiple providers)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config.example.json config.local.json
cp .env.example .env
export AUTORESEARCH_CONFIG=$PWD/config.local.json
```

Fill in your own provider credentials in `.env` or `config.local.json` — never commit real values. See `docs/llm_provider_setup.md` for provider-by-provider setup (Anthropic, OpenAI-compatible, Gemini API key, Vertex Gemini) and `docs/secrets.md` for the credential-handling policy.

Then run the pipeline:

```bash
python daily_full.py
```

or review a single idea against your own knowledge base:

```bash
python check_idea.py --list
```

## Before publishing your own fork

If you're building a release from this tree, run:

```bash
python scripts/secret_scan.py .
python scripts/check_release_tree.py .
```

Both must pass before anything is published. See `docs/secrets.md` for what must never be committed.

## License

MIT — see `LICENSE`. See `THIRD_PARTY_NOTICES.md` for third-party component notes.
