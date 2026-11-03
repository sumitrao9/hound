# Hound Feature Inventory

## Overview
Complete inventory of Hound's existing features, mapped to implementation files and verification status.

---

## MCP Tools (7 Tools)

| Tool | File | Status | Description |
|------|------|--------|-------------|
| `browser_open` | `mcp/server.py:tool_open` | ✅ Working | Navigate URL, return budgeted snapshot |
| `browser_snapshot` | `mcp/server.py:tool_snapshot` | ✅ Working | Re-read page (delta by default) |
| `browser_act` | `mcp/server.py:tool_act` | ✅ Working | Click/fill/press/select with healing |
| `browser_find` | `mcp/server.py:tool_find` | ✅ Working | Locate elements by name/role (cheap) |
| `browser_extract` | `mcp/server.py:tool_extract` | ✅ Working | Structured extraction with confidence |
| `browser_heal` | `mcp/server.py:tool_heal` | ✅ Working | Repair broken selector, verify, persist |
| `browser_budget_report` | `mcp/server.py:tool_report` | ✅ Working | Session token spend report |

---

## Core Engine Features

### Budget Engine (`hound/core/budget.py`)

| Feature | Status | Test Coverage |
|---------|--------|---------------|
| Token estimation (char-count heuristic) | ✅ Implemented | ✅ `test_estimate_tokens_*` |
| Profile system (MINIMAL/BALANCED/FULL) | ✅ Implemented | ✅ `test_minimal_request_*` |
| Hard token budget enforcement | ✅ Implemented | ✅ `test_response_within_budget_*` |
| Automatic profile degradation (BALANCED→MINIMAL) | ✅ Implemented | ✅ `test_oversized_response_degrades_*` |
| MINIMAL never upgraded by degradation | ✅ Implemented | ✅ `test_minimal_request_is_never_upgraded` |
| Hard fail mode (BudgetExceeded) | ✅ Implemented | ✅ `test_hard_fail_raises_*` |
| Last-resort text/element trimming | ✅ Implemented | ✅ `test_last_resort_trims_*` |
| BudgetReport serialization/rendering | ✅ Implemented | ✅ `test_budget_report_serialises` |

### Element References & Delta (`hound/core/refs.py`)

| Feature | Status | Test Coverage |
|---------|--------|---------------|
| Stable element refs (e1, e2...) | ✅ Implemented | ✅ `test_refs_are_assigned_and_stable` |
| Element identity (role|name, excludes position/value) | ✅ Implemented | ✅ `test_identity_ignores_position` |
| PageState with signature hashing | ✅ Implemented | ✅ `test_signature_changes_*` |
| Delta diffing (added/removed/changed) | ✅ Implemented | ✅ `test_delta_reports_*` |
| Navigation detection (URL change voids refs) | ✅ Implemented | ✅ `test_navigation_is_flagged` |
| Identical page detection (signature match) | ✅ Implemented | ✅ `test_identical_pages_produce_empty_delta` |
| First snapshot = navigation | ✅ Implemented | ✅ `test_first_snapshot_is_treated_as_navigation` |
| Profile element caps (MINIMAL=0, BALANCED=60, FULL=400) | ✅ Implemented | ✅ `test_*_profile_*` |

### Budgeted Browser Engine (`hound/core/engine.py`)

| Feature | Status | Notes |
|---------|--------|-------|
| Playwright integration | ✅ Working | Chromium headless by default |
| Budgeted snapshots (full + delta) | ✅ Working | Delta by default |
| Stable element refs (e1, e2...) | ✅ Working | Assigned on capture |
| Click/fill/press/select actions | ✅ Working | With human-like delays |
| Self-healing on action failure | ✅ Working | Auto-generates candidates |
| Human-like mouse (Bezier curves) | ✅ Implemented | `_bezier_curve()` |
| Human-like delays | ✅ Implemented | `_human_delay()` |
| Verified selector repair | ✅ Working | `probe` + `verify` callbacks |
| Session spend tracking | ✅ Implemented | `self.spend` list |

### Self-Healing Selector Engine (`hound/healing/selectors.py`)

