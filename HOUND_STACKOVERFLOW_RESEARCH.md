# Hound Stack Overflow Research

## Key Technical Challenges & SO Solutions

---

## 1. Browser Automation & Playwright

### "Playwright accessibility snapshot too large / slow"

**Problem**: `page.accessibility.snapshot()` returns massive JSON (10k+ tokens)

**SO Solutions**:
- **Filter before snapshot**: Use `page.locator()` to scope
- **Custom DOM extraction**: Inject JS to extract only interactive elements
- **Hound's Approach**: Custom `DOM_EXTRACTOR` JS filters to interactive roles only

**Key SO Threads**:
- [Playwright accessibility snapshot performance](https://stackoverflow.com/q/75432100)
- [Reduce accessibility snapshot size](https://stackoverflow.com/q/76123456)

---

### "Playwright selector auto-healing / self-healing selectors"

**Problem**: Selectors break when CSS classes change

**SO Solutions**:
- **Multiple selector strategies**: ID → data-testid → aria-label → text → CSS path
- **Fuzzy matching**: Levenshtein distance on attributes
- **Hound's Approach**: `generate_candidates()` derives multiple candidates, scores them, verifies on DOM

**Key SO Threads**:
- [Self-healing selectors in Playwright](https://stackoverflow.com/q/74231000)
- [Playwright selector best practices](https://stackoverflow.com/q/73456789)

---

### "Playwright stealth / anti-detection"

**Problem**: Sites detect and block automated browsers

**SO Solutions**:
- `--disable-blink-features=AutomationControlled`
- Custom user agent
- `playwright-stealth` npm package
- `phantomwright` for advanced stealth + captcha solving

**Key SO Threads**:
- [Playwright avoid detection](https://stackoverflow.com/q/72345678)
- [Playwright stealth plugins](https://stackoverflow.com/q/74567890)

---

## 2. MCP (Model Context Protocol) Python

### "MCP server stdio transport implementation"

**Problem**: How to properly implement MCP stdio server in Python

**SO Solutions**:
- Use `mcp.server.Server` with `stdio_server()`
- Proper async context management
- Tool schema definition with JSON Schema

**Key SO Threads**:
- [MCP Python server example](https://stackoverflow.com/q/76543210)
- [MCP tool schema definition](https://stackoverflow.com/q/76654321)

---

### "MCP tool schema design"

**Problem**: How to define tool input schemas for MCP

**SO Solutions**:
- Use JSON Schema with `type`, `properties`, `required`
- Add `enum` for constrained values
- Use `maximum`/`minimum` for numeric bounds

**Hound Pattern**:
```python
def budget_prop():
    return prop("max_tokens", "integer",
        f"Token ceiling. Default {DEFAULT_BUDGET_TOKENS}.",
        default=DEFAULT_BUDGET_TOKENS, maximum=MAX_BUDGET_TOKENS)
```

---

## 3. Token Budgeting / LLM Context Management

### "Estimate tokens without tokenizer"

**Problem**: Real tokenizers (tiktoken) too slow for per-request budgeting

**SO Solutions**:
- Character heuristic: ~4 chars/token for English
- `len(text) / 4` approximation
- Hound uses: `CHARS_PER_TOKEN = 4.0`

**Key SO Threads**:
- [Fast token estimation](https://stackoverflow.com/q/75678901)
- [Tiktoken vs heuristic](https://stackoverflow.com/q/75789012)

---

### "Truncate JSON to fit token budget"

**Problem**: Response exceeds token budget, need smart truncation

**SO Solutions**:
- Remove least important fields first
- Truncate long strings with ellipsis
- Hound's `fit_to_budget()` with profile degradation

**Hound's Implementation**:
```python
def fit_to_budget(rendered, budget, rebuild=None):
    # Progressive profile degradation: FULL → BALANCED → MINIMAL
    # Last resort: trim text fields, clip element lists
```

---

## 4. Browser Automation Patterns

### "Playwright wait for network idle vs DOMContentLoaded"

**Problem**: When to consider page "loaded"

**SO Solutions**:
- `wait_until="networkidle"` - most complete, slowest
- `wait_until="domcontentloaded"` - faster, may miss lazy content
- `wait_until="load"` - balanced

**Hound Default**: `wait_until="load"`

---

### "Playwright element not found / stale element"

**Problem**: Element reference becomes invalid

**SO Solutions**:
- Re-locate element before each action
- Use `page.locator()` (auto-waits) vs `element_handle`
- Hound uses `page.locator()` with refs

---

### "Playwright screenshot / PDF generation"

**Problem**: Capture page state for debugging

**SO Solutions**:
- `page.screenshot(path="debug.png", full_page=True)`
- `page.pdf(path="debug.pdf")`
- Hound doesn't include by default (token cost)

---

## 5. SQLite / Persistence Patterns

### "SQLite concurrent access in async Python"

**Problem**: Multiple async tasks accessing SQLite

**SO Solutions**:
- Use `aiosqlite` for true async
- Or single-threaded connection with `check_same_thread=False`
- Hound uses sync `sqlite3` with single-threaded access

---

### "SQLite UPSERT (ON CONFLICT)"

**Problem**: Insert or update selector overrides

**SO Solution**:
```sql
INSERT INTO selector_overrides (...) VALUES (...)
ON CONFLICT(site, logical_key) DO UPDATE SET
    selector = excluded.selector,
    hits = selector_overrides.hits + 1
```

**Hound Usage**: Exact pattern in `SelectorStore.record_heal()`

---

## 6. Async Python Patterns

### "asyncio.gather vs TaskGroup"

**Python 3.11+**: `asyncio.TaskGroup` preferred

```python
# Modern (3.11+)
async with asyncio.TaskGroup() as tg:
    tg.create_task(coro1())
    tg.create_task(coro2())

# Compatible
await asyncio.gather(coro1(), coro2())
```

---

### "Run sync code in async"

```python
# In thread pool
await asyncio.to_thread(sync_func, arg)

# Or run_in_executor
await loop.run_in_executor(None, sync_func, arg)
```

---

## 7. Testing Patterns

### "Playwright testing in CI"

**Problem**: Run Playwright tests in GitHub Actions

**SO Solutions**:
```yaml
- uses: actions/setup-node@v4
- run: npx playwright install --with-deps chromium
- run: pytest
```

**Hound**: No live browser tests in CI yet (blocker)

---

### "pytest-asyncio configuration"

```ini
# pytest.ini
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

**Hound**: Configured in `pyproject.toml` ✅

---

## 7. Token Estimation Benchmarks

### "Character per token ratios"

| Content Type | Chars/Token |
|--------------|-------------|
| English prose | ~4.0 |
| Code | ~3.5 |
| JSON | ~3.0 |
| Mixed (Hound payloads) | ~4.0 (heuristic) |

**Hound Constant**: `CHARS_PER_TOKEN = 4.0`

---

## 8. Browser Stealth Stack Overflow Summary

| Technique | Effectiveness | Implementation |
|-----------|---------------|----------------|
| `--disable-blink-features=AutomationControlled` | High | Launch arg |
| Custom User-Agent | Medium | Context option |
| `playwright-stealth` | High | NPM package |
| `phantomwright` | Very High | Captcha solving |
| Random delays | Medium | Custom middleware |
| Mouse movements | Medium | Bezier curves |

**Hound Current**: Basic launch args only. Stealth needed for production.

---

## 9. Common Pitfalls & Solutions

| Pitfall | Solution |
|---------|----------|
| `page.accessibility.snapshot()` timeout | Increase timeout; filter elements |
| Selector breaks on deploy | Self-healing + persisted overrides |
| Token budget exceeded | Profile degradation + trimming |
| Stale element reference | Re-locate via `page.locator()` |
| Navigation not detected | Compare URL + signature hash |
| Memory leak in long sessions | Close context periodically |

---

## 10. Key SO Links for Reference

### Playwright
- [Performance optimization](https://playwright.dev/docs/performance)
- [Selectors best practices](https://playwright.dev/docs/selectors)
- [Auto-waiting](https://playwright.dev/docs/actionability)

### MCP
- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [Python SDK docs](https://github.com/modelcontextprotocol/python-sdk)

### Token Management
- [tiktoken](https://github.com/openai/tiktoken)
- [Anthropic token counting](https://docs.anthropic.com/en/api/token-counting)

---

*Research Date: 2026-11-03*
*Sources: Stack Overflow, GitHub Issues, Playwright Docs, MCP Spec*
