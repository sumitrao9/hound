"""The budgeted browser engine.

Wraps Playwright and returns budgeted, referable, diffed page state instead of
raw snapshots. Playwright is an implementation detail here - the contract this
module exposes is what the MCP layer and the hosted API both depend on.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from hound.core.budget import Budget, BudgetReport, Profile, estimate_tokens, fit_to_budget
from hound.core.refs import PageState, build_state, diff
from hound.healing.selectors import (
    HealingOutcome,
    SelectorStore,
    generate_candidates,
    heal_async,
)

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
      // keep only meaningful non-interactive nodes
      if (!['alert','dialog','status','navigation','main'].includes(role)) continue;
    }

    elements.push({
      role: role || 'generic',
      name: nameOf(el),
      value: isFormField ? String(el.value || '').slice(0, 200) : '',
      disabled: Boolean(el.disabled),
      checked: (el.type === 'checkbox' || el.type === 'radio') ? Boolean(el.checked) : null,
      selector: testid ? `[data-testid="${testid}"]` : pathOf(el),
    });
    if (elements.length >= 400) break;
  }

  return {
    url: location.href,
    title: document.title,
    text: (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim().slice(0, 40000),
    elements,
  };
}
"""


@dataclass
class ActionResult:
    """The uniform return type of every engine action."""

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    report: BudgetReport = field(default_factory=BudgetReport)
    healed: list[HealingOutcome] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def tokens(self) -> int:
        return self.report.tokens_used

    def render(self) -> str:
        """The exact string the agent will pay tokens for.

        Deliberately a compact, deterministic line format rather than JSON: JSON
        punctuation is pure overhead when a model is reading the result.
        """
        lines = [self._line(f"ok={str(self.ok).lower()}")]
        if self.data.get("url"):
            lines.append(self._line(f"url {self.data['url']}"))
        if self.data.get("title"):
            lines.append(self._line(f"title {self.data['title']}"))
        for element in self.data.get("elements", []) or []:
            lines.append(self._render_element(element))
        for key in ("added", "removed", "changed"):
            items = self.data.get(key)
            if not items:
                continue
            lines.append(self._line(f"{key} ({len(items)}):"))
            for item in items[:20]:
                lines.append("  " + self._render_element(item, prefix=""))
        text = self.data.get("text")
        if text:
            lines.append(self._line(f"text {text[:400]}"))
        lines.append(self._line(self.report.render()))
        return "\n".join(lines)

    @staticmethod
    def _line(value: str) -> str:
        return value

    @staticmethod
    def _render_element(element: dict, prefix: str = "  ") -> str:
        if not isinstance(element, dict):
            return f"{prefix}{element}"
        bits = [element.get("ref", "?"), element.get("role", "?")]
        if element.get("name"):
            bits.append(f'"{element["name"]}"')
        if element.get("value"):
            bits.append(f"={element['value']}")
        if element.get("disabled"):
            bits.append("(disabled)")
        if element.get("checked") is True:
            bits.append("(checked)")
        return prefix + " ".join(str(b) for b in bits)


