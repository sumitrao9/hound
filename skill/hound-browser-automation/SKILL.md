---
name: hound-browser-automation
description: Token-budgeted, self-healing browser automation via the Hound MCP server. Use when you need to browse, click, fill forms, or extract data with minimal context cost using budgeted/delta snapshots and automatic selector healing.
version: 1.0.0
---

# Hound Browser Automation

## When to use Hound vs a full-tree browser MCP
- **Use Hound** when doing multi-step flows and you want only changed elements returned (delta snapshots). Good for long sessions where context cost matters.
- **Use a full-tree browser MCP** when you need a complete, untruncated view of the page on every call, or for simple one-off dumps where delta tracking isn't needed.
- **Note:** First snapshot has no baseline to diff against. With budgeting, you may not see everything - use `browser_find` or `browser_extract` for targeted info.

## Prerequisites
Hound is **not currently on PyPI**. Install from source.

## Workflow: open -> act -> snapshot(delta) -> extract -> heal
1. **Open**: `browser_open` with URL. Get budgeted snapshot.
2. **Act**: Use `browser_act` with refs from snapshot or selectors.
3. **Snapshot**: After actions/navigation, use `browser_snapshot` (delta) to get only changes.
4. **Extract**: Use `browser_extract` with a target/schema for structured data.
5. **Heal**: If a selector fails, use `browser_heal` with selector and logical_key; Hound will verify and remember repairs.

## Tools (all 7)
| Tool | Purpose | Key params |
|---|---|---|
| `browser_open` | Navigate and get budgeted snapshot | `url` |
| `browser_snapshot` | Re-read page, return only changes if possible | (uses session) |
| `browser_act` | Click/fill/press/select | `action`, `selector` or ref, `value` (for fill) |
| `browser_find` | Locate elements without full snapshot | `query`/criteria |
| `browser_extract` | Structured extraction with confidence/verified | `target`, schema hints |
| `browser_heal` | Repair broken selector, verify, remember | `selector`, `logical_key` |
| `browser_budget_report` | Session token spend by tool | - |

## Environment variables
| Variable | Default | Notes |
| --- | --- | --- |
| `HOUND_DB` | OS default (see repo) | Learned selectors DB |
| `HOUND_DEFAULT_BUDGET` | `1200` | Token budget |
| `HOUND_MAX_BUDGET` | (engine) | Max budget |
| `HOUND_HEADLESS` | `1` | Headless mode |

## Not the web-research Hound
**PyPI package `hound-mcp` is a different project** (web research, command `hound`). This is **`hound-browser-mcp`** with command **`hound-mcp`** (same command name exists for different project - check which is installed). Repo: https://github.com/sumitrao9/hound

## Safety
You must only automate sites you are allowed to automate.

## Setup
See [references/quickstart.md](references/quickstart.md) and [templates/mcp-config.json](templates/mcp-config.json).
