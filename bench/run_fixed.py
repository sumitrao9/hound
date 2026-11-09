"""Token benchmark: Hound vs a snapshot-per-action MCP server."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from hound.core.budget import Budget, Profile, estimate_tokens
from hound.core.engine import BudgetedBrowser
from hound.healing.selectors import SelectorStore

# A realistic agent flow
FLOW: list[dict[str, Any]] = [
    {"kind": "open"},
    {"kind": "snapshot"},
    {"kind": "act", "action": "click", "role": "link", "pick": 0},
    {"kind": "snapshot"},
    {"kind": "snapshot"},
    {"kind": "act", "action": "fill", "role": "textbox", "value": "python"},
    {"kind": "snapshot"},
    {"kind": "snapshot"},
]


@dataclass
class Step:
    label: str
    conventional_tokens: int
    hound_tokens: int

    @property
    def saved(self) -> int:
        return self.conventional_tokens - self.hound_tokens

    @property
    def ratio(self) -> float:
        if not self.hound_tokens:
            return float("inf") if self.conventional_tokens else 1.0
        return self.conventional_tokens / self.hound_tokens


@dataclass
class Result:
    url: str
    dom_elements: int
    steps: list[Step] = field(default_factory=list)

    @property
    def conventional_total(self) -> int:
        return sum(s.conventional_tokens for s in self.steps)

    @property
    def hound_total(self) -> int:
        return sum(s.hound_tokens for s in self.steps)

    @property
    def reduction_pct(self) -> float:
        base = self.conventional_total
        if not base:
            return 0.0
        return round((1 - self.hound_total / base) * 100, 1)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "dom_elements": self.dom_elements,
            "conventional_total_tokens": self.conventional_total,
            "hound_total_tokens": self.hound_total,
            "reduction_pct": self.reduction_pct,
            "steps": [asdict(s) for s in self.steps],
        }


ARIA_SNAPSHOT_JS = """
() => {
  const out = [];
  const walk = (el, depth) => {
    if (out.length > 1500 || depth > 22) return;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
    const role = el.getAttribute('role')
      || ({A: 'link', BUTTON: 'button', INPUT: 'textbox', TEXTAREA: 'textbox',
           SELECT: 'combobox', IMG: 'img', H1: 'heading', H2: 'heading',
           H3: 'heading', H4: 'heading', LI: 'listitem', TR: 'row', TD: 'cell'})[el.tagName]
      || '';
    const name = (el.getAttribute('aria-label') || el.innerText || '').trim().slice(0, 120);
    if (role || name) {
      out.push('- '.repeat(depth) + '[' + (role || el.tagName.toLowerCase()) + '] ' + name);
    }
    for (const child of el.children) walk(child, depth + 1);
  };
  walk(document.body, 0);
  return out.join('\\n');
}
"""


async def conventional_step(page) -> int:
    try:
        tree = await page.locator("body").aria_snapshot()
    except Exception:
        tree = await page.evaluate(ARIA_SNAPSHOT_JS)
    text = await page.evaluate("() => (document.body?.innerText || '').slice(0, 40000)")
    return estimate_tokens({"snapshot": tree, "text": text})


async def _pick(page, role: str, index: int):
    selector = {
        "link": "a[href]",
        "button": "button",
        "textbox": "input[type=text], input[type=search], textarea",
    }[role]
    locator = page.locator(selector)
    count = await locator.count()
    if count == 0:
        return None
    return locator.nth(min(index, count - 1))


async def run_page(url: str, *, budget_tokens: int, profile: Profile) -> Result:
    from playwright.async_api import async_playwright

    store = SelectorStore(":memory:")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        engine = BudgetedBrowser(page, store=store, default_budget=Budget(max_tokens=budget_tokens, profile=profile))
        result = Result(url=url, dom_elements=0)

        for step in FLOW:
            label = step["kind"]

            if step["kind"] == "open":
                await engine.goto(url)
                conventional = await conventional_step(page)
                hound = await engine.snapshot(delta=False, budget=Budget(budget_tokens, Profile.BALANCED))
            elif step["kind"] == "snapshot":
                conventional = await conventional_step(page)
                hound = await engine.snapshot(budget=Budget(budget_tokens, Profile.MINIMAL), delta=True)
            else:
                target = await _pick(page, step["role"], step.get("pick", 0))
                if target is None:
                    continue
                selector = await target.evaluate(
                    "el => el.id ? '#' + CSS.escape(el.id) : el.tagName.toLowerCase()"
                )
                hound = await engine.act(
                    step["action"],
                    selector,
                    value=step.get("value"),
                    budget=Budget(budget_tokens, Profile.MINIMAL),
                )
                conventional = await conventional_step(page)
                label = f"{step['kind']}:{step['action']}"

            result.steps.append(Step(label, conventional, hound.tokens))

        result.dom_elements = await page.evaluate("() => document.querySelectorAll('*').length")

        await context.close()
        await browser.close()
        store.close()

    return result


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url")
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--budget", type=int, default=1200)
    p.add_argument("--profile", default="balanced", choices=[p.value for p in Profile])
    p.add_argument("--json", help="write results to JSON")
    args = p.parse_args(argv)

    urls = [
        "https://example.com",
        "https://news.ycombinator.com",
        "https://en.wikipedia.org/wiki/Web_scraping",
    ][: args.pages]

    profile = Profile(args.profile)
    results = []
    for url in urls:
        try:
            res = await run_page(url, budget_tokens=args.budget, profile=profile)
            results.append(res.to_dict())
            print(f"{url}: {res.reduction_pct}% reduction ({res.hound_total}/{res.conventional_total} tokens)")
        except Exception as exc:
            print(f"skipped {url}: {exc}", flush=True)

    out = {"budget_tokens": args.budget, "profile": profile.value, "pages": results}
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, indent=2)
        print(f"wrote {args.json}")
    else:
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
