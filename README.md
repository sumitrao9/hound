# Hound

**Token-budgeted, self-healing browser automation MCP server for AI agents.** Self-host (stdio) or run as a **hosted HTTP/Streamable MCP** endpoint with API-key auth.

[![CI](https://github.com/sumitrao9/hound/actions/workflows/ci.yml/badge.svg)](https://github.com/sumitrao9/hound/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-Compatible-6b4fbb)

## What it is
Hound gives AI agents browser control with **budgeted responses** and **delta snapshots** (returns only what changed). It also **heals selectors** and remembers verified repairs per site.

## Superpowers (13 tools)
| Tool | Purpose |
| --- | --- |
| `browser_open` | Navigate and get a budgeted snapshot (`url`) |
| `browser_snapshot` | Re-read page; delta by default (`full_snapshot`) |
| `browser_act` | `action` + `target` (ref like `e3` or CSS), optional `value` — supports `click/fill/press/select/hover` |
| `browser_find` | Find by accessible `text` (optional `role`,`limit`) |
| `browser_extract` | Extract with `root` + `fields` map; confidence/verified |
| `browser_heal` | Repair `selector` for `logical_key`; verify & remember |
| `browser_content` | Budgeted, cleaned text extraction (page or selector) |
| `browser_eval` | Run JS in page context, return budgeted result |
| `browser_wait` | Wait for selector/text/state before next action |
| `browser_scroll` | Scroll page or element (up/down) |
| `browser_screenshot` | JPEG screenshot (base64 when within budget, else size metadata) |
| `browser_pdf` | PDF export (base64 when within budget) — Chromium |
| `browser_budget_report` | Session token spend + optimizer/selector stats |

All tools accept `max_tokens` and enforce budgeted responses (profile degradation + truncation reporting). Screenshots/PDFs are **budget-aware**: if the payload would blow the token budget, Hound returns size metadata instead of dumping base64.

## Measured results
Benchmark (`bench/run_fixed2.py`, see `bench/results/latest.json`): baseline = full ARIA snapshot + body text per step; Hound = budgeted/delta.

| Page | Conventional | Hound | Reduction |
| --- | ---:| ---:| ---:|
| example.com | 8,781 | 614 | 93.0% |
| news.ycombinator.com | 1,687 | 192 | 88.6% |
| en.wikipedia.org/wiki/Web_scraping | 212,358 | 1,145 | 99.5% |

**Overall:** 222,826 → 1,951 tokens (**~99.1%**). First snapshot has no delta baseline; results vary by page/flow.

## Tools (7)
| Tool | Purpose |
| --- | --- |
| `browser_open` | Navigate and get a budgeted snapshot (`url`) |
| `browser_snapshot` | Re-read page; delta by default (`full_snapshot`) |
| `browser_act` | `action` + `target` (ref like `e3` or CSS), optional `value` |
| `browser_find` | Find by accessible `text` (optional `role`,`limit`) |
| `browser_extract` | Extract with `root` + `fields` map; confidence/verified |
| `browser_heal` | Repair `selector` for `logical_key`; verify & remember |
| `browser_budget_report` | Session token spend |

## Quick Start (self-host, stdio)
```bash
pip install git+https://github.com/sumitrao9/hound
playwright install chromium
hound-mcp
```
MCP client config:
```json
{"mcpServers":{"hound":{"command":"hound-mcp","env":{"HOUND_DEFAULT_BUDGET":"1200","HOUND_HEADLESS":"1"}}}}
```

## Run as 24/7 Hosted MCP (HTTP/Streamable)
```bash
export HOUND_API_KEY="your-secret-key"   # optional but recommended for hosted
export HOUND_HOST=0.0.0.0
export HOUND_PORT=8000
hound-mcp-http
# MCP endpoint: http://HOST:8000/mcp  (also mounted at /)
# Health: /health
```
Auth: send `Authorization: Bearer <HOUND_API_KEY>`. Supports `HOUND_API_KEYS` (comma-separated). No key set = open (dev only).

## Docker
```bash
docker build -t hound-mcp .
docker run -p 8000:8000 -e HOUND_API_KEY=secret hound-mcp hound-mcp-http
```

## Environment variables
| Variable | Default | Notes |
| --- | --- | --- |
| `HOUND_DEFAULT_BUDGET` | `1200` | Token budget |
| `HOUND_MAX_BUDGET` | `20000` | Max budget |
| `HOUND_HEADLESS` | `1` | Headless browser |
| `HOUND_DB` | `hound-selectors.db` | Selector memory DB |
| `HOUND_API_KEY` / `HOUND_API_KEYS` | *(unset)* | Bearer auth for HTTP mode |
| `HOUND_HOST` / `HOUND_PORT` | `0.0.0.0` / `8000` | HTTP bind |
| `HOUND_JSON_RESPONSE` | `0` | JSON responses vs SSE |
| `HOUND_STATELESS` | `0` | Stateless sessions |

## Monetization / Support (use Hound)
- **Hosted 24/7 MCP endpoint** (managed, API key, usage limits) — [request access / waitlist](https://github.com/sumitrao9/hound/issues/new?template=hosted-waitlist.yml) (INR ₹799–₹3,999/mo or $9–$49/mo + usage, *estimate/validate*; pay via Razorpay/Stripe/checkout link on approval).
- **Pro/support**: integration help, custom tools, authorized automation workflows.
- **Agensi skill**: installable skill package for local MCP setup.
- **GitHub Sponsors** / inquiries: https://github.com/sumitrao9/hound/issues

## Safety & limitations
Only automate sites/data you are **authorized** to access. Respect ToS/law. Budgeting may truncate (use `browser_find`/`browser_extract`). Requires Playwright/Chromium.

## Development
```bash
pip install -e ".[dev]"
ruff check .
pytest -v -m "not live"
```

## License
MIT
