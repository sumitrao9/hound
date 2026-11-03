# Hound Product Roadmap

## Vision
Make Hound the **standard infrastructure** for AI agents that need browser control — reliable, token-efficient, and commercially viable.

---

## Current State (v0.1.0-beta)

| Metric | Value |
|--------|-------|
| Version | 0.1.0 |
| Tests | 38 passing |
| Core Features | Complete |
| Production Ready | Partial (see audit) |
| Commercial Interest | 1 agency (70/30 rev share) |

---

## Release Milestones

### v0.2.0 - "Production Hardening" (Week 1-2)
**Goal**: CI-passing, deployable, secure

| Task | Status | Owner |
|------|--------|-------|
| Live browser integration tests in CI | 🔄 Planned | |
| Rate limiting + semaphore | 🔄 Planned | |
| Request timeouts (network/element) | 🔄 Planned | |
| SSRF protection (URL validation) | 🔄 Planned | |
| Signal handlers (SIGTERM/SIGINT) | 🔄 Planned | |
| Structured logging (structlog) | 🔄 Planned | |
| Health check endpoint | 🔄 Planned | |

**Definition of Done**: All tests pass in CI including live browser tests; zero critical security findings.

---

### v0.3.0 - "Deployable" (Week 3-4)
**Goal**: One-command deploy anywhere

| Task | Status | Owner |
|------|--------|-------|
| Dockerfile + docker-compose.yml | 🔄 Planned | |
| PyPI publishing workflow | 🔄 Planned | |
| Version tagging + changelog | 🔄 Planned | |
| GitHub Actions CI/CD | 🔄 Planned | |
| README + INSTALLATION.md + CONFIGURATION.md | 🔄 Planned | |

**Definition of Done**: `docker run hound-browser-mcp` works; `pip install hound-browser-mcp` works.

---

### v0.4.0 - "Commercial Ready" (Month 2)
**Goal**: Agency/demo ready with monitoring

| Task | Status | Owner |
|------|--------|-------|
| Structured logging (JSON) | 🔄 Planned | |
| Prometheus metrics endpoint | 🔄 Planned | |
| Request/response logging | 🔄 Planned | |
| Error tracking (Sentry) | 🔄 Planned | |
| API key auth (optional) | 🔄 Planned | |
| Rate limit per API key | 🔄 Planned | |

---

### v1.0.0 - "Commercial Launch" (Month 3)
**Goal**: Revenue-generating product

| Task | Status | Owner |
|------|--------|-------|
| Documentation site (MkDocs) | 🔄 Planned | |
| MCP integration guide | 🔄 Planned | |
| Commercial license option | 🔄 Planned | |
| Agency pilot program | 🔄 Planned | |
| Pricing page / Stripe | 🔄 Planned | |

---

## Feature Backlog

### High Priority (Revenue Impact)

| Feature | Description | Effort | Revenue Impact |
|---------|-------------|--------|----------------|
| **Caching Layer** | Optional response cache for repeated URLs | Medium | Reduces cost, improves latency |
| **Concurrent Sessions** | Multiple browser contexts per process | High | Enables SaaS multi-tenancy |
| **Web Search Integration** | Discover URLs before browsing | Medium | Increases agent autonomy |
| **Document Extraction** | PDF/OCR/table extraction | Medium | New use cases (RAG, research) |

### Medium Priority (Product Quality)

| Feature | Description | Effort |
|---------|-------------|--------|
| Response Caching | In-memory + Redis optional | Medium |
| Multi-browser Support | Firefox, WebKit via Playwright | Medium |
| Session Recording | Video + trace export | Medium |
| Custom Selector Attributes | User-defined stable hints | Low |
| Batch/Bulk Operations | Queue multiple URLs | Medium |

### Research / Experimental

| Feature | Description | Effort |
|---------|-------------|--------|
| Vision-based Extraction | GPT-4V / LLaVA for complex pages | High |
| LLM-based Selector Healing | Use LLM to generate candidates | High |
| Agent-to-Agent Protocol | Hound-to-Hound coordination | High |
| Mobile Emulation | Viewport + touch simulation | Medium |

---

## Technical Debt Paydown

| Item | Target Version |
|------|----------------|
| Live browser CI tests | v0.2.0 |
| Rate limiting / timeouts | v0.2.0 |
| SSRF protection | v0.2.0 |
| Structured logging | v0.3.0 |
| Metrics endpoint | v0.4.0 |
| Request caching | v0.5.0 |
| Multi-tenancy | v0.6.0 |

---

## Commercial Milestones

| Milestone | Target | Criteria |
|-----------|--------|----------|
| **Agency Pilot** | Month 2 | 1 agency using in production |
| **First Revenue** | Month 3 | $1k MRR |
| **PyPI Downloads** | Month 3 | 100+/month |
| **GitHub Stars** | Month 3 | 50+ |
| **Case Study** | Month 4 | Published with agency |
| **$10k MRR** | Month 6 | 10+ paying customers |

---

## Resource Requirements

| Role | Current | Needed |
|------|---------|--------|
| Principal Engineer | 1 (you) | 1 |
| DevOps | 0 | 0.5 (contract) |
| Technical Writer | 0 | 0.25 (contract) |
| Security Review | 0 | 1 audit |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Playwright breaking changes | Medium | High | Pin version; test on release |
| MCP protocol changes | Low | High | Track MCP spec; abstract transport |
| Browser detection/blocking | High | High | Rotate UA; stealth plugins |
| Competitor launches free tier | Medium | Medium | Focus on token efficiency moat |
| MCP adoption stalls | Low | High | Diversify: REST API + MCP |

---

## Success Metrics

| Metric | Current | 3-Month Target | 6-Month Target |
|--------|---------|----------------|----------------|
| Test Pass Rate | 100% | 100% | 100% |
| CI Build Time | N/A | < 10 min | < 8 min |
| Token Reduction | 99.2% | 99.2% | 99.5% |
| Avg Response Time | ~2s | < 1.5s | < 1s |
| Crash Rate | Unknown | < 0.1% | < 0.01% |
| PyPI Downloads | 0 | 500/mo | 5,000/mo |
| GitHub Stars | 0 | 50 | 200 |
| Paying Customers | 0 | 1 | 10 |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-11-03 | Keep MIT license | Maximize adoption; commercial via support/hosting |
| 2026-11-03 | 7 tools max | Token efficiency for agent context |
| 2026-11-03 | SQLite for selector store | Zero-config, portable, sufficient scale |
| 2026-11-03 | No raw HTML to agent | Security + token budget |
