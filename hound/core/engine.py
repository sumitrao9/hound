"""The budgeted browser engine - Hound's Original Implementation.

Wraps Playwright and returns budgeted, referable, diffed page state instead of
raw snapshots. Playwright is an implementation detail here - the contract this
module exposes is what the MCP layer and the hosted API both depend on.

Hound's Original Innovations Integrated:
- AdaptiveBudget: Learns optimal budgets per site/action
- SemanticDiffer: Understands semantic meaning of page changes
- PredictiveHealer: ML-style explainable selector healing
- SessionTokenOptimizer: Cross-action token optimization
- CrossSiteKnowledgeBase: Transfers selector learnings across sites
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlparse
from collections import defaultdict

from hound.core.budget import Budget, BudgetReport, Profile, estimate_tokens, fit_to_budget
from hound.core.refs import PageState, build_state, diff
from hound.healing.selectors import (
    HealingOutcome,
    SelectorStore,
    generate_candidates,
    heal_async,
)
from hound.core.innovations import (
    AdaptiveBudget,
    SemanticDiffer,
    PredictiveHealer,
    SessionTokenOptimizer,
    CrossSiteKnowledgeBase,
    SemanticChange,
    PredictiveHealResult,
)

_log = logging.getLogger(__name__)

# ============================================================================
# HOUND ORIGINAL: Security-First URL Validation
# ============================================================================

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOST_PREFIXES = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "10.",
    "192.168.",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.",
    "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "::1",
    "fe80::",
)

# Metadata endpoints that should never be accessed
BLOCKED_HOSTNAMES = {
    "169.254.169.254",      # AWS metadata
    "metadata.google.internal",  # GCP metadata
    "metadata.azure.com",     # Azure metadata
    "metadata",               # Generic
}

def validate_url(url: str) -> tuple[bool, str]:
    """Hound Original: Comprehensive URL validation with SSRF protection."""
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL: {e}"

    if parsed.scheme not in ALLOWED_SCHEMES:
        return False, f"Scheme '{parsed.scheme}' not allowed (only http/https)"

    hostname = parsed.hostname or ""
    if not hostname:
        return False, "No hostname"

    # Block known metadata endpoints
    if hostname in BLOCKED_HOSTNAMES:
        return False, f"Metadata endpoint '{hostname}' blocked"

    # Block localhost and common local hostnames
    if hostname in ("localhost", "localhost.localdomain", "localhost6", "localhost6.localdomain6"):
        return False, f"Localhost '{hostname}' blocked"

    # Block private IP ranges
    for prefix in ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
                   "172.20.", "172.21.", "172.22.", "172.22.", "172.23.",
                   "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
                   "172.28.", "172.29.", "172.30.", "172.31.",
                   "192.168.", "10.", "127.", "0.0.0.0", "::1", "fe80::"):
        if hostname.startswith(prefix):
            return False, f"Private/internal address '{hostname}' blocked"

    return True, "OK"


# ============================================================================
# HOUND ORIGINAL: Rate Limiter with Adaptive Windows
# ============================================================================

class RateLimiter:
    """Hound Original: Token bucket with adaptive windows based on site behavior."""
    
    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: list[float] = []
        self._lock = asyncio.Lock()
        self.site_limits: dict[str, tuple[int, float]] = {}  # site -> (max_req, window)

    def set_site_limit(self, site: str, max_requests: int, window_seconds: float):
        """Set custom rate limit for a specific site."""
        self.site_limits[site] = (max_requests, window_seconds)

    async def acquire(self, site: str = "default") -> None:
        async with self._lock:
            now = time.monotonic()
            max_req, window = self.site_limits.get(site, (self.max_requests, self.window_seconds))
            
            # Remove old requests outside window
            cutoff = now - window
            self.requests = [t for t in self.requests if t > cutoff]

            if len(self.requests) >= max_req:
                wait_time = self.requests[0] + window - time.monotonic()
                if wait_time > 0:
                    _log.debug("Rate limited for %s, waiting %.2fs", site, wait_time)
                    await asyncio.sleep(wait_time)
                now = time.monotonic()
                self.requests = [t for t in self.requests if t > now - window]

            self.requests.append(time.monotonic())


# ============================================================================
# Timeouts Configuration
# ============================================================================

@dataclass
class TimeoutConfig:
    """Configurable timeouts for browser operations."""
    navigation: float = 30.0
    element_action: float = 10.0
    selector_wait: float = 5.0
    snapshot: float = 10.0
    healing: float = 15.0


# ============================================================================
# HOUND ORIGINAL: Core Browser Engine with All Innovations
# ============================================================================

COUNT_CANDIDATES_JS = """
(sel) => {
  const out = {};
  for (const s of sel) {
    try { out[s] = document.querySelectorAll(s).length; }
    catch (e) { out[s] = 0; }
  }
  return out;
}
"""

DOM_EXTRACTOR = """
() => {
  const INTERACTIVE = new Set(['button','link','textbox','searchbox','combobox','checkbox',
    'radio','menuitem','tab','option','switch','slider','spinbutton']);
  const KEEP = new Set(['button','link','textbox','searchbox','combobox','checkbox','radio',
    'menuitem','tab','option','switch','slider','spinbutton','heading','alert','dialog',
    'status','form','navigation','main','list','listitem','img','table','row','cell']);

  const nameOf = (el) => (
    el.getAttribute('aria-label')
    || (el.getAttribute('aria-labelledby')
        ? (document.getElementById(el.getAttribute('aria-labelledby'))?.textContent || '').trim()
        : '')
    || el.innerText
    || el.getAttribute('title')
    || el.getAttribute('placeholder')
    || el.getAttribute('alt')
    || ''
  ).replace(/\\s+/g, ' ').trim().slice(0, 200);

  const roleOf = (el) => (
    el.getAttribute('role')
    || (el.tagName === 'A' && el.hasAttribute('href') ? 'link' : '')
    || (el.tagName === 'BUTTON' ? 'button' : '')
    || (el.tagName === 'INPUT' ? ({text:'textbox',search:'searchbox',checkbox:'checkbox',
        radio:'radio',submit:'button',button:'button',range:'slider',number:'spinbutton'})[
        (el.getAttribute('type')||'text').toLowerCase()] || 'textbox' : '')
    || (el.tagName === 'TEXTAREA' ? 'textbox' : '')
    || (el.tagName === 'SELECT' ? 'combobox' : '')
    || (/^h[1-6]$/i.test(el.tagName) ? 'heading' : '')
    || (el.tagName === 'IMG' ? 'img' : '')
    || ''
  ).toLowerCase();

  const pathOf = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    let node = el;
    let depth = 0;
    while (node && node.nodeType === 1 && depth < 4) {
      let part = node.tagName.toLowerCase();
      if (node.id) { parts.unshift('#' + CSS.escape(node.id)); break; }
      const cls = (node.getAttribute('class') || '').split(/\\s+/)
        .filter(c => c && !/^(ng|css|sc)-/.test(c) && c.length < 40).slice(0, 2);
      if (cls.length) part += '.' + cls.map(c => CSS.escape(c)).join('.');
      parts.unshift(part);
      node = node.parentElement;
      depth++;
    }
    return parts.join(' > ');
  };

  const nodes = Array.from(document.querySelectorAll('*'));
  const elements = [];
  for (const el of nodes) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;

    const tag = el.tagName.toLowerCase();
    const role = roleOf(el);
    const testid = el.getAttribute('data-testid') || el.getAttribute('data-qa');
    const isFormField = ['input','select','textarea'].includes(tag);
    if (!role && !testid) continue;
    if (!KEEP.has(role) && !testid && !isFormField) continue;
    if (INTERACTIVE.size && !INTERACTIVE.has(role) && role !== 'heading' && !testid) {
      continue;
    }

    const name = nameOf(el);
    const selector = pathOf(el);
    const value = (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')
      ? (el.value || '').slice(0, 200)
      : '';
    const disabled = el.disabled || false;
    const checked = el.checked === true ? true : (el.checked === false ? false : null);

    elements.push({
      role, name, selector, value, disabled, checked,
      tag, testid: testid || null
    });
  }
  return { elements };
}
"""


def _bezier_curve(x0, y0, x1, y1, cpx, cpy, steps=12):
    pts = []
    for i in range(steps):
        t = i / max(steps - 1, 1)
        mt = 1 - t
        bx = mt*mt*mt*x0 + 3*mt*mt*t*cpx + 3*mt*t*t*x1 + t*t*t*x1
        by = mt*mt*mt*y0 + 3*mt*mt*t*cpy + 3*mt*t*t*y1 + t*t*t*y1
        pts.append((bx, by))
    return pts


def _human_delay(min_ms=30, max_ms=120):
    return random.uniform(min_ms, max_ms) / 1000.0


class HumanMouse:
    """Hound Original: Bezier curve mouse movement with human-like timing."""
    
    def __init__(self, page):
        self.page = page

    async def move_to(self, x, y, clicks=False, button='left'):
        dx = abs(x - (self.page.viewport_size.get('width', 1280) / 2)) if False else random.randint(50, 200)
        dy = random.randint(-100, 100)
        cpx = (x + dx) / 2 + random.uniform(-50, 50)
        cpy = (y + dy) / 2 + random.uniform(-30, 30)
        steps = random.randint(10, 20)
        start_x, start_y = x / 2, y / 2
        curve = _bezier_curve(start_x, start_y, x, y, cpx, cpy, steps)
        for cx, cy in curve:
            await self.page.mouse.move(cx, cy)
            await asyncio.sleep(_human_delay(10, 20))
        if clicks:
            await self.page.mouse.down(button=button)
            await asyncio.sleep(_human_delay(20, 60))
            await self.page.mouse.up(button=button)
        return True


@dataclass
class ActionResult:
    ok: bool
    data: dict[str, Any]
    report: BudgetReport
    healed: list = field(default_factory=list)
    semantic_changes: list = field(default_factory=list)  # Hound Original
    duration_ms: int = 0

    def render(self) -> str:
        parts = [f"ok={self.ok}"]
        if self.healed:
            parts.append(f"healed={len(self.healed)}")
        if self.semantic_changes:
            parts.append(f"semantic_changes={len(self.semantic_changes)}")
        if self.duration_ms:
            parts.append(f"{self.duration_ms}ms")
        parts.append(self.report.render())
        return " | ".join(parts)


class BudgetedBrowser:
    """
    Hound's Original Budgeted Browser Engine.
    
    Integrates all Hound's original innovations:
    - AdaptiveBudget: Learns optimal budgets per site/action
    - SemanticDiffer: Understands semantic meaning of changes
    - PredictiveHealer: ML-style explainable selector healing
    - SessionTokenOptimizer: Cross-action token optimization
    - CrossSiteKnowledgeBase: Transfers learnings across sites
    """

    def __init__(
        self,
        page,
        store: SelectorStore,
        default_budget: Budget,
        rate_limiter: Optional[RateLimiter] = None,
        timeouts: Optional[TimeoutConfig] = None,
        enable_innovations: bool = True,
    ):
        self.page = page
        self.store = store
        self.default_budget = default_budget
        self.rate_limiter = rate_limiter or RateLimiter()
        self.timeouts = timeouts or TimeoutConfig()
        self.enable_innovations = enable_innovations
        
        # Hound Original Innovations
        if enable_innovations:
            self.adaptive_budget = AdaptiveBudget(default_budget.max_tokens, default_budget.profile)
            self.semantic_differ = SemanticDiffer()
            self.predictive_healer = PredictiveHealer(store)
            self.token_optimizer = SessionTokenOptimizer()
            self.cross_site_kb = CrossSiteKnowledgeBase()
        else:
            self.adaptive_budget = None
            self.semantic_differ = None
            self.predictive_healer = None
            self.token_optimizer = None
            self.cross_site_kb = None
        
        self._previous: Optional[PageState] = None
        self._session_spend: list[dict[str, Any]] = []
        self._closed = False

    async def _rate_limit(self, site: str = "default") -> None:
        await self.rate_limiter.acquire(site)

    async def _validate_and_goto(self, url: str, **kwargs) -> None:
        ok, msg = validate_url(url)
        if not ok:
            raise ValueError(f"URL validation failed: {msg}")
        await asyncio.wait_for(
            self.page.goto(url, **kwargs),
            timeout=self.timeouts.navigation
        )

    async def _capture(self) -> PageState:
        raw = await self.page.evaluate(DOM_EXTRACTOR)
        title = await self.page.title()
        text = await self.page.evaluate("() => document.body?.innerText || ''")
        elements = raw.get("elements", []) if isinstance(raw, dict) else []
        return build_state(self.page.url, title, text, elements)

    async def snapshot(
        self,
        budget: Budget,
        delta: bool = True,
    ) -> ActionResult:
        """Return a budgeted page snapshot with semantic diff."""
        started = time.perf_counter()
        await self._rate_limit(_site_of(self.page.url))

        try:
            state = await asyncio.wait_for(
                self._capture(),
                timeout=self.timeouts.snapshot
            )
        except asyncio.TimeoutError:
            return self._failure({"error": "snapshot timeout"}, budget, started)

        # Hound Original: Semantic diff
        semantic_changes = []
        if self.semantic_differ:
            semantic_changes = self.semantic_differ.compute_semantic_diff(
                self._previous if delta else None, 
                state
            )

        if delta and self._previous is not None:
            diff_result = diff(self._previous, state)
            payload = diff_result
        else:
            payload = state.render(budget.profile)

        self._previous = state

        rebuilt, report = fit_to_budget(payload, budget)
        report.tokens_used = estimate_tokens(rebuilt)
        duration_ms = int((time.perf_counter() - started) * 1000)

        site = _site_of(self.page.url)
        self._session_spend.append({
            "tool": "snapshot",
            "tokens": report.tokens_used,
            "profile": report.profile_effective.value,
            "ms": duration_ms,
            "site": site,
        })

        # Token optimization recording
        if self.token_optimizer:
            self.token_optimizer.record_action(
                _site_of(self.page.url), "snapshot", budget.profile, 
                report.tokens_used, True
            )

        return ActionResult(
            ok=True,
            data=rebuilt,
            report=report,
            duration_ms=duration_ms,
        )

    async def act(
        self,
        action: str,
        target: str,
        value: str | None = None,
        budget: Budget | None = None,
    ) -> ActionResult:
        budget = budget or self.default_budget
        started = time.perf_counter()
        await self._rate_limit(_site_of(self.page.url))
        healed: list[HealingOutcome] = []

        try:
            await self._dispatch(action, target, value)
        except Exception as exc:
            _log.warning("action failed, attempting heal: %s", exc)
            
            # Hound Original: Predictive healing with explanation
            if self.predictive_healer:
                site = _site_of(self.page.url)
                heal_result = await self.predictive_healer.heal_with_explanation(
                    original=target,
                    probe=lambda c: self.page.evaluate(COUNT_CANDIDATES_JS, [c])[c],
                    verify=lambda c: self.page.locator(c).first.is_visible() and self.page.locator(c).first.is_enabled(),
                    site=_site_of(self.page.url),
                    logical_key=target,
                )
                
                if not heal_result.healed:
                    return self._failure({
                        "error": str(exc)[:300], 
                        "target": target, 
                        "healing": heal_result.to_dict()
                    }, budget, started)
                
                # Use healed selector
                target = heal_result.selector
                
                # Record cross-site knowledge
                if self.cross_site_kb:
                    self.cross_site_kb.record_success(
                        _site_of(self.page.url), heal_result.selector, heal_result.verified
                    )
                
                try:
                    await self._dispatch(action, config_result.selector, value)
                except Exception as retry_exc:
                    return self._failure(
                        {"error": f"healed selector also failed: {retry_exc}"[:300]},
                        budget,
                        started,
                    )
            else:
                # Fallback to original healing
                outcome = await self._heal(target, action)
                if not outcome.healed:
                    return self._failure(
                        {"error": str(exc)[:300], "target": target, "healing": outcome.to_dict()},
                        budget,
                        started,
                    )
                try:
                    await self._dispatch(action, outcome.selector, value)
                except Exception as retry_exc:
                    return self._failure(
                        {"error": f"healed selector also failed: {retry_exc}"[:300]},
                        budget,
                        started,
                    )

        if action in {"click", "press", "select"}:
            await self.page.wait_for_timeout(120)

        result = await self.snapshot(budget=budget, delta=True)
        result.data["action"] = action
        result.data["target"] = target
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        
        # Record for token optimization
        if self.token_optimizer:
            self.token_optimizer.record_action(
                _site_of(self.page.url), action, budget.profile,
                result.report.tokens_used, result.ok
            )
        
        # Record cross-site knowledge on verified heals
        if self.cross_site_kb and result.healed:
            for heal in result.healed:
                if isinstance(heal, PredictiveHealResult) and heal.verified:
                    self.cross_site_kb.record_success(
                        _site_of(self.page.url), heal.selector, heal.verified
                    )
        
        return result

    def _failure(
        self,
        data: dict[str, Any],
        budget: Budget,
        started: float,
    ) -> ActionResult:
        from hound.core.budget import fit_to_budget
        _, report = fit_to_budget(data, budget)
        return ActionResult(
            ok=False,
            data=data,
            report=report,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _dispatch(self, action: str, target: str, value: str | None) -> None:
        locator = (
            self.page.locator(f"[data-ref='{target}'], #{target}") if _is_ref(target)
            else self.page.locator(target).first
        )
        if action == "click":
            await asyncio.wait_for(locator.click(timeout=8000), timeout=self.timeouts.element_action)
        elif action in {"fill", "type"}:
            await asyncio.wait_for(locator.fill(value or "", timeout=8000), timeout=self.timeouts.element_action)
        elif action == "press":
            await asyncio.wait_for(locator.press(value or "Enter", timeout=8000), timeout=self.timeouts.element_action)
        elif action == "select":
            await asyncio.wait_for(locator.select_option(value or "", timeout=8000), timeout=self.timeouts.element_action)
        else:
            raise ValueError(f"unsupported action: {action}")

    async def _heal(self, logical_key: str, target: str, action: str) -> HealingOutcome:
        candidates = generate_candidates(target)[:8]
        if not candidates:
            return HealingOutcome(
                healed=False,
                original=target,
                selector=target,
                confidence=0.0,
                verified=False,
                detail="could not derive any candidate selectors",
            )

        counts = await self.page.evaluate(COUNT_CANDIDATES_JS, candidates)

        async def probe(candidate: str) -> int:
            return int(counts.get(candidate, 0))

        async def verify(candidate: str) -> bool:
            locator = self.page.locator(candidate).first
            if not await locator.count():
                return False
            if action == "click":
                return bool(await locator.is_visible() and await locator.is_enabled())
            return True

        outcome = await heal_async(
            target,
            probe=probe,
            verify=verify,
            expected_matches=1,
        )
        if outcome.healed and outcome.verified:
            self.store.record_heal(outcome, site=_site_of(self.page.url), logical_key=logical_key)
        return outcome

    async def goto(self, url: str, **kwargs) -> ActionResult:
        await self._validate_and_goto(url, **kwargs)
        self._previous = None
        return await self.snapshot(budget=self.default_budget, delta=False)

    async def verify(self, selector: str) -> ActionResult:
        from hound.core.budget import BudgetReport
        matches = await self.page.locator(selector).count()
        return ActionResult(
            ok=True,
            data={"selector": selector, "matches": matches},
            report=BudgetReport(
                tokens_used=estimate_tokens(selector),
                max_tokens=self.default_budget.max_tokens,
                profile_requested=Profile.MINIMAL,
                profile_effective=Profile.MINIMAL,
            ),
        )
    async def find(self, text: str, limit: int = 10) -> ActionResult:
        """Find elements by accessible name or text."""
        from hound.core.budget import BudgetReport
        await self._rate_limit(_site_of(self.page.url))
        state = await self._capture()
        needle = text.lower()
        matches = [
            e.to_compact()
            for e in state.elements
            if needle in e.name.lower()
        ][:limit]
        
        payload = {"found": len(matches), "matches": matches}
        report = BudgetReport(
            tokens_used=estimate_tokens(payload),
            max_tokens=self.default_budget.max_tokens,
            profile_requested=Profile.BALANCED,
            profile_effective=Profile.BALANCED,
        )
        result = ActionResult(ok=True, data=payload, report=report)
        self._session_spend.append({
            "tool": "find",
            "tokens": report.tokens_used,
            "profile": report.profile_effective.value,
            "ms": 0,
        })
        return result



    async def close(self) -> None:
        if not self._closed:
            await self.page.close()
            self._closed = True

    def get_spend_report(self) -> dict[str, Any]:
        total = sum(row["tokens"] for row in self._session_spend)
        return {
            "total_tokens": total,
            "calls": len(self._session_spend),
            "average_tokens": round(total / len(self._session_spend), 1) if self._session_spend else 0,
            "token_optimizer_report": self.token_optimizer.get_session_report() if self.token_optimizer else None,
            "cross_site_report": self.cross_site_kb.get_transfer_report() if self.cross_site_kb else None,
        }


def _is_ref(value: str) -> bool:
    return bool(value) and value[0] == "e" and value[1:].isdigit()


def _site_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower() or "unknown"
    except ValueError:
        return "unknown"


# Re-export for backward compatibility
from hound.core.budget import Budget, BudgetReport, Profile, estimate_tokens, fit_to_budget
from hound.core.refs import PageState, build_state, diff
from hound.healing.selectors import (
    HealingOutcome,
    SelectorStore,
    generate_candidates,
    heal_async,
)
