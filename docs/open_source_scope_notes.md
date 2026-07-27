# Open-source scope notes

This file documents where the public release's behavior intentionally differs from the original private working system, and why. Read this before assuming a feature is fully equivalent to what's described elsewhere in the docs.

## 1. Single-endpoint ("simple") mode changes the review panel's semantics

`src/idea_forge/forge.py` defines `IDEA_MODELS = ["gemini-pro", "gpt-5.5", "claude-opus"]` and treats idea review as a 3-independent-model cross-validation panel: each idea is reviewed by all three roles, and a majority vote (≥2/3) decides pass/fail. The intent is to reduce single-model bias — no one model's blind spots or sycophancy alone can pass or kill an idea.

When `AUTORESEARCH_API_BASE_URL` + `AUTORESEARCH_API_KEY` are both set (see `docs/llm_provider_setup.md`), every one of those three roles is routed to the same underlying model. The pipeline still runs three review passes and still requires 2/3 agreement, but all three passes come from the same model — so the "cross-model" bias reduction the design relies on does not hold. This is a deliberate simplification for accessibility, not a hidden bug. If you need genuine cross-model review, configure at least two different providers via `config.local.json` instead of single-endpoint mode.

## 2. Vertex Gemini path is bypassed in simple mode

Normally, any model name starting with `gemini-` is routed through `src/idea_forge/gemini_vertex.py` (Google Vertex AI, `generateContent`), which requires `GOOGLE_APPLICATION_CREDENTIALS` + `GEMINI_VERTEX_PROJECT_ID`. In simple mode, this route is skipped entirely — `gemini-pro`/`gemini-flash` are just role labels that get sent to your configured OpenAI-compatible endpoint like every other role. You do not need a Google Cloud service account to run the pipeline in simple mode.

## 3. What was removed from this release, and why (see also `THIRD_PARTY_NOTICES.md`)

- **Downstream execution runtime** (turning a validated idea into code, experiments, and results) is a separate, private system and is not part of this release. This repository only covers signal collection → idea generation → cross-review → plan drafting. Running `daily_full.py` produces idea + plan JSON output; it does not run experiments.
- **`knowledge_base/`** (domain-knowledge markdown files referenced by `src/idea_forge/b_library.py` and `check_idea.py`) is not included. Code that depends on it degrades gracefully (empty domain context, not a crash) if the directory doesn't exist — you can create your own `knowledge_base/*.md` files locally.
- **Reverse-engineered/forked coding-agent runtime** (`claude-code/` in the private tree) and a **vendored research-report generator** (`gpt-researcher/`) are excluded pending separate legal/provenance review and licensing. Neither is required for this pipeline to run.
- **Internal design docs, investor materials, and a competitor reverse-engineering report** were excluded as out of scope for a public source release (not because the code they described was removed — they described systems not included here in the first place).

## 4. Nothing was disabled purely to make the demo look better

No success-path behavior (retry logic, validation thresholds, consensus checks, freshness refresh) was weakened or hardcoded to pass more easily for the public release. The changes made for open-sourcing were: (a) replacing hardcoded private paths/credentials with environment variables, (b) adding the single-endpoint simple mode as an additive option, (c) removing content that was out of scope (investor docs, competitor analysis, docs describing unreleased components), and (d) minor collector hygiene (rate-limit delays, an added dependency, ToS disclaimers). None of these change what a validated idea has to pass to be accepted.
