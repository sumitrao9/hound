# Hound Python / PyPI Research

## Core Python Dependencies

| Package | Version Spec | Current | Purpose | License |
|---------|-------------|---------|---------|---------|
| `mcp` | >=1.0 | 1.x | Model Context Protocol SDK | MIT |
| `playwright` | >=1.45 | 1.64.1 | Browser automation engine | Apache-2.0 |
| `pytest` | >=8.0 | 8.x | Test framework | MIT |
| `pytest-asyncio` | >=0.23 | 0.23+ | Async test support | Apache-2.0 |
| `ruff` | >=0.5 | 0.5+ | Linting/formatting | MIT |

---

## Python Version Compatibility

| Python Version | Status | Notes |
|----------------|--------|-------|
| 3.10 | ✅ Supported | Minimum required |
| 3.11 | ✅ Supported | Recommended |
| 3.12 | ✅ Supported | Recommended |
| 3.13 | ✅ Supported | Latest |
| 3.14 | ✅ Supported | Current local |

**pyproject.toml**: `requires-python = ">=3.10"`

---

## FastAPI / Starlette Research (Alternative MCP Transport)

| Package | Version | Description | Relevance |
|---------|---------|-------------|-----------|
| `fastapi` | 0.115+ | Modern web framework | Alternative to stdio MCP |
| `uvicorn` | 0.30+ | ASGI server | For HTTP MCP transport |
| `starlette` | 0.38+ | ASGI toolkit | Base for FastAPI |
| `mcp[cli]` | - | MCP with HTTP transport | Alternative to stdio |

**Current Hound**: Uses stdio transport only (`stdio_server`)

---

## Browser Automation Python Ecosystem

### Playwright Python

| Aspect | Details |
|--------|---------|
| **Package** | `playwright` |
| **Version** | 1.64.1 |
| **Install** | `pip install playwright && playwright install` |
| **Browsers** | Chromium, Firefox, WebKit |
| **API** | Sync + Async |
| **CDP Access** | `page.context.new_cdp_session()` |

**Hound Usage**: Primary engine. Uses `page.accessibility.snapshot()` for ARIA tree.

### Alternative: Selenium

| Package | Version | Notes |
|---------|---------|-------|
| `selenium` | 4.x | Mature, slower, wider browser support |
| `undetected-chromedriver` | - | Stealth Chrome for Selenium |

**Verdict**: Playwright superior for Hound's use case (faster, better CDP, better async).

---

## MCP Python SDK (`mcp`)

| Aspect | Details |
|--------|---------|
| **Package** | `mcp` |
| **Version** | >=1.0 |
| **Transports** | stdio, HTTP (SSE), WebSocket |
| **Server** | `mcp.server.Server` |
| **Client** | `mcp.client.Client` |

**Hound Usage**: `mcp.server.Server` with `stdio_server` transport.

### FastMCP (Alternative)

| Package | Description |
|---------|-------------|
| `fastmcp` | FastAPI-style MCP server builder |
| **Status** | Community project; not official |

**Verdict**: Official `mcp` SDK sufficient for Hound's stdio transport.

---

## Async Patterns in Hound

### Current Patterns ✅

```python
# Proper async/await throughout
async def snapshot(self, budget: Budget, delta: bool = True) -> ActionResult:
    state = await self._capture()
    ...

# Proper async context managers
async with stdio_server() as (read_stream, write_stream):
    await server.run(...)
```

### Async Best Practices Used

| Pattern | Status |
|---------|--------|
| `async/await` consistency | ✅ |
| `async with` for resources | ✅ |
| `asyncio.gather` for parallelism | ✅ (in multi_discovery) |
| Proper exception handling | ✅ |
| No blocking calls in async | ✅ |

---

## Type Hints & Static Analysis

### Current Coverage

| Module | Type Hints | Coverage |
|--------|------------|----------|
| `budget.py` | ✅ Extensive | High |
| `refs.py` | ✅ Extensive | High |
| `engine.py` | ✅ Good | Medium-High |
| `selectors.py` | ✅ Good | Medium-High |
| `server.py` | ✅ Good | Medium |

