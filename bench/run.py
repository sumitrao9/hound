"""Token benchmark: Hound vs a snapshot-per-action MCP server.

This is the project's claim, so it has to be measured rather than asserted.

Method
------
Drive the same scripted flow twice against the same page:

1. **Snapshot-per-action** - the behaviour of a conventional browser MCP server.
   Every action re-serialises the full accessibility tree into the response.
2. **Hound** - budgeted responses plus a delta against the previous call.

The Playwright ARIA snapshot (``page.accessibility.snapshot()``) is used as the
"full tree" payload because that is what these servers actually return. Hound's
own rendering is what the engine emits.

Run it:

    python -m bench.run --url https://news.ycombinator.com
    python -m bench.run --pages 3 --json results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from hound.core.budget import Budget, Profile, estimate_tokens
from hound.core.engine import BudgetedBrowser

# A realistic agent flow: land, orient, read, interact, read again.
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
    """Cost of a snapshot-per-action server: full ARIA tree, every time.

    Mirrors what a browser MCP server returns after an action - the accessibility
    tree plus the page's text - with no memory of what the agent already saw.
    """
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

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        engine = BudgetedBrowser(page, default_budget=Budget(max_tokens=budget_tokens, profile=profile))  # noqa: E501
        result = Result(url=url, dom_elements=0)

        for step in FLOW:
            label = step["kind"]

            if step["kind"] == "open":
                await engine.goto(url)
                # Measured after the navigation, because a snapshot-per-action
                # server returns the post-action page. Measuring before would
                # compare the new page against about:blank.
                conventional = await conventional_step(page)
                hound = await engine.snapshot(
                    delta=False, budget=Budget(budget_tokens, Profile.BALANCED)
                )
            elif step["kind"] == "snapshot":
                conventional = await conventional_step(page)
                hound = await engine.snapshot(
                    budget=Budget(budget_tokens, Profile.MINIMAL), delta=True
                )
            else:
                target = await _pick(page, step["role"], step.get("pick", 0))
                if target is None:
                    # The page has no element of that kind. Measuring Hound on a
                    # step it cannot perform would flatter the comparison, so the
                    # step is dropped from both sides instead.
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

        result.dom_elements = await page.evaluate(
            "() => document.querySelectorAll('*').length"
        )

        await context.close()
        await browser.close()

    return result


def render_table(results: list[Result]) -> str:
    lines = [
        "",
        "=" * 78,
        "  HOUND TOKEN BENCHMARK",
        "=" * 78,
        f"  {'step':<16}{'conventional':>14}{'hound':>10}{'saved':>12}{'ratio':>9}",
        "  " + "-" * 74,
    ]
    for result in results:
        lines.append(f"  {result.url}")
        for step in result.steps:
            ratio = f"{step.ratio:.1f}x" if step.ratio != float("inf") else "inf"
            lines.append(
                f"  {step.label:<16}{step.conventional_tokens:>14,}"
                f"{step.hound_tokens:>10,}{step.saved:>12,}{ratio:>9}"
            )
        lines.append(
            f"  {'TOTAL':<16}{result.conventional_total:>14,}"
            f"{result.hound_total:>10,}"
            f"{result.conventional_total - result.hound_total:>12,}"
        )
        lines.append("")

    totals_conventional = sum(r.conventional_total for r in results)
    totals_hound = sum(r.hound_total for r in results)
    reduction = (1 - totals_hound / totals_conventional) * 100 if totals_conventional else 0

    lines += [
        "-" * 78,
        f"  Conventional total : {totals_conventional:>10,} tokens",
        f"  Hound total        : {totals_hound:>10,} tokens",
        f"  Reduction          : {reduction:>9.1f}%",
        "-" * 78,
    ]
    return "\n".join(lines)


DEFAULT_PAGES = [
    "https://example.com",
    "https://news.ycombinator.com",
    "https://en.wikipedia.org/wiki/Web_scraping",
]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Hound against snapshot-per-action.")
    parser.add_argument("--url", action="append", help="Page to benchmark. Repeatable.")
    parser.add_argument("--pages", type=int, default=3, help="How many default pages to use.")
    parser.add_argument("--budget", type=int, default=1200, help="Hound token budget per call.")
    parser.add_argument(
        "--profile", default=Profile.BALANCED.value, choices=[p.value for p in Profile]
    )
    parser.add_argument("--json", help="Also write raw results to this path.")
    args = parser.parse_args()

    urls = args.url or DEFAULT_PAGES[: max(1, args.pages)]

    results: list[Result] = []
    for url in urls:
        try:
            results.append(
                await run_page(
                    url, budget_tokens=args.budget, profile=Profile(args.profile)
                )
            )
        except Exception as exc:
            print(f"  skipped {url}: {exc}")

    if not results:
        print("no pages benchmarked successfully")
        return 1

    print(render_table(results))

    if args.json:
        payload = {
            "budget_tokens": args.budget,
            "profile": args.profile,
            "pages": [r.to_dict() for r in results],
        }
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print(f"\n  wrote {args.json}")
    return 0


def cli() -> int:
    """Console entry point (``hound-bench``)."""
    return asyncio.run(main())


if __name__ == "__main__":
    raise SystemExit(cli())