| Feature | Status | Test Coverage |
|---------|--------|---------------|
| Candidate generation from original selector | ✅ Working | ✅ `test_candidates_are_derived_*` |
| Includes aria-label, text, test-id | ✅ Working | ✅ `test_candidates_include_*` |
| Narrows from class chains to target tag | ✅ Working | ✅ `test_candidates_narrow_*` |
| Never includes original broken selector | ✅ Working | ✅ `test_candidates_never_include_original` |
| Volatility scoring (css-, sc-, hash penalties) | ✅ Working | ✅ `test_volatile_selectors_score_lower` |
| Non-unique matches score lower | ✅ Working | ✅ `test_non_unique_match_scores_lower` |
| Verified adoption (probe + verify) | ✅ Working | ✅ `test_heal_adopts_verified` |
| Refuses unverified adoption | ✅ Working | ✅ `test_heal_refuses_when_verification_fails` |
| Gives up when nothing matches | ✅ Working | ✅ `test_heal_gives_up_*` |
| Refuses low-confidence candidates | ✅ Working | ✅ `test_heal_refuses_low_confidence` |
| Explains failure when cannot heal | ✅ Working | ✅ `test_heal_explains_when_cannot` |
| Survives raising probe | ✅ Working | ✅ `test_heal_survives_raising_probe` |
| Persistent SQLite store per site | ✅ Working | ✅ `test_store_round_trips` |
| Hit/miss tracking | ✅ Working | ✅ `test_store_heal_increments_hits` |
| Marks unverified on repeat failure | ✅ Working | ✅ `test_store_marks_unverified_on_repeat` |
| Persists across instances | ✅ Working | ✅ `test_store_persists_across_instances` |

### Selector Store (`hound/healing/selectors.py:SelectorStore`)

| Feature | Status | Notes |
|---------|--------|-------|
| SQLite-backed persistence | ✅ Working | `hound-selectors.db` |
| Per-site overrides (site, logical_key) | ✅ Working | Composite PK |
| Healing log with audit trail | ✅ Working | `healing_log` table |
| Hit/miss counters | ✅ Working | Auto-increment |
| Concurrent access safe | ✅ Working | SQLite WAL mode |

---

## MCP Protocol Features

| Feature | Status | Implementation |
|---------|--------|----------------|
| 7 focused tools (not 50-90) | ✅ Working | `TOOLS` list in server.py |
| Explicit `max_tokens` per tool | ✅ Working | `budget_prop()` schema |
| Profile selection per tool | ✅ Working | `profile_prop()` schema |
| Session spend tracking | ✅ Working | `self.spend` list |
| Spend report with by-tool breakdown | ✅ Working | `tool_report()` |
| Selector stats in report | ✅ Working | `self.store.stats()` |
| Error responses with budget accounting | ✅ Working | `_failure()` counts tokens |
| Verified responses only | ✅ Working | Every tool states verification |

---

## Benchmark (`bench/run.py`)

| Feature | Status |
|---------|--------|
| Conventional vs Hound comparison | ✅ Working |
| Real ARIA snapshot baseline | ✅ Implemented |
| Scripted agent flow (8 steps) | ✅ Defined |
| Multi-page support | ✅ `--pages` flag |
| JSON output for CI | ✅ `--json` flag |

---

## Configuration

| Setting | Env Var | Default |
|---------|---------|---------|
| SQLite DB path | `HOUND_DB` | `hound-selectors.db` |
| Default token budget | `HOUND_DEFAULT_BUDGET` | 1200 |
| Max token budget (hard cap) | `HOUND_MAX_BUDGET` | 20000 |
| Headless mode | `HOUND_HEADLESS` | 1 (true) |

---

## Testing Status

| Test Suite | Tests | Status |
|------------|-------|--------|
| `test_budget_and_healing.py` | 38 | ✅ All Pass |

**Run**: `pytest` (0.15s, no browser required)

---

## Missing / Not Yet Implemented

| Feature | Status | Priority |
|---------|--------|----------|
| Live browser integration tests | ❌ Missing | High |
| Web search integration | ❌ Missing | Medium |
| Document extraction (PDF/OCR) | ❌ Missing | Medium |
| Web search APIs (Google, Bing) | ❌ Missing | Low |
| Crawler/batch mode | ❌ Missing | Low |
| Rate limiting / concurrency control | ❌ Missing | High |
| Caching layer | ❌ Missing | Medium |
| Prometheus/Grafana metrics | ❌ Missing | Low |
| Docker image / CI publish | ❌ Missing | Medium |
| Python package publishing (PyPI) | ❌ Missing | Medium |
| Official documentation site | ❌ Missing | Medium |
