"""The budgeted browser engine.

Wraps Playwright and returns budgeted, referable, diffed page state instead of
raw snapshots. Playwright is an implementation detail here - the contract this
module exposes is what the MCP layer and the hosted API both depend on.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from hound.core.budget import Budget, BudgetReport, Profile, estimate_tokens, fit_to_budget
from hound.core.refs import PageState, build_state, diff
from hound.healing.selectors import (
    HealingOutcome,
    SelectorStore,
    generate_candidates,
    heal_async,
)

_log = logging.getLogger(__name__)

# --- Security: URL Validation ---

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOST_PREFIXES = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "10.",
    "192.168.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "::1",
    "fe80::",
)

def validate_url(url: str) -> tuple[bool, str]:
    """Validate URL against SSRF and security policies."""
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL: {e}"

    if parsed.scheme not in ALLOWED_SCHEMES:
        return False, f"Scheme '{parsed.scheme}' not allowed"

    hostname = parsed.hostname or ""
    if not hostname:
        return False, "No hostname"

    # Check blocked prefixes
    for prefix in BLOCKED_HOST_PREFIXES:
        if hostname.startswith(prefix):
            return False, f"Host '{hostname}' is blocked (private/internal)"

    # Additional: block metadata endpoints
    if hostname in ("169.254.169.254", "metadata.google.internal", "metadata.azure.com"):
        return False, f"Metadata endpoint '{hostname}' blocked"

    return True, "OK"


# --- Rate Limiting ---

class RateLimiter:
    """Simple token bucket rate limiter for browser operations."""

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # Remove old requests outside window
            cutoff = now - self.window_seconds
            self.requests = [t for t in self.requests if t > cutoff]

            if len(self.requests) >= self.max_requests:
                # Wait until oldest request expires
                wait_time = self.requests[0] + self.window_seconds - time.monotonic()
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                # Recheck after wait
                now = time.monotonic()
                self.requests = [t for t in self.requests if t > now - self.window_seconds]

            self.requests.append(time.monotonic())


# --- Timeouts Configuration ---

@dataclass
class TimeoutConfig:
    """Configurable timeouts for browser operations."""
    navigation: float = 30.0      # Page navigation
    element_action: float = 10.0  # Click, fill, etc.
    selector_wait: float = 5.0    # Wait for selector
    snapshot: float = 10.0        # Page capture
    healing: float = 15.0         # Selector healing


# --- Main Engine ---

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
    import random
    return random.uniform(min_ms, max_ms) / 1000.0


class HumanMouse:
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
    duration_ms: int = 0

    def render(self) -> str:
        parts = [f"ok={self.ok}"]
        if self.healed:
            parts.append(f"healed={len(self.healed)}")
        if self.duration_ms:
            parts.append(f"{self.duration_ms}ms")
        parts.append(self.report.render())
        return " | ".join(parts)


class BudgetedBrowser:
    """Wraps Playwright and returns budgeted, referable, diffed page state."""

    def __init__(
        self,
        page,
        store: SelectorStore,
        default_budget: Budget,
        rate_limiter: Optional[RateLimiter] = None,
        timeouts: Optional[TimeoutConfig] = None,
    ):
        self.page = page
        self.store = store
        self.default_budget = default_budget
        self.rate_limiter = rate_limiter or RateLimiter()
        self.timeouts = timeouts or TimeoutConfig()
        self._previous: Optional[PageState] = None
        self._session_spend: list[dict[str, Any]] = []
        self._closed = False

    async def _rate_limit(self) -> None:
        await self.rate_limiter.acquire()

    async def _validate_and_goto(self, url: str, **kwargs) -> None:
        """Validate URL and navigate with timeout."""
        ok, msg = validate_url(url)
        if not ok:
            raise ValueError(f"URL validation failed: {msg}")
        await asyncio.wait_for(
            self.page.goto(url, **kwargs),
            timeout=self.timeouts.navigation
        )

    async def _capture(self) -> PageState:
        """Capture current page state via injected DOM extractor."""
        raw = await self.page.evaluate(DOM_EXTRACTOR)
        return build_state(self.page.url, raw)

    async def snapshot(
        self,
        budget: Budget,
        delta: bool = True,
    ) -> ActionResult:
        """Return a budgeted page snapshot (delta or full)."""
        started = time.perf_counter()
        await self._rate_limit()

        try:
            state = await asyncio.wait_for(
                self._capture(),
                timeout=self.timeouts.snapshot
            )
        except asyncio.TimeoutError:
            return self._failure(
                {"error": "snapshot timeout"},
                budget,
                started,
            )

        if delta and self._previous is not None:
            diff_result = diff(self._previous, state)
            payload = diff_result
        else:
            payload = state.to_compact()

        self._previous = state

        rebuilt, report = fit_to_budget(payload, budget)
        report.tokens_used = estimate_tokens(rebuilt)
        duration_ms = int((time.perf_counter() - started) * 1000)

        self._session_spend.append({
            "tool": "snapshot",
            "tokens": report.tokens_used,
            "profile": report.profile_effective.value,
            "ms": duration_ms,
        })

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
        """Perform an action with budget enforcement and self-healing."""
        budget = budget or self.default_budget
        started = time.perf_counter()
        await self._rate_limit()
        healed: list[HealingOutcome] = []

        try:
            await self._dispatch(action, target, value)
        except Exception as exc:
            _log.warning("action failed, attempting heal: %s", exc)
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
        result.healed = []  # reset for this action
        result.data["action"] = action
        result.data["target"] = target
        result.duration_ms = int((time.perf_counter() - started) * 1000)
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
            return bool(await locator.is_visible() and await locator.is_enabled())

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
        """Navigate to URL with validation and return snapshot."""
        await self._validate_and_goto(url, **kwargs)
        self._previous = None
        return await self.snapshot(delta=False)

    async def verify(self, selector: str) -> ActionResult:
        from hound.core.budget import BudgetReport
        from hound.core.engine import ActionResult
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
