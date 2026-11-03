# Hound Architecture Documentation

## Overview

Hound is a **token-budgeted, self-healing browser automation MCP server** that provides AI agents with browser control while dramatically reducing token consumption (~99.2% reduction vs full accessibility tree snapshots).

**Core Problem Solved**: Mainstream browser-automation MCP servers return the full accessibility tree on every action (~10,162 tokens/action, ~114,000 per 10-step flow). Hound reduces this to ~343 avg tokens/action (~2,744 per 10-step flow) — a **99.2% reduction**.

---

## Architecture Overview

```
hound/
├── core/           # Budget enforcement, element refs, delta computation
├── healing/        # Self-healing selector engine with verification
├── mcp/            # MCP server with 7-tool surface
├── bench/          # Reproducible benchmark harness
└── tests/          # 38 unit tests (no browser required)
```

---

## Core Components

### 1. Token Budget Engine (`hound/core/budget.py`)

**Purpose**: Enforce hard token ceilings on every tool response, auto-degrading to cheaper profiles when needed.

**Key Concepts**:
- **Profiles**: `MINIMAL` (confirmation only), `BALANCED` (interactive elements + capped text), `FULL` (everything, still budget-clipped)
- **Budget**: Hard token ceiling with automatic degradation (BALANCED → MINIMAL)
- **Estimation**: Character-count heuristic (~4 chars/token) for microsecond budget decisions
- **Degradation**: Progressive profile reduction (BALANCED → MINIMAL), never upgrades MINIMAL

**Key Classes**:
- `Profile` (Enum): MINIMAL, BALANCED, FULL
- `Budget`: max_tokens, profile, hard_fail flag
- `BudgetReport`: tokens_used, max_tokens, profile_effective, degraded, dropped_elements, truncated_text
- `fit_to_budget()`: Clamps payload to budget with progressive degradation

### 2. Stable Element References & Delta Snapshots (`hound/core/refs.py`)

**Purpose**: Assign stable references to elements and compute deltas between page states.

**Key Concepts**:
- **Element Identity**: `role|normalised_name` (excludes position & value for stability)
- **PageState**: url, title, text, elements[], signature (hash of structure + values)
- **Delta Diffing**: Only returns what changed (added/removed/changed elements)
- **Navigation Detection**: URL change voids all previous refs

**Key Classes**:
- `Element`: role, name, ref (e1, e2...), value, disabled, checked, selector
- `PageState`: url, title, text, elements[], signature
- `diff(previous, current)`: Returns navigated flag, added/removed/changed elements
- `signature_of()`: Fast hash for identical-page detection

### 3. Budgeted Browser Engine (`hound/core/engine.py`)

**Purpose**: Wraps Playwright, returns budgeted/diffed page state instead of raw snapshots.

**Key Features**:
- **BudgetedBrowser**: Main class wrapping Playwright page
- **Element References**: Stable `e1`, `e2` refs for agents
- **Delta Snapshots**: Returns only changes since last call
- **Self-Healing Integration**: Automatic selector repair on action failures
- **Human-Like Actions**: Bezier mouse curves, random delays

**Key Methods**:
- `goto(url)`: Navigate + full snapshot
- `snapshot(budget, delta)`: Returns diffed or full page state
- `act(action, target, value, budget)`: Click/fill/press/select with healing
- `verify(selector)`: Confirm element exists
- `_heal()`: Attempt verified selector repair

### 4. Self-Healing Selector Engine (`hound/healing/selectors.py`)

**Purpose**: Auto-repair broken selectors by scoring candidates on live DOM, adopting only after verification.

**Key Concepts**:
- **Candidate Generation**: Derives candidates from original selector attributes
- **Scoring**: Matches count, stability hints (test-id, aria-label), volatility penalties (css-, sc-, hash)
- **Verification**: Probes candidate matches, optionally verifies actionability
- **Persistence**: SQLite-backed store per site + logical key
- **Adoption Threshold**: Min confidence 0.55, requires verification

**Key Classes**:
- `SelectorCandidate`: selector, score, reason
- `HealingOutcome`: healed, original, selector, confidence, verified, detail, candidates
- `SelectorStore`: SQLite-backed per-site persistent overrides
- `heal()/heal_async()`: Core healing logic with probe/verify callbacks

### 5. MCP Server (`hound/mcp/server.py`)

**Purpose**: Exposes 7 focused tools via MCP protocol with explicit token budgets.

**7 Tools**:
1. `browser_open` - Navigate URL, return budgeted snapshot
2. `browser_snapshot` - Re-read page (delta by default)
3. `browser_act` - Click/fill/press/select with healing
4. `browser_find` - Locate elements by name/role (cheap, no full snapshot)
5. `browser_extract` - Structured extraction with confidence/verified flags
6. `browser_heal` - Repair broken selector, verify, remember per site
6. `browser_budget_report` - Session token spend report

**Design Principles**:
- Small tool surface (7 vs 50-90 in alternatives)
- Explicit `max_tokens` budget per tool
- Every response states what was verified
- Session spend tracking

---

## Data Flow

```
Agent Request (MCP) 
    → HoundServer._budget() → Budget(max_tokens, profile)
    → BudgetedBrowser method (goto/snapshot/act/find/extract/heal)
    → BudgetedBrowser._capture() → DOM_EXTRACTOR JS → PageState
    → fit_to_budget() → BudgetReport + payload
    → ActionResult → HoundServer._record() → spend tracking
    → MCP TextContent response with .render() one-line footer
```

---

## Key Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `HOUND_DB` | `hound-selectors.db` | SQLite DB for selector overrides |
| `HOUND_DEFAULT_BUDGET` | `1200` | Default token ceiling per response |
| `HOUND_MAX_BUDGET` | `20000` | Hard cap (caller cannot exceed) |
| `HOUND_HEADLESS` | `1` | Set to `0` to watch browser |

---

## Testing Strategy

| Test File | Scope |
|-----------|-------|
| `tests/test_budget_and_healing.py` | 38 tests: budget engine, delta/diff, healing, store persistence |
| (No live browser tests in CI) | Browser tests require network + Chromium |

Run: `pytest` (0.15s, no browser needed)

---

## Installation & Usage

```bash
# Install
pip install -e ".[dev]"
playwright install chromium

# Run as MCP server
hound-mcp

# MCP Client Config (Claude Desktop, Cursor)
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

---

## Benchmark

```bash
# Full benchmark (needs network + chromium)
python -m bench.run --url https://news.ycombinator.com

# Typical result: ~99.2% token reduction
# Conventional: ~114,000 tokens / 10-step flow
# Hound: ~2,744 tokens / 10-step flow
```
