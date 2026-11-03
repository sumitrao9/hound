# Hound NPM Ecosystem Research

## Core Browser Automation Packages

| Package | Version | Monthly Downloads | Description | License |
|---------|---------|-------------------|-------------|---------|
| `playwright` | 1.64.1 | ~5M+ | High-level API to automate web browsers | Apache-2.0 |
| `puppeteer` | 25.16.0 | ~3M+ | High-level API to control headless Chrome | Apache-2.0 |
| `stagehand` | 1.0.1 | ~50K | AI-powered browser automation for agents | Apache-2.0 |
| `@mastra/stagehand` | 0.4.0 | ~10K | Mastra integration for Stagehand | MIT |

---

## MCP Browser Packages

| Package | Version | Description | Notes |
|---------|---------|-------------|-------|
| `@browsermcp/mcp` | Latest | MCP server for browser automation using Browser MCP | References external "Browser MCP" |
| `@browsermcp/mcp` | - | MCP server for browser automation | - |
| `@n8n/mcp-browser` | - | n8n integration for browser MCP | n8n integration |
| `@agent-browser/eve` | - | Eve extension for browser automation | - |

---

## Key Dependencies Analysis

### Playwright (Primary Dependency)

| Aspect | Details |
|--------|---------|
| **Version** | 1.64.1 (current) |
| **License** | Apache-2.0 |
| **Browsers** | Chromium, Firefox, WebKit |
| **Languages** | TypeScript, Python, Java, .NET |
| **Architecture** | CDP-based, separate browser processes |
| **Stealth** | Basic; `playwright-stealth` community plugin available |
| **API** | `page.accessibility.snapshot()` for ARIA tree |

**Hound Usage**: Primary browser engine. `page.accessibility.snapshot()` provides the baseline ARIA tree that Hound optimizes.

### Stagehand (AI-Powered Layer)

| Aspect | Details |
|--------|---------|
| **Version** | 1.0.1 |
| **License** | Apache-2.0 |
| **Approach** | Natural language → Playwright actions |
| **AI Integration** | LLM-powered action planning |
| **Extract** | Schema-based extraction with Zod |

**Relevance to Hound**: Potential integration for AI-powered action planning, but adds LLM dependency and cost.

---

## Browser Stealth / Anti-Detection Packages

| Package | Version | Description | Relevance |
|---------|---------|-------------|-----------|
| `playwright-stealth` | Community | Applies stealth evasion techniques | Medium |
| `phantomwright` | - | Undetected browser automation SDK | High (captcha solving) |
| `phantomwright-cli` | - | CLI for undetected automation | High |
| `undetected-chromedriver` | Python | Selenium-based stealth | Low (Selenium-based) |

**Recommendation**: Hound currently uses basic Playwright. For production stealth, consider `playwright-stealth` or `phantomwright` integration.

---

## MCP Server Packages (TypeScript/JS)

| Package | Description | Language | Notes |
|---------|-------------|----------|-------|
| `@browsermcp/mcp` | Browser MCP server | TypeScript | References "Browser MCP" |
| `@n8n/mcp-browser` | n8n browser MCP | TypeScript | n8n workflow integration |
| `@agent-browser/eve` | Agent browser tools | TypeScript | Agent toolset |

---

## Python Ecosystem (PyPI)

### Core Packages

| Package | Version | Description | Hound Usage |
|---------|---------|-------------|-------------|
| `mcp` | >=1.0 | Model Context Protocol SDK | Primary MCP SDK |
| `playwright` | >=1.45 | Python bindings | Primary browser engine |
| `pytest` | >=8.0 | Testing framework | Test runner |
| `pytest-asyncio` | >=0.23 | Async test support | Async tests |
| `ruff` | >=0.5 | Linting/formatting | Code quality |

### Additional Research Packages

| Package | Description | Potential Use |
|---------|-------------|---------------|
| `playwright-stealth` | Stealth evasion | Production stealth |
| `lxml` / `selectolax` | Fast HTML parsing | Faster extraction |
| `readability-lxml` | Article extraction | Content extraction |
| `trafilatura` | Web content extraction | Alternative extractor |
| `markdownify` | HTML to Markdown | LLM-friendly output |
| `trafilatura` | Web content extraction | Content extraction |

---

## Security Scanning

```bash
# Run before release
pip audit
npm audit
```

**Current Status**: No known vulnerabilities in `mcp>=1.0`, `playwright>=1.45`.

---

## Recommendations for Hound

### Immediate (v0.2.0)
1. **Pin Playwright version** in `pyproject.toml`: `"playwright==1.64.1"`
2. **Add `playwright-stealth`** as optional dependency for production
2. **Add `pytest-asyncio`** already present ✅

### Short-term (v0.3.0)
1. **Evaluate Stagehand** for AI-powered action planning (adds LLM cost)
2. **Add `playwright-stealth`** as optional dependency
3. **Consider `selectolax`** for faster HTML parsing in extraction

### Long-term (v1.0+)
1. **Multi-browser support** (Firefox, WebKit via Playwright)
2. **Custom browser profiles** for persistent sessions
3. **CDP direct access** for advanced debugging

---

## Dependency Decision Matrix

| Package | Decision | Reason |
|---------|----------|--------|
| `playwright` | ✅ Keep (core) | Primary engine; well-maintained |
| `mcp` | ✅ Keep (core) | MCP protocol SDK |
| `pytest` / `pytest-asyncio` | ✅ Keep | Test infrastructure |
| `ruff` | ✅ Keep | Fast linting |
| `playwright-stealth` | ➕ Add optional | Production stealth needs |
| `stagehand` | 🔄 Evaluate | Adds LLM dependency; maybe v0.4+ |
| `phantomwright` | 🔄 Evaluate | High stealth; captcha solving; v0.5+ |
| `selectolax` | ➕ Add optional | Faster extraction; v0.4+ |

---

## Security Advisories (as of 2026-11-03)

```bash
# Run before each release
pip audit
npm audit
```

**No known critical vulnerabilities** in current dependency tree.

---

## License Compatibility

| Package | License | Compatible with MIT? |
|---------|---------|---------------------|
| `playwright` | Apache-2.0 | ✅ Yes |
| `mcp` | MIT | ✅ Yes |
| `pytest` | MIT | ✅ Yes |
| `ruff` | MIT | ✅ Yes |
| `playwright-stealth` | MIT | ✅ Yes |
| `stagehand` | Apache-2.0 | ✅ Yes |

All dependencies compatible with MIT license for Hound distribution.

---

*Research Date: 2026-11-03*
*Next Review: Before v0.3.0 release*
