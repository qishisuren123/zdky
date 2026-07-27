# Third-party notices

This release contains only the AutoResearch V3 idea-generation pipeline (`src/`, `config/`, root entrypoints, `docs/`, `scripts/`). It does **not** include and has never included, in this specific release:

- `gpt-researcher/` — a separate upstream project with its own license and governance files. Not vendored here. If you integrate it separately, follow its own license terms.
- `claude-code/` — a separate runtime/fork tree. Not included here pending legal/provenance review; do not add it to this repository without that review.
- `node_modules/`, `.conda-env/`, `dist/`, generated binaries, and run artifacts — never committed to this release.

## Third-party Python dependencies

See `requirements.txt` for required dependencies (permissively licensed: httpx, requests, beautifulsoup4, lxml, feedparser, arxiv, openreview-py, google-auth, pandas, numpy, pytest) and its optional-dependencies section for the Twitter/X collection path (`Scweet`, `twikit`) — verify their current license and maintenance status yourself before depending on them, since that path is not required for core functionality.

## Attribution

`src/collectors/jina_chinese_media.py` credits `github.com/qhlx/SciDataDaily` as an inspiration (no code copied from that project).
