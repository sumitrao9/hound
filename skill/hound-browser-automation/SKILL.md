---
name: hound-browser-automation
description: Token-budgeted, self-healing browser automation via the Hound MCP server. Use when you need to browse, click, fill forms, or extract data with minimal context cost using budgeted/delta snapshots and automatic selector healing.
version: 1.0.1
---

# Hound Browser Automation

## When to use Hound vs a full-tree browser MCP
- **Use Hound** when doing multi-step flows and you want only changed elements returned (delta snapshots). Good for long sessions where context cost matters.
- **Use a full-tree browser MCP** when you need a complete, untruncated view of the page on every call, or for simple one-off dumps where delta tracking isn't needed.
- **Note:** First snapshot has no baseline to diff against. With budgeting, you may not see everything - use `browser_find` or `browser_extract` for targeted info.

## Prerequisites
Hound is **not currently on PyPI**. Install from source.

## Workflow: open -> act -> snapshot(delta) -> extract -> heal
1. **Open**: `browser_open` with `url`. Get budgeted snapshot.
2. **Act**: Use `browser_act` with `action` + `target` (ref like `e3` or CSS selector). Pass `value` for fill/press/select.
3. **Snapshot**: After actions/navigation, use `browser_snapshot` (delta) to get only changes.
4. **Find**: Use `browser_find` with `text` (and optional `role`) to locate elements without a full snapshot.
5. **Extract**: Use `browser_extract` with `root` and `fields` map for structured data.
6. **Heal**: If a selector fails, use `browser_heal` with `selector` and `logical_key`; Hound verifies and remembers repairs.

## Tools (all 7)
| Tool | Required | Key options |
|---|---|---|
| `browser_open` | `url` | `wait_until`, `max_tokens`, `profile` |
| `browser_snapshot` | - | `full_snapshot`, `max_tokens`, `profile` |
| `browser_act` | `action`, `target` | `value` (fill/press/select) |
| `browser_find` | `text` | `role`, `limit` |
| `browser_extract` | `root`, `fields` | `max_tokens` |
| `browser_heal` | `selector`, `logical_key` | - |
| `browser_budget_report` | - | - |

## Environment variables
| Variable | Default | Notes |
| --- | --- | --- |
| `HOUND_DB` | OS default | Learned selectors DB |
| `HOUND_DEFAULT_BUDGET` | `1200` | Token budget |
| `HOUND_HEADLESS` | `1` | Headless mode |

## Not the web-research Hound
**PyPI package `hound-mcp` is a different project** (web research, command `hound`). This is **`hound-browser-mcp`** (repo: https://github.com/sumitrao9/hound). If installed from source, run `hound-mcp` or `python -m hound.mcp.server`.

## Safety
Only automate sites you are authorized to automate.

## Setup
See [references/quickstart.md](references/quickstart.md), [references/tools.md](references/tools.md), and [templates/mcp-config.json](templates/mcp-config.json).
