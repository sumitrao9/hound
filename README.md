# Hound

**A token-budgeted, self-healing browser automation MCP server for AI agents.**

Hound exists because of a specific, measured, and completely unfixed problem: every mainstream
browser-automation MCP server returns the page's full accessibility tree on *every* action, so
per-action cost is O(page size) and total context growth is O(number of actions).

---

## The problem

Measured across the MCP servers an agent is most likely to be handed:

| Behaviour | Cost |
|---|---|
| Playwright MCP: full ARIA tree returned per action | **~10,162 tokens per action** |
| Playwright MCP: 10-step flow | **~114,000 tokens** |
| A single screenshot | ~15,000 tokens |
| One `browser_navigate` response | reported at 28,149 tokens, *over the 25,000 limit* |

This is not a configuration mistake, it is architectural. It has been reported repeatedly
([#889](https://github.com/microsoft/playwright-mcp/issues/889),
[#1216](https://github.com/microsoft/playwright-mcp/issues/1216),
[#1573](https://github.com/microsoft/playwright-mcp/issues/1573)), and the maintainer's response
has consistently been that optimising for token cost is not a priority. Microsoft's own README
now points coding agents at a CLI instead.

Vercel spotted the same gap and shipped `agent-browser` as a **CLI rather than an MCP server**,
reaching 22,000 GitHub stars in two months on a 94% token reduction. Cloudflare added
`minimize_tools` to MCP portals in March 2026 for the same reason. The MCP-native version of that
idea did not exist.

## What Hound does differently

| | Conventional MCP server | Hound |
|---|---|---|
| Per-action response | Full page tree, every time | **Delta against the last call**, plus pointer refs |
| Payload ceiling | None — can exceed the context limit | **Hard `max_tokens` budget**, auto-degrades to a cheaper profile |
| Tool definitions | Often 50–90 tools, all loaded every turn | **7 tools**, all with an explicit budget |
| Broken selector | Fails the run | **Repairs it, verifies the repair, and remembers it per site** |
| Extraction result | Raw dump | **Confidence score + verified flag** |
| Output format | JSON | Compact line format (JSON punctuation is pure overhead) |

### Capture profiles

Every tool call states a `max_tokens` ceiling. Hound returns the most useful representation that
fits and *reports what it dropped*, so the agent can tell the difference between "this page is
small" and "I have not seen the whole page."

| Profile | Returns |
|---|---|
| `minimal` | Confirmation only: element refs and counts. Correct for most actions. |
| `balanced` | Interactive elements with accessible names, text capped. **Default.** |
| `full` | Full element detail including selectors — still clipped to the budget. |

A larger budget with `full` gives a richer page; a small budget with `full` degrades to
`balanced`. A `minimal` request is never silently upgraded.

### Delta snapshots

Elements get stable short refs (`e1`, `e2`). Identity is `role + accessible name`, so a ref
survives unrelated DOM changes, and a textbox whose contents change is reported as a state change
rather than as one element vanishing and another appearing.

On the next call Hound emits only what changed. A navigation is explicitly flagged, because it
voids every ref the agent is holding and a delta would be a lie.

### Self-healing selectors

When a selector breaks, Hound derives candidate replacements from the *original* selector's
attributes, scores them against the live DOM, and adopts one only if it clears a confidence
threshold **and** verifies against a real, actionable element. Verified repairs are persisted per
site, so later runs start already fixed.

The verification step is the point. Adopting a selector that merely *matches* something is how
scrapers silently start returning the wrong data, which is worse than failing loudly.

## Measured results

Reproduce with `python -m bench.run`. The comparison drives the same scripted flow twice: once
emulating a snapshot-per-action server (full ARIA tree + page text on every call), once with
Hound's budgeted delta responses.

**8-step flow, budget 1,200 tokens, profile `balanced`:**

| Page | DOM elements | Snapshot-per-action | Hound | Reduction |
|---|---:|---:|---:|---:|
| news.ycombinator.com | 814 | 93,194 | 805 | **99.1%** |
| en.wikipedia.org/wiki/Web_scraping | 2,153 | 210,272 | 1,003 | **99.5%** |
| python.org | 900 | 47,100 | 936 | **98.0%** |
| **Total** | | **350,566** | **2,744** | **99.2%** |

The 10-step flow these pages produce costs a conventional server ~350k tokens. Hound spends under
3k — roughly **$10.50 in Claude Sonnet input tokens versus $1,050**, on the same work.

Honest caveat: on the *first* snapshot Hound pays for the page, because it has no baseline to diff
against. That step shows a real 20–44x saving rather than being free. The saving comes from every
subsequent call, which is where the cost actually accumulates.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

## Use

Register with any MCP client:

```json
{
  "mcpServers": {
    "hound": {
      "command": "hound-mcp"
    }
  }
}
```

```bash
cp .env.example .env
hound-mcp
```

## Tools

| Tool | Purpose |
|---|---|
| `browser_open` | Navigate and get a budgeted snapshot |
| `browser_snapshot` | Re-read the page; returns only what changed |
| `browser_act` | Click / fill / press / select, by ref or selector |
| `browser_find` | Locate elements by name or role without a full snapshot |
| `browser_extract` | Structured extraction with confidence and verified flag |
| `browser_heal` | Repair a broken selector, verified, and remember it |
| `browser_budget_report` | Session token spend, by tool |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `HOUND_DB` | `hound-selectors.db` | Where learned selector overrides persist |
| `HOUND_DEFAULT_BUDGET` | `1200` | Default token ceiling per response |
| `HOUND_MAX_BUDGET` | `20000` | Hard cap; a caller cannot exceed it |
| `HOUND_HEADLESS` | `1` | Set to `0` to watch the browser work |

## Architecture

```
hound/
  core/
    budget.py     Token estimation, profiles, hard budgets, degradation
    refs.py       Element identity, stable refs, delta computation
    engine.py     The budgeted browser wrapper
  healing/
    selectors.py  Candidate generation, scoring, verification, persistence
  mcp/
    server.py     The 7-tool MCP surface
bench/
  run.py          The benchmark that produces the table above
tests/            38 tests
```

## Tests

```bash
pytest              # 38 tests, no browser required
python -m bench.run # needs network + chromium
```

The unit suite covers budget enforcement, profile degradation, delta correctness, and the
selector healer without launching a browser, so it runs in under a second.

## Responsible use

Hound automates a browser you control against sites you choose. Respect each site's terms of
service and `robots.txt`, and keep request rates polite. It is built for research, monitoring,
testing, and automation of sources that permit it.

## License

MIT
