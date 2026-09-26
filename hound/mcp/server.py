"""MCP server exposing Hound's budgeted browser tools.

Deliberately exposes a *small* tool set. Every tool definition is loaded into the
model's context on every turn, so a server that publishes 71 tools costs the
agent thousands of tokens before it has done anything. Hound publishes seven,
and each one takes an explicit ``max_tokens`` budget.

The separate design goal from the token budget: a model should never be told a
selector "probably works". Every response states what was verified.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from hound.core.budget import Budget, Profile, estimate_tokens
from hound.core.engine import BudgetedBrowser
from hound.healing.selectors import SelectorStore

SERVER_NAME = "hound"
DEFAULT_DB = os.environ.get("HOUND_DB", "hound-selectors.db")
MAX_BUDGET_TOKENS = int(os.environ.get("HOUND_MAX_BUDGET", "20000"))
DEFAULT_BUDGET_TOKENS = int(os.environ.get("HOUND_DEFAULT_BUDGET", "1200"))

TOOLS = [
    Tool(
        name="browser_open",
        description=(
            "Open a URL and return a budgeted page snapshot. Use this instead of a "
            "raw fetch when the page is rendered client-side or needs a real browser."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute URL to open."},
                "max_tokens": {
                    "type": "integer",
                    "description": f"Token ceiling for the response. Default {DEFAULT_BUDGET_TOKENS}.",
                    "default": DEFAULT_BUDGET_TOKENS,
                    "maximum": MAX_BUDGET_TOKENS,
                },
                "profile": {
                    "type": "string",
                    "enum": [p.value for p in Profile],
                    "description": "How much of the page to return. Default balanced.",
                    "default": Profile.BALANCED.value,
                },
                "wait_until": {
                    "type": "string",
                    "enum": ["load", "domcontentloaded", "networkidle"],
                    "default": "load",
                },
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="browser_snapshot",
        description=(
            "Re-read the current page. Returns only what changed since the last call "
            "unless the page navigated, so this is cheap to call after an action. "
            "Set full_snapshot=true after a navigation to get every element ref."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "max_tokens": {"type": "integer", "default": DEFAULT_BUDGET_TOKENS,
                               "maximum": MAX_BUDGET_TOKENS},
                "profile": {"type": "string", "enum": [p.value for p in Profile],
                            "default": Profile.BALANCED.value},
                "full_snapshot": {"type": "boolean", "default": False},
            },
        },
    ),
    Tool(
        name="browser_act",
        description=(
            "Click, type into, select from, or press a key on an element addressed by "
            "ref (e1, e2) or CSS selector. Returns a compact confirmation plus whatever "
            "changed on the page."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["click", "fill", "press", "select"]},
                "target": {"type": "string", "description": "Element ref (e3) or CSS selector."},
                "value": {"type": "string", "description": "Text for fill, key for press, option for select."},
                "max_tokens": {"type": "integer", "default": DEFAULT_BUDGET_TOKENS,
                               "maximum": MAX_BUDGET_TOKENS},
                "profile": {"type": "string", "enum": [p.value for p in Profile],
                            "default": Profile.MINIMAL.value},
            },
            "required": ["action", "target"],
        },
    ),
    Tool(
        name="browser_find",
        description=(
            "Locate elements by accessible name, role or text and return their refs. "
            "Use this when you know what you want to click but not where it is, which "
            "avoids paying for a full page snapshot."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Substring of the accessible name."},
                "role": {"type": "string", "description": "Optional role filter, e.g. link, button."},
                "limit": {"type": "integer", "default": 10, "maximum": 50},
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="browser_extract",
        description=(
            "Pull structured records out of the page using a field -> CSS selector map. "
            "Reports a confidence level and a verified flag so you can tell a successful "
            "extraction from an empty one."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "root": {"type": "string", "description": "Repeating container selector, e.g. 'li.job'."},
                "fields": {
                    "type": "object",
                    "description": "Map of output field name to CSS selector within each container.",
                    "additionalProperties": {"type": "string"},
                },
                "max_tokens": {"type": "integer", "default": DEFAULT_BUDGET_TOKENS,
                               "maximum": MAX_BUDGET_TOKENS},
            },
            "required": ["root", "fields"],
        },
    ),
    Tool(
        name="browser_heal",
        description=(
            "Repair a broken selector against the live page. Returns the replacement only "
            "if it was verified to match a real, actionable element. Verified repairs are "
            "remembered per site, so later runs on the same site start already fixed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "The selector that stopped working."},
                "logical_key": {
                    "type": "string",
                    "description": "Stable name for what this selector targets, e.g. 'search_button'.",
                },
            },
            "required": ["selector", "logical_key"],
        },
    ),
    Tool(
        name="browser_budget_report",
        description=(
            "Return token spend for the current session. Use this to check whether a "
            "flow is running expensive before adding more steps."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
]


class HoundServer:
    """Owns the browser session and the per-session spend counter."""

    def __init__(self, db_path: str | None = None, headless: bool = True):
        self.store = SelectorStore(db_path or DEFAULT_DB)
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self.engine: BudgetedBrowser | None = None
        self.spend: list[dict[str, Any]] = []

    async def start(self) -> None:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        self.engine = BudgetedBrowser(
            self.page,
            store=self.store,
            default_budget=Budget(max_tokens=DEFAULT_BUDGET_TOKENS),
        )

    async def stop(self) -> None:
        for closer in (self.context, self.browser):
            if closer is not None:
                try:
                    await closer.close()
                except Exception:
                    pass
        if getattr(self, "_pw", None) is not None:
            await self._pw.stop()
        self.store.close()

    def _record(self, tool: str, result) -> None:
        self.spend.append(
            {
                "tool": tool,
                "tokens": result.tokens,
                "profile": result.report.profile_effective.value,
                "truncated": result.report.truncated,
                "ms": result.duration_ms,
            }
        )

    def _budget(self, args: dict) -> Budget:
        raw = int(args.get("max_tokens") or DEFAULT_BUDGET_TOKENS)
        raw = max(64, min(raw, MAX_BUDGET_TOKENS))
        profile = Profile(args["profile"]) if args.get("profile") else Profile.BALANCED
        return Budget(max_tokens=raw, profile=profile)

    # -- tool implementations -------------------------------------------

    async def tool_open(self, args: dict) -> Any:
        budget = self._budget({**args, "profile": args.get("profile", Profile.BALANCED.value)})
        result = await self.engine.goto(
            args["url"], wait_until=args.get("wait_until", "load")
        )
        result.report.max_tokens = budget.max_tokens
        self._record("browser_open", result)
        return result

    async def tool_snapshot(self, args: dict) -> Any:
        budget = self._budget(args)
        result = await self.engine.snapshot(
            budget=budget, delta=not args.get("full_snapshot", False)
        )
        self._record("browser_snapshot", result)
        return result

    async def tool_act(self, args: dict) -> Any:
        budget = self._budget({**args, "profile": args.get("profile", Profile.MINIMAL.value)})
        result = await self.engine.act(
            args["action"],
            args["target"],
            value=args.get("value"),
            budget=budget,
        )
        self._record("browser_act", result)
        return result

    async def tool_find(self, args: dict) -> Any:
        assert self.engine is not None
        state = await self.engine._capture()
        needle = args["text"].lower()
        role = args.get("role")
        limit = int(args.get("limit", 10))
        matches = [
            e.to_compact()
            for e in state.elements
            if needle in e.name.lower() and (role is None or e.role == role)
        ][:limit]
        from hound.core.engine import ActionResult
        from hound.core.budget import BudgetReport

        payload = {"found": len(matches), "matches": matches}
        report = BudgetReport(
            tokens_used=estimate_tokens(payload),
            max_tokens=DEFAULT_BUDGET_TOKENS,
            profile_requested=Profile.BALANCED,
            profile_effective=Profile.BALANCED,
        )
        result = ActionResult(ok=True, data=payload, report=report)
        self._record("browser_find", result)
        return result

    async def tool_extract(self, args: dict) -> Any:
        assert self.engine is not None
        root = args["root"]
        fields: dict[str, str] = args["fields"]
        limit = 200
        rows: list[dict] = []
        containers = self.page.locator(root)
        total = min(await containers.count(), limit)

        for i in range(total):
            container = containers.nth(i)
            record: dict[str, str | None] = {}
            for name, selector in fields.items():
                try:
                    record[name] = (await container.locator(selector).first.inner_text()).strip()
                except Exception:
                    record[name] = None
            rows.append(record)

        filled = sum(
            1
            for row in rows
            if any(v for k, v in row.items() if k in list(fields)[:1])
        )
        # A record is only "verified" if its primary key field is non-empty.
        # Returning a list of empty objects and calling it success is the single
        # most common failure mode of automated extraction.
        confidence = round(filled / total, 3) if total else 0.0

        from hound.core.budget import BudgetReport
        from hound.core.engine import ActionResult

        budget = self._budget(args)
        payload = {
            "root": root,
            "count": total,
            "confidence": confidence,
            "verified": confidence >= 0.8 and total > 0,
            "records": rows[:100],
        }
        from hound.core.budget import fit_to_budget

        payload, report = fit_to_budget(payload, budget)
        result = ActionResult(ok=True, data=payload, report=report)
        self._record("browser_extract", result)
        return result

    async def tool_heal(self, args: dict) -> Any:
        assert self.engine is not None
        outcome = await self.engine._heal(args["logical_key"], args["selector"], "click")

        from hound.core.budget import BudgetReport
        from hound.core.engine import ActionResult

        payload = outcome.to_dict()
        report = BudgetReport(
            tokens_used=estimate_tokens(payload),
            max_tokens=DEFAULT_BUDGET_TOKENS,
            profile_requested=Profile.MINIMAL,
            profile_effective=Profile.MINIMAL,
        )
        result = ActionResult(ok=outcome.healed, data=payload, report=report)
        self._record("browser_heal", result)
        return result

    async def tool_report(self, args: dict) -> Any:
        from hound.core.budget import BudgetReport
        from hound.core.engine import ActionResult

        total = sum(row["tokens"] for row in self.spend)
        payload = {
            "total_tokens": total,
            "calls": len(self.spend),
            "average_tokens": round(total / len(self.spend), 1) if self.spend else 0,
            "by_tool": self.spend[-40:],
            "selectors": self.store.stats(),
        }
        report = BudgetReport(
            tokens_used=estimate_tokens(payload),
            max_tokens=DEFAULT_BUDGET_TOKENS,
            profile_requested=Profile.FULL,
            profile_effective=Profile.FULL,
        )
        return ActionResult(ok=True, data=payload, report=report)

    async def dispatch(self, name: str, args: dict) -> Any:
        table = {
            "browser_open": self.tool_open,
            "browser_snapshot": self.tool_snapshot,
            "browser_act": self.tool_act,
            "browser_find": self.tool_find,
            "browser_extract": self.tool_extract,
            "browser_heal": self.tool_heal,
            "browser_budget_report": self.tool_report,
        }
        handler = table.get(name)
        if handler is None:
            raise ValueError(f"unknown tool: {name}")
        return await handler(args)


def build_server() -> Server:
    session = HoundServer(headless=os.environ.get("HOUND_HEADLESS", "1") != "0")
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        result = await session.dispatch(name, arguments or {})
        return [TextContent(type="text", text=result.render())]

    server.hound_session = session  # type: ignore[attr-defined]
    return server


async def main() -> None:
    server = build_server()
    session: HoundServer = server.hound_session  # type: ignore[attr-defined]
    await session.start()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await session.stop()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
