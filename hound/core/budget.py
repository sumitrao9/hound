"""Token budgeting for browser automation tool responses.

This is the core idea of Hound and the reason it exists.

Every mainstream browser-automation MCP server returns the page's full
accessibility tree on *every* action. That makes per-action cost O(n) in the size
of the page and total context growth O(n) in the number of actions, so a
ten-step flow routinely costs ~114,000 tokens.

Hound inverts that: tool responses are **budgeted**. The caller states a ceiling,
Hound returns the most useful representation of the page that fits, and reports
what it dropped. Cost per action is O(1) once the agent has a reference for the
elements it cares about.

Token counts here are *estimates* using the standard ~4 characters per token
heuristic. They are used for budgeting and for the benchmark report, never for
billing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

CHARS_PER_TOKEN = 4.0


def estimate_tokens(payload: Any) -> int:
    """Estimate the token cost of a payload.

    Uses a character-count heuristic rather than a real BPE tokenizer because
    the goal is a *budget decision* made in microseconds on every tool call, not
    an exact bill. A real tokenizer costs roughly 50-100x more than it is worth
    here, and the error is well under 15% for the mixed prose/ASCII payloads
    these tools emit.
    """
    if payload is None:
        return 0
    text = payload if isinstance(payload, str) else _compact_repr(payload)
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def _compact_repr(payload: Any) -> str:
    import json

    try:
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(payload)


class Profile(str, Enum):
    """How much of a page to return.

    The point of the light profile is that most agent actions (click, type,
    wait) do not need the page contents at all - they need confirmation that the
    click landed. Handing back a full tree anyway is pure waste.
    """

    MINIMAL = "minimal"
    """Confirmation only. Element refs and counts. No content, no structure.

    Cheapest option, and correct for the majority of actions in a real flow.
    """

    BALANCED = "balanced"
    """Interactive elements with their accessible names, plus visible text
    capped to a character allowance. This is the default."""

    FULL = "full"
    """Everything, including full element detail, still subject to the budget.

    A budget is a hard ceiling, not a suggestion, so FULL can still be clipped.
    A larger budget with FULL yields a richer page; a small budget with FULL
    degrades to BALANCED.
    """

    @property
    def max_elements(self) -> int:
        return {"minimal": 0, "balanced": 60, "full": 400}[self.value]

    @property
    def include_text(self) -> bool:
        return self is not Profile.MINIMAL

    @property
    def text_char_allowance(self) -> int:
        return {"minimal": 0, "balanced": 2_000, "full": 40_000}[self.value]


@dataclass
class Budget:
    """A token ceiling for one tool response.

    The default is deliberately tight. Agents that ask for the whole page on
    every step are the reason context windows fill up; making the cheap option
    the default is what actually changes behaviour.
    """

    max_tokens: int = 1_200
    profile: Profile = Profile.BALANCED
    hard_fail: bool = False
    """When true, content that cannot fit raises instead of being truncated."""


@dataclass
class BudgetReport:
    """What actually happened to the payload.

    Returned to the agent so it can tell the difference between "the page is
    small" and "Hound cut this response down". An agent that cannot tell those
    apart will assume it has seen the whole page and make bad decisions.
    """

    tokens_used: int = 0
    max_tokens: int = 0
    profile_requested: Profile = Profile.BALANCED
    profile_effective: Profile = Profile.BALANCED
    degraded: bool = False
    dropped_elements: int = 0
    truncated_text: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def utilisation(self) -> float:
        if not self.max_tokens:
            return 0.0
        return self.tokens_used / self.max_tokens

    @property
    def truncated(self) -> bool:
        return self.degraded or self.truncated_text or self.dropped_elements > 0

    def to_dict(self) -> dict:
        return {
            "tokens": self.tokens_used,
            "max_tokens": self.max_tokens,
            "profile": self.profile_effective.value,
            "profile_requested": self.profile_requested.value,
            "degraded": self.degraded,
            "dropped_elements": self.dropped_elements,
            "truncated_text": self.truncated_text,
            "utilisation": round(self.utilisation, 3),
            "notes": self.notes,
        }

    def render(self) -> str:
        """One-line footer the agent can read cheaply."""
        bits = [f"{self.tokens_used}/{self.max_tokens}tok"]
        if self.degraded:
            bits.append(f"degraded {self.profile_requested.value}->{self.profile_effective.value}")
        if self.dropped_elements:
            bits.append(f"{self.dropped_elements} elements omitted")
        if self.truncated_text:
            bits.append("text clipped")
        return " | ".join(bits)


class BudgetExceeded(ValueError):
    """Raised when a hard budget cannot fit even a minimal response."""


_RANK = {Profile.MINIMAL: 0, Profile.BALANCED: 1, Profile.FULL: 2}

# Degradation order: always try progressively cheaper representations.
DEGRADATION_ORDER = (Profile.BALANCED, Profile.MINIMAL)


def fit_to_budget(
    rendered: dict[str, Any],
    budget: Budget,
    *,
    rebuild: callable = None,
) -> tuple[dict[str, Any], BudgetReport]:
    """Clamp ``rendered`` until it fits ``budget``.

    ``rebuild`` is called with a narrower profile when the payload is too large,
    letting the caller regenerate a cheaper representation rather than having its
    structured data flattened into a string here.
    """
    report = BudgetReport(
        max_tokens=budget.max_tokens,
        profile_requested=budget.profile,
        profile_effective=budget.profile,
    )

    used = estimate_tokens(rendered)
    if used <= budget.max_tokens:
        report.tokens_used = used
        return rendered, report

    # Degrade one step at a time, never below MINIMAL, and never widening: asking
    # for MINIMAL should not silently upgrade the caller to BALANCED.
    profile = budget.profile
    for candidate in DEGRADATION_ORDER:
        if _RANK[candidate] >= _RANK[profile]:
            break
        if rebuild is None:
            break
        replacement = rebuild(candidate)
        if replacement is None:
            continue
        profile = candidate
        rendered = replacement
        report.profile_effective = candidate
        report.degraded = True
        used = estimate_tokens(rendered)
        if used <= budget.max_tokens:
            report.tokens_used = used
            return rendered, report

    if budget.hard_fail:
        raise BudgetExceeded(
            f"response needs {used} tokens but budget is {budget.max_tokens}"
        )

    # Even MINIMAL did not fit. Trim the oversized fields directly.
    rendered, report = _last_resort_trim(rendered, budget, report)
    report.tokens_used = estimate_tokens(rendered)
    if report.tokens_used > budget.max_tokens:
        report.notes.append("budget floor reached; response may exceed max_tokens")
    return rendered, report


def _last_resort_trim(
    rendered: dict[str, Any],
    budget: Budget,
    report: BudgetReport,
) -> tuple[dict[str, Any], BudgetReport]:
    clipped = dict(rendered)
    for key in ("text", "html", "body", "content"):
        if key in clipped and isinstance(clipped[key], str):
            allowance = int(budget.max_tokens * CHARS_PER_TOKEN / 2)
            if len(clipped[key]) > allowance:
                clipped[key] = clipped[key][:allowance] + " ...[clipped]"
                report.truncated_text = True
    if isinstance(clipped.get("elements"), list) and len(clipped["elements"]) > 5:
        clipped["elements"] = clipped["elements"][:5]
        report.dropped_elements = report.dropped_elements or 0
        report.notes.append("element list clipped to 5")
    return clipped, report
