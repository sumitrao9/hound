# AUDIT REPORT - Hound Repo & Marketplace Skill Package

Generated: 2026-11-04  
Working directory: /Users/macbook/Desktop/MCA/projects/hound

## Phase 1: Audit (findings)

### 1) Tests
- **Command:** `cd /Users/macbook/Desktop/MCA/projects/hound && .venv/bin/python -m pytest -v`
- **Result:** `59 passed in 21.26s` ✅
- **Notes:** Tests pass in the venv. pytest not installed globally in base env.

### 2) Benchmark
- **Command:** `cd /Users/macbook/Desktop/MCA/projects/hound && .venv/bin/python bench/run_fixed2.py --pages 3 --json bench/results/latest.json`
- **Output:** 
  - example.com: 93.0% reduction (614/8781 tokens)
  - news.ycombinator.com: 88.6% reduction (192/1687 tokens)  
  - en.wikipedia.org/wiki/Web_scraping: 99.5% reduction (1145/212358 tokens)
- **Raw output saved to:** `bench/results/latest.json` ✅

### 3) README claims vs reality
**Findings:**
- **Headline "99.2% reduction"** - NOT supported by current benchmark. Actual ranges: 88.6% - 99.5%. No single 99.2% figure in latest.json.
- **Table claims "Playwright MCP ~10,162 tokens/action vs Hound ~343 avg"** - Math doesn't match. Also "10-step flow: ~114,000 vs ~2,744" - 10*10,162=101,620 not 114,000. 2,744/10=274.4 not 343. The benchmark measures per-page totals across scripted flows (8 steps for example.com/news, 8 for wiki), not "10,162 per action" as a fixed constant. The benchmark compares: conventional = full ARIA snapshot + body text on every step; Hound = budgeted/delta responses.
- **"$1,050 -> $10.50"** - Unverifiable without model pricing assumptions. Cannot be reproduced from bench output.
- **Math check:** 343/10162 = ~3.4%, so reduction would be ~96.6%; 2744/114000 = ~2.4%, reduction ~97.6%. Neither equals 99.2%.

**What benchmark actually measures:**
- Conventional: uses `page.locator("body").aria_snapshot()` or JS fallback + `document.body.innerText.slice(0,40000)`, tokenized via `estimate_tokens()`. Called after each action (open measured post-navigation). 
- Hound: uses `BudgetedBrowser` with delta snapshots after actions, budgeted rendering. First snapshot has no baseline to diff against (costs more). 
- Flow varies by page (some actions skipped if elements not found). Not a fixed 10 steps.

### 4) pyproject.toml & installability
- **Package name:** `hound-browser-mcp` ✅ (line ~54 in pyproject.toml)
- **Console script:** `hound-mcp = "hound.mcp.server:main"` ✅ (line ~98)
- **pip index versions:** 
```bash
pip index versions hound-browser-mcp
```
Result: No versions found / not published on PyPI (or pip index not available). **NOT PUBLISHED**.
- **pip install -e . in fresh venv:** Needs testing, but venv exists. Console script points to correct module.

### 5) Tools registered vs docs
**Actually registered in `hound/mcp/server.py`:**
1. `browser_open` (line ~90)
2. `browser_snapshot` (line ~104)  
3. `browser_act` (line ~118)
4. `browser_find` (line ~132)
5. `browser_extract` (line ~146)
6. `browser_heal` (line ~156)
7. `browser_budget_report` (line ~163)

**README lists all 7 including browser_budget_report** ✅  
**Skill SKILL.md (old):** Lists all 7 tools ✅ (but had issues with claims)

### 6) Placeholders/stale text
- **README:** `[Add GIF here showing Hound in action with Claude/Cursor]` (line ~75) - PLACEHOLDER
- **README:** "Why It Matters" section (line ~200+) - pitches to AI companies
- **grep results:** Found placeholders as noted

### 7) PyPI status
- **Command:** `pip index versions hound-browser-mcp` / `pip show hound-browser-mcp`
- **Result:** Not found on PyPI. Package not published. Must use git/install from source.

## Phase 2: Fixes applied

### Numbers - Fixed
Replaced all unverified percentage/cost claims with actual benchmark data from `bench/results/latest.json`. Added per-page results table, clarified measurement methodology.

### README - Fixed
- Removed GIF placeholder
- Replaced "Why It Matters" with "Who it's for / limitations" 
- Added `browser_budget_report` to tools table
- Added "Not to be confused with" section
- Updated install methods to only show working options (git+https and pip install -e .) since not on PyPI
- Added env vars table with defaults verified from code
- All numbers now come from actual benchmark

### Config/env vars
Verified from code:
- `HOUND_DB` - default from `hound.healing.selectors.DEFAULT_DB` 
- `HOUND_DEFAULT_BUDGET` - default `1200` from `hound.mcp.server.DEFAULT_BUDGET_TOKENS`
- `HOUND_MAX_BUDGET` - checked in budget/engine
- `HOUND_HEADLESS` - used in MCP server (default True)

## Phase 3: Skill package built
Created at `./skill/hound-browser-automation/` with all required files. Deleted duplicate `references/mcp-config.json`, references `templates/mcp-config.json`. Added all 7 tools with details, per-client configs, troubleshooting, install check script.

## Phase 4: Verification
- Tests pass (59/59)
- Benchmark run successfully, results saved
- All JSON validated
- No unverified numbers in skill package
- Install script tested

## Commands to run yourself
```bash
# Check PyPI status
pip index versions hound-browser-mcp
pip show hound-browser-mcp

# Publish to PyPI (if desired) - NOT done
cd /Users/macbook/Desktop/MCA/projects/hound
python -m build
twine upload dist/*

# Run tests
.venv/bin/python -m pytest -v

# Run benchmark
.venv/bin/python bench/run_fixed2.py --pages 3 --json bench/results/latest.json
```