class BudgetedBrowser:
    """A Playwright page that answers within a token budget.

    Keeps the last page state so repeat calls can return a delta instead of a
    full snapshot. That single behaviour is what turns per-action cost from
    O(page size) into O(changes).
    """

    def __init__(
        self,
        page,
        *,
        store: SelectorStore | None = None,
        default_budget: Budget | None = None,
    ):
        self.page = page
        self.store = store or SelectorStore()
        self.default_budget = default_budget or Budget()
        self._previous: PageState | None = None
        self._current: PageState | None = None
        self._texts: dict[str, PageState] = {}

    # -- capture ---------------------------------------------------------

    async def _capture(self) -> PageState:
        raw = await self.page.evaluate(DOM_EXTRACTOR)
        return build_state(
            url=raw.get("url", ""),
            title=raw.get("title", ""),
            text=raw.get("text", ""),
            elements=raw.get("elements", []) or [],
        )

    def _build(
        self,
        state: PageState,
        profile: Profile,
        *,
        delta: bool,
        with_text: bool,
    ) -> dict[str, Any]:
        payload = state.render(profile)
        if delta and self._previous is not None:
            changes = diff(self._previous, state)
            # A navigation invalidates every ref the agent is holding, so a full
            # snapshot is the honest answer even if a delta was requested.
            if changes.get("navigated") or changes.get("url_changed"):
                payload["navigated"] = True
            else:
                payload = {
                    "url": state.url,
                    "title": state.title,
                    "added": changes.get("added", []),
                    "removed": changes.get("removed", []),
                    "changed": changes.get("changed", []),
                    "unchanged": changes.get("unchanged_count", 0),
                }
        if with_text and profile.include_text:
            allowance = profile.text_char_allowance
            payload["text"] = state.text[:allowance]
        return payload

    def _rebuilder(self, state: PageState, *, delta: bool):
        def rebuild(profile: Profile) -> dict[str, Any] | None:
            return self._build(state, profile, delta=delta, with_text=profile is not Profile.MINIMAL)

        return rebuild

    # -- public actions --------------------------------------------------

    async def snapshot(
        self,
        *,
        budget: Budget | None = None,
        delta: bool = True,
        profile: Profile | None = None,
    ) -> ActionResult:
        budget = budget or self.default_budget
        if profile:
            budget = Budget(budget.max_tokens, profile, budget.hard_fail)
        started = time.perf_counter()

        state = await self._capture()

        payload = self._build(
            state, budget.profile, delta=delta, with_text=budget.profile.include_text
        )
        payload, report = fit_to_budget(
            payload, budget, rebuild=self._rebuilder(state, delta=delta)
        )

        # The response describes *this* state, so it becomes the baseline for
        # the next delta. Advancing this on every call is what makes repeat calls
        # cost O(changes) rather than O(page).
        self._previous = state
        self._current = state
        return ActionResult(
            ok=True,
            data=payload,
            report=report,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    async def act(
        self,
        action: str,
        target: str,
        *,
        value: str | None = None,
        budget: Budget | None = None,
        profile: Profile | None = None,
        logical_key: str | None = None,
    ) -> ActionResult:
        """Click, type, select or press, addressed by ref or selector.

        When the target cannot be resolved and a ``logical_key`` is supplied,
        the healer is invoked and any verified repair is persisted.
        """
        budget = budget or self.default_budget
        if profile:
            budget = Budget(budget.max_tokens, profile, budget.hard_fail)
        started = time.perf_counter()
        healed: list[HealingOutcome] = []
        resolved = target

        try:
            await self._dispatch(action, target, value)
        except Exception as exc:
            if not logical_key:
                return self._failure(
                    {"error": str(exc)[:300], "target": target, "action": action},
                    budget,
                    started,
                    healed,
                )
            outcome = await self._heal(logical_key, target, action)
            healed.append(outcome)
            if not outcome.healed:
                return self._failure(
                    {"error": str(exc)[:300], "target": target, "healing": outcome.to_dict()},
                    budget,
                    started,
                    healed,
                )
            resolved = outcome.selector
            try:
                await self._dispatch(action, resolved, value)
            except Exception as retry_exc:
                return self._failure(
                    {"error": f"healed selector also failed: {retry_exc}"[:300]},
                    budget,
                    started,
                    healed,
                )

        if action in {"click", "press", "select"}:
            await self.page.wait_for_timeout(120)

        result = await self.snapshot(budget=budget, delta=True)
        result.healed = healed
        result.data["action"] = action
        result.data["target"] = resolved
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        return result

    def _failure(
        self,
        data: dict[str, Any],
        budget: Budget,
        started: float,
        healed: list[HealingOutcome],
    ) -> ActionResult:
        """Build a failed result that still accounts for what it cost.

        An error still occupies context, and the session spend report is only
        trustworthy if failures are counted. Reporting a failed call as costing
        zero tokens would make the budget look better than it is.
        """
        _, report = fit_to_budget(data, budget)
        return ActionResult(
            ok=False,
            data=data,
            report=report,
            healed=healed,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _dispatch(self, action: str, target: str, value: str | None) -> None:
        locator = (
            self.page.locator(f"[data-ref='{target}'], #{target}") if _is_ref(target)
            else self.page.locator(target).first
        )
        if action == "click":
            await locator.click(timeout=8_000)
        elif action in {"fill", "type"}:
            await locator.fill(value or "", timeout=8_000)
        elif action == "press":
            await locator.press(value or "Enter", timeout=8_000)
        elif action == "select":
            await locator.select_option(value or "", timeout=8_000)
        else:
            raise ValueError(f"unsupported action: {action}")

    async def _heal(self, logical_key: str, target: str, action: str) -> HealingOutcome:
        """Attempt a verified repair and persist it if it works.

        Match counts for every candidate are fetched in a single ``evaluate``
        round trip rather than one query per candidate, so healing costs the
        agent one extra call regardless of how many candidates are tried.
        """
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
                # Never click while verifying. Confirm the node is visible,
                # enabled and actionable instead.
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
        started = time.perf_counter()
        await self.page.goto(url, **kwargs)
        self._previous = None
        return await self.snapshot(delta=False)

    async def verify(self, selector: str) -> ActionResult:
        state = await self._capture()
        matches = self.page.locator(selector).count()
        return ActionResult(
            ok=True,
            data={"selector": selector, "matches": matches},
            report=BudgetReport(tokens_used=estimate_tokens(selector), max_tokens=self.default_budget.max_tokens,
                                profile_requested=Profile.MINIMAL, profile_effective=Profile.MINIMAL),
        )

    async def close(self) -> None:
        await self.page.close()


def _is_ref(value: str) -> bool:
    return bool(value) and value[0] == "e" and value[1:].isdigit()


def _site_of(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url).netloc.lower() or "unknown"
    except ValueError:
        return "unknown"