### Tools Configured

| Tool | Config | Status |
|------|--------|--------|
| `ruff` | line-length=100, strict selects | ✅ |
| `mypy` | Not configured | ➕ Add |
| `pyright` | Not configured | ➕ Add |

**Recommendation**: Add `mypy` or `pyright` to CI for static type checking.

---

## Python Packaging (PyPI)

### Current Configuration (`pyproject.toml`)

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "hound-browser-mcp"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["mcp>=1.0", "playwright>=1.45"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.5", "build>=1.2", "twine>=5.0"]

[project.scripts]
hound-mcp = "hound.mcp.server:main"
hound-bench = "bench.run:cli"
```

### PyPI Publishing Checklist

| Step | Status |
|------|--------|
| Version bump | Manual |
| `pip install build twine` | ✅ In dev deps |
| `python -m build` | ➕ Test |
| `twine check dist/*` | ➕ Test |
| `twine upload dist/*` | ➕ Manual |
| GitHub Actions workflow | ➕ Add |

---

## Alternative Python Packages for Enhancement

### Document Processing

| Package | Purpose | Version | License |
|---------|---------|---------|---------|
| `pdfplumber` | PDF text/table extraction | 0.10+ | MIT |
| `pymupdf` (fitz) | Fast PDF processing | 1.23+ | AGPL |
| `pypdf` | Basic PDF reading | 3.17+ | BSD |
| `python-docx` | DOCX processing | 1.1+ | MIT |
| `markdownify` | HTML → Markdown | 0.12+ | MIT |
| `readability-lxml` | Article extraction | 0.8+ | Apache-2.0 |
| `trafilatura` | Web content extraction | 1.6+ | GPL-3.0 |

**Recommendation**: `pdfplumber` + `markdownify` for v0.4+ document extraction.

### HTML Parsing

| Package | Speed | License | Notes |
|---------|-------|---------|-------|
| `lxml` | Fast | BSD | C extension |
| `selectolax` | Very fast | MIT | Modest (C) |
| `beautifulsoup4` | Slow | MIT | Pure Python |
| `html5lib` | Standards-compliant | MIT | Slow |

**Recommendation**: `selectolax` for v0.4+ extraction speed.

### Structured Output / Validation

| Package | Purpose | License |
|---------|---------|---------|
| `pydantic` | Data validation | MIT |
| `pydantic-settings` | Settings management | MIT |
| `typeguard` | Runtime type checking | MIT |

---

## Testing Ecosystem

### Current

| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |

### Recommended Additions

| Package | Purpose | Priority |
|---------|---------|----------|
| `pytest-cov` | Coverage reporting | Medium |
| `pytest-xdist` | Parallel test execution | Low |
| `pytest-mock` | Mocking utilities | Low |
| `hypothesis` | Property-based testing | Low |

---

## CI/CD Python Tooling

### Recommended GitHub Actions

```yaml
# .github/workflows/ci.yml
- uses: actions/setup-python@v5
  with:
    python-version: '3.11'
- run: pip install -e ".[dev]"
- run: ruff check .
- run: mypy hound/  # Add mypy
- run: pytest
```

---

## Python Version Support Policy

| Version | Support Until | Hound Support |
|---------|---------------|---------------|
| 3.10 | 2026-10 | ✅ Minimum |
| 3.11 | 2027-10 | ✅ Recommended |
| 3.12 | 2028-10 | ✅ Recommended |
| 3.13 | 2029-10 | ✅ Current |
| 3.14 | 2030-10 | ✅ Current local |

**Recommendation**: Keep `>=3.10`, test on 3.10, 3.11, 3.12 in CI.

---

## Performance Profiling Tools

| Tool | Purpose |
|------|---------|
| `py-spy` | Sampling profiler |
| `pyinstrument` | Statistical profiler |
| `scalene` | CPU + memory profiler |
| `snakeviz` | Profile visualization |

**Recommended**: Add `py-spy` to dev dependencies for production profiling.

---

*Research Date: 2026-11-03*
*Next Review: Before v0.3.0 release*
