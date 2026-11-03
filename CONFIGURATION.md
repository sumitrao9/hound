# Hound Configuration Guide

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOUND_DB` | `hound-selectors.db` | SQLite database path for selector overrides |
| `HOUND_DEFAULT_BUDGET` | `1200` | Default token ceiling per response |
| `HOUND_MAX_BUDGET` | `20000` | Hard ceiling (cannot be exceeded by callers) |
| `HOUND_HEADLESS` | `1` | Set to `0` to run headed (visible browser) |

## Budget Configuration

### Default Budget

The default budget of 1200 tokens balances detail with cost. Adjust based on your use case:

- **Low budget (500-800)**: Minimal responses, fastest
- **Default (1200)**: Balanced detail and cost
- **High budget (2000-5000)**: More detail, higher cost

### Profile System

| Profile | Max Elements | Text Allowance | Use Case |
|---------|--------------|----------------|----------|
| `minimal` | 0 | 0 chars | Click confirmation only |
| `balanced` | 60 | 2,000 chars | Default - interactive elements + text |
| `full` | 400 | 40,000 chars | Maximum detail |

### Per-Tool Budget Override

Each MCP tool accepts `max_tokens` and `profile` parameters:

```json
{
  "max_tokens": 800,
  "profile": "minimal"
}
```

---

## Selector Store Configuration

### Database Location

Default: `hound-selectors.db` in working directory

Override with `HOUND_DB`:
```bash
export HOUND_DB=/path/to/custom-selectors.db
```

### Database Schema

```sql
-- Selector overrides (per site + logical key)
CREATE TABLE selector_overrides (
    site TEXT NOT NULL,
    logical_key TEXT NOT NULL,
    selector TEXT NOT NULL,
    original TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    verified INTEGER DEFAULT 0,
    hits INTEGER DEFAULT 0,
    misses INTEGER DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (site, logical_key)
);

-- Healing audit log
CREATE TABLE healing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    logical_key TEXT NOT NULL,
    original TEXT NOT NULL,
    replacement TEXT,
    verified INTEGER NOT NULL,
    confidence REAL NOT NULL,
    created_at REAL NOT NULL
);
```

---

## Browser Configuration

### Headless Mode

```bash
# Headless (default, production)
export HOUND_HEADLESS=1

# Headed (debugging)
export HOUND_HEADLESS=0
```

### Browser Launch Arguments

Default arguments (in `engine.py`):
- `--no-sandbox`
- `--disable-blink-features=AutomationControlled`
- `--disable-web-security`
- `--disable-features=IsolateOrigins,site-per-process`

### Viewport

Default: 1366x768

Custom viewport (via MCP tool args):
```json
{
  "viewport": {"width": 1920, "height": 1080}
}
```

---

## Rate Limiting

Configure in code (BudgetedBrowser constructor):

```python
from hound.core.engine import RateLimiter

# 30 requests per 60 seconds
rate_limiter = RateLimiter(max_requests=30, window_seconds=60)

engine = BudgetedBrowser(page, store, budget, rate_limiter=rate_limiter)
```

---

## Timeouts

Configure in code (BudgetedBrowser constructor):

```python
from hound.core.engine import TimeoutConfig

timeouts = TimeoutConfig(
    navigation=30.0,      # Page navigation
    element_action=10.0,  # Click, fill, etc.
    selector_wait=5.0,    # Wait for selector
    snapshot=10.0,        # Page capture
    healing=15.0          # Selector healing
)

engine = BudgetedBrowser(page, store, budget, timeouts=timeouts)
```

---

## MCP Client Configuration

### Claude Desktop

```json
{
  "mcpServers": {
    "hound": {
      "command": "hound-mcp",
      "env": {
        "HOUND_DEFAULT_BUDGET": "1200",
        "HOUND_HEADLESS": "1",
        "HOUND_DB": "/path/to/hound-selectors.db"
      }
    }
  }
}
```

### Cursor

```json
{
  "mcp": {
    "servers": {
      "hound": {
        "command": "hound-mcp",
        "env": {
          "HOUND_DEFAULT_BUDGET": "1200"
        }
      }
    }
  }
}
```

### Custom Stdio Client

```python
from mcp.client.stdio import stdio_client

async with stdio_client(["hound-mcp"]) as (read, write):
    client = Client(read, write)
    result = await client.call_tool("browser_open", {"url": "https://example.com"})
```

---

## Docker Configuration

### Environment Variables

```yaml
environment:
  - HOUND_HEADLESS=1
  - HOUND_DEFAULT_BUDGET=1200
  - HOUND_MAX_BUDGET=20000
  - HOUND_DB=/data/hound-selectors.db
```

### Volumes

```yaml
volumes:
  - hound-data:/data
```

### Run Command

```bash
# Stdio transport (for MCP clients)
docker run -i --rm hound-browser-mcp

# With custom config
docker run -i --rm \
  -e HOUND_DEFAULT_BUDGET=800 \
  -v $(pwd)/data:/data \
  hound-browser-mcp
```

---

## Advanced Configuration

### Custom Selector Hints

Add stable attribute hints in `healing/selectors.py`:

```python
_STABLE_HINTS = (
    "testid",
    "test-id",
    "data-qa",
    "data-cy",
    "aria-label",
    "role",
    "name",
    "id",
    "title",
    "placeholder",
    "alt",
    "href",
    # Add your custom attributes here
    "data-cy",
    "data-test",
)
```

### Volatile Hint Patterns

```python
_VOLATILE_HINTS = (
    "css-",
    "sc-",
    "jsx-",
    "emotion",
    "styled",
    "random",
    "uuid",
    "hash",
    "generated",
    "btn-",
    "col-",
    "row-",
    # Add your framework's volatile patterns
)
```

---

## Security Configuration

### URL Validation

Blocked by default:
- `localhost`, `127.0.0.1`, `::1`
- Private IP ranges (10.x, 192.168.x, 172.16-31.x)
- Metadata endpoints (169.254.169.254)

### Allowed Schemes

Only `http` and `https` allowed.

### Custom Allowlist

Modify `validate_url()` in `engine.py` for custom allow/block lists.

---

## Performance Tuning

### Budget Tuning

| Use Case | Budget | Profile |
|----------|--------|---------|
| Simple clicks | 500 | minimal |
| Form filling | 800 | balanced |
| Data extraction | 2000 | balanced |
| Full page analysis | 5000 | full |

### Concurrency

For concurrent sessions, create separate `BudgetedBrowser` instances with shared `SelectorStore`:

```python
store = SelectorStore("shared-selectors.db")
engine1 = BudgetedBrowser(page1, store, budget)
engine2 = BudgetedBrowser(page2, store, budget)
```

---

## Debugging

### Enable Debug Logging

```bash
export PYTHONPATH=/path/to/hound
export LOG_LEVEL=DEBUG
```

### Inspect Selector Store

```bash
sqlite3 hound-selectors.db "SELECT * FROM selector_overrides;"
sqlite3 hound-selectors.db "SELECT * FROM healing_log;"
```

### Budget Report

Call `browser_budget_report` tool:
```json
{
  "total_tokens": 15420,
  "calls": 12,
  "average_tokens": 1285,
  "by_tool": [...],
  "selectors": {...}
}
```
