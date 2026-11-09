# Hound

**Token-budgeted, self-healing browser automation MCP server for AI agents.**

[![CI](https://github.com/sumitrao9/hound/actions/workflows/ci.yml/badge.svg)](https://github.com/sumitrao9/hound/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-Compatible-6b4fbb)

## What it is

Hound is a purpose-built MCP server that gives AI agents browser control with budgeted responses and delta-based snapshots. Instead of re-serializing the entire accessibility tree on every action, Hound tracks page state and returns only what changed (within a token budget). When selectors break, it can heal them and remember repairs per site.

## Measured results

Benchmark methodology (see [`bench/run_fixed2.py`](bench/run_fixed2.py)): compare a "snapshot-per-action" baseline (full ARIA snapshot + body text on every step, tokenized with `estimate_tokens`) against Hound (budgeted/delta responses). First snapshot has no baseline to diff against and costs more. Flows vary by page; actions are skipped if not found.

From [`bench/results/latest.json`](bench/results/latest.json):

| Page | Conventional total | Hound total | Reduction | Steps |
| --- | --- | --- | --- | --- |
| https://example.com | 8,781 | 614 | 93.0% | 7 |
| https://news.ycombinator.com | 1,687 | 192 | 88.6% | 7 |
| https://en.wikipedia.org/wiki/Web_scraping | 212,358 | 1,145 | 99.5% | 8 |

**Overall across these pages:** 222,826 → 1,951 tokens = **99.1% reduction** (sum of totals). Per-page results range from 88.6% to 99.5% depending on page size and how much changes between steps.

## Quick Start

### Install

The package is **not currently published on PyPI**. Install from source:

```bash
# From GitHub
pip install git+https://github.com/sumitrao9/hound

# Or in development mode
git clone https://github.com/sumitrao9/hound.git
cd hound
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium
```

### Run as MCP server
```bash
hound-mcp
```

### MCP client config
Add to your MCP client (e.g., Claude Desktop, Cursor):

```json
{
  "mcpServers": {
    "hound": {
      "command": "hound-mcp",
      "env": {
        "HOUND_DEFAULT_BUDGET": "1200",
        "HOUND_HEADLESS": "1"
      }
    }
  }
}
```

## Tools

| Tool | Purpose |
| --- | --- |
| `browser_open` | Navigate and get a budgeted snapshot |
| `browser_snapshot` | Re-read the page; returns only what changed (delta) when possible |
| `browser_act` | Click / fill / press / select, by ref or selector |
| `browser_find` | Locate elements by name or role without a full snapshot |
| `browser_extract` | Structured extraction with confidence scores and verified flag |
| `browser_heal` | Repair a broken selector, verified, and remember it |
| `browser_budget_report` | Session token spend, by tool |

## Environment variables

Defaults verified against code:

| Variable | Default | Notes |
| --- | --- | --- |
| `HOUND_DB` | OS-appropriate (see `hound/healing/selectors.py` DEFAULT_DB) | Path to SQLite DB for learned selectors/healing history |
| `HOUND_DEFAULT_BUDGET` | `1200` | Default token budget (see `hound/mcp/server.py`) |
| `HOUND_MAX_BUDGET` | (engine-dependent) | Max budget enforced by engine |
| `HOUND_HEADLESS` | `1`/`true` | Run browser headless (MCP server respects this) |

## Who it's for / limitations

**For:**
- AI agents doing multi-step web workflows where context cost matters
- Cases where you need to act on specific elements without dumping full DOM
- Sites where selectors change and you want automatic healing

**Limitations:**
- Requires Playwright/Chromium
- Some actions may need JS/healing on complex SPAs
- Budgeting/truncation means you may not see the full page - use `browser_find`/`browser_extract` for targeted info
- First snapshot has no delta baseline
- Network access needed for live sites

## Not to be confused with

- **PyPI package `hound-mcp`** is a different project (web research, command `hound`). 
- **This project:** PyPI name `hound-browser-mcp`, console command `hound-mcp` (same command name as the other project - be aware of which one is installed).
- **Repo:** `https://github.com/sumitrao9/hound`

## Development

```bash
pip install -e ".[dev]"
pytest -v
```

## License
MIT
