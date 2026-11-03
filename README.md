# Hound

**Token-budgeted, self-healing browser automation MCP server that slashes AI agent context costs by 99.2%.**

[![CI](https://github.com/sumitrao9/hound/actions/workflows/ci.yml/badge.svg)](https://github.com/sumitrao9/hound/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-Compatible-6b4fbb)

## Problem

Every mainstream browser-automation MCP server returns the **entire accessibility tree** on every single action. For an agent running multi-step workflows, this is catastrophic:

| Approach | Tokens Per Action | 10-Step Flow | Cost Impact |
| --- | --- | --- | --- |
| **Playwright MCP (baseline)** | ~10,162 | ~114,000 | Expensive at scale |
| **Hound (MCP-native)** | ~343 avg | ~2,744 | **99.2% reduction** |

**Real impact:** $1,050 → **$10.50** in model input costs for identical work across 3 live sites.

This isn't a config issue — it's architectural. Multiple issues have been reported upstream ([#889](https://github.com/microsoft/playwright-mcp/issues/889), [#1216](https://github.com/microsoft/playwright-mcp/issues/1216), [#1573](https://github.com/microsoft/playwright-mcp/issues/1573)) with no fix in sight.

## Solution

Hound is a purpose-built MCP server that gives AI agents browser control **without burning their entire context window**.

| Feature | Impact |
| --- | --- |
| **Delta-based snapshots** | Returns only what changed since the last call, not the full DOM tree every time |
| **Hard token budgets** | Every tool call has a `max_tokens` ceiling with automatic profile degradation |
| **7 focused tools** | Minimal tool surface vs 50-90 in alternatives, reducing noise and cost |
| **Self-healing selectors** | Broken selectors auto-repair by deriving from attributes, scoring against live DOM, and verifying before adopting |
| **Verified extraction** | Structured extraction with confidence scores and verification flags |
| **Persistent memory** | Learned selectors persist per-site, getting smarter over time |

## Demo

> *[Add GIF here showing Hound in action with Claude/Cursor]*

**Quick test:** Run `python -m bench.run` against live sites to reproduce the 99.2% reduction yourself.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Run as MCP server
hound-mcp
```

Add to your MCP client config (e.g., Claude Desktop, Cursor):

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
| `browser_snapshot` | Re-read the page; returns only what changed |
| `browser_act` | Click / fill / press / select, by ref or selector |
| `browser_find` | Locate elements by name or role without a full snapshot |
| `browser_extract` | Structured extraction with confidence and verified flag |
| `browser_heal` | Repair a broken selector, verified, and remember it |
| `browser_budget_report` | Session token spend, by tool |

## Architecture

```
hound/
  core/       # Budget enforcement, element refs, delta computation
  healing/    # Self-healing selector engine with verification
  mcp/        # MCP server with 7-tool surface
bench/        # Reproducible benchmark harness
tests/        # 38 tests, run without browser
```

## Tests

```bash
pytest              # 38 tests, no browser required
python -m bench.run # Full benchmark (needs network + chromium)
```

## Why It Matters

**Hound solves a problem that AI companies actually pay to solve.** As agents become more capable and run longer workflows, context cost becomes the bottleneck. Hound makes browser automation economically viable for production agent workflows.

## License

MIT License - see [LICENSE](LICENSE) for details.
