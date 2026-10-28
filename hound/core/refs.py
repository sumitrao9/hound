"""Stable element references and delta snapshots.

The second half of the token problem.

Even a perfect capture profile still re-describes the whole page on every call.
The agent pays for the banner, the nav, the sidebar and the footer *again* on
every single action, even though none of it changed.

Hound assigns each interactive element a short stable reference (``e1``, ``e2``)
and remembers the previous page state. On the next call it emits only what
changed, so a click that moves one element costs a few dozen tokens instead of
ten thousand.

This is why per-action cost is O(1) for Hound and O(n) for a snapshot-per-action
server.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from hound.core.budget import Profile

# Roles worth exposing. Everything else is noise as far as an agent is
# concerned, and noise is what exhausts context windows.
INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "searchbox",
    "combobox",
    "checkbox",
    "radio",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "tab",
    "option",
    "switch",
    "slider",
    "spinbutton",
}

# Roles that carry meaning even though they are not interactive.
SEMANTIC_ROLES = {
    "heading",
    "alert",
    "dialog",
    "status",
    "table",
    "row",
    "cell",
    "form",
    "navigation",
    "main",
    "banner",
    "contentinfo",
    "list",
    "listitem",
    "img",
    "progressbar",
}


@dataclass(frozen=True)
class Element:
    """One addressable node on a page."""

    role: str
    name: str
    ref: str = ""
    value: str = ""
    disabled: bool = False
    checked: bool | None = None
    selector: str = ""

    @property
    def interactive(self) -> bool:
        return self.role in INTERACTIVE_ROLES

    @property
    def identity(self) -> str:
        """Stable key used to match an element across snapshots.

        Deliberately excludes both position and ``value``. Excluding position
        means an unrelated insertion above the element does not invalidate the
        ref the agent is holding; excluding value means a textbox whose contents
        change is reported as a state change rather than as one element vanishing
        and another appearing.
        """
        return f"{self.role}|{_normalise(self.name)}"

    def to_compact(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ref": self.ref, "role": self.role}
        if self.name:
            out["name"] = self.name[:120]
        if self.value:
            out["value"] = self.value[:120]
        if self.disabled:
            out["disabled"] = True
        if self.checked is not None:
            out["checked"] = self.checked
        return out

    def to_verbose(self) -> dict[str, Any]:
        out = self.to_compact()
        if self.selector:
            out["selector"] = self.selector
        return out


def _normalise(value: str) -> str:
    return " ".join((value or "").lower().split())


def short_hash(identity: str, length: int = 6) -> str:
    return hashlib.blake2s(identity.encode("utf-8"), digest_size=8).hexdigest()[:length]


@dataclass
class PageState:
    """The remembered shape of a page, used to compute the next delta."""

    url: str = ""
    title: str = ""
    text: str = ""
    elements: list[Element] = field(default_factory=list)
    signature: str = ""

    def index(self) -> dict[str, Element]:
        return {e.identity: e for e in self.elements}

    def ordered(self, profile) -> list[Element]:
        """Elements sorted so that truncation keeps what matters.

        Headings and dialogs carry the structure an agent needs to orient
        itself; interactive elements are what it can act on; everything else is
        only worth including under a generous budget.
        """
        tier = {"heading": 0, "alert": 0, "dialog": 0, "status": 0, "navigation": 1, "main": 1}
        if profile is Profile.MINIMAL:
            return [e for e in self.elements if e.interactive]

        def key(element: Element) -> tuple:
            return (tier.get(element.role, 2 if not element.interactive else 1), element.ref)

        return sorted(self.elements, key=key)

    def render(self, profile) -> dict[str, Any]:
        """Build the payload for a profile, ordered so truncation keeps the
        most important elements (headings, then interactive) rather than whatever
        happened to appear first in the DOM."""
        ordered = self.ordered(profile)
        cap = profile.max_elements
        selected = ordered[:cap] if cap else ordered
        return {
            "url": self.url,
            "title": self.title,
            "elements": [
                e.to_verbose() if profile is Profile.FULL else e.to_compact() for e in selected
            ],
        }


def build_state(
    url: str,
    title: str,
    text: str,
    elements: Iterable[dict[str, Any]],
) -> PageState:
    """Build a PageState, assigning stable refs to every element."""
    materialised: list[Element] = []
    for index, raw in enumerate(elements):
        element = Element(
            role=(raw.get("role") or "generic").lower(),
            name=(raw.get("name") or "").strip()[:200],
            ref=f"e{index + 1}",
            value=(raw.get("value") or "").strip()[:200],
            disabled=bool(raw.get("disabled")),
            checked=raw.get("checked"),
            selector=raw.get("selector", ""),
        )
        materialised.append(element)

    state = PageState(
        url=url,
        title=title,
        text=text,
        elements=materialised,
    )
    state.signature = signature_of(url, materialised)
    return state


def signature_of(url: str, elements: Iterable[Element]) -> str:
    """A short hash of the page's identity, structure and field values.

    Used as a fast path to skip diffing when nothing moved at all, so it must
    cover everything ``diff`` looks at. It includes ``value`` even though
    ``identity`` does not: a form field whose contents changed has not changed
    identity, but it definitely has changed state.
    """
    parts = [url]
    for element in elements:
        parts.append(f"{element.identity}={element.value}")
    return short_hash("|".join(parts), length=12)


def diff(previous: PageState | None, current: PageState) -> dict[str, Any]:
    """Compute what changed between two page states.

    ``navigated`` is the important signal: a navigation voids every element ref
    the agent is holding, so the caller must fall back to a full snapshot rather
    than a delta even when the new page happens to share elements with the old.
    """
    if previous is None:
        return {
            "navigated": True,
            "url_changed": False,
            "added": [e.to_compact() for e in current.elements],
            "removed": [],
            "changed": [],
            "unchanged_count": 0,
        }

    navigated = previous.url != current.url
    if previous.signature == current.signature:
        return {
            "navigated": False,
            "url_changed": False,
            "added": [],
            "removed": [],
            "changed": [],
            "unchanged_count": len(current.elements),
        }

    before = previous.index()
    after = current.index()

    added = [e.to_compact() for e in current.elements if e.identity not in before]
    removed = [before[k].to_compact() for k in before if k not in after]
    changed = []
    for key, element in after.items():
        old = before.get(key)
        if old is None:
            continue
        if old.value != element.value or old.checked != element.checked or (
            old.disabled != element.disabled
        ):
            changed.append(
                {
                    "ref": element.ref,
                    "name": element.name[:120] or None,
                    "from": {
                        "value": old.value[:60],
                        "checked": old.checked,
                        "disabled": old.disabled,
                    },
                    "to": {
                        "value": element.value[:60],
                        "checked": element.checked,
                        "disabled": element.disabled,
                    },
                }
            )

    return {
        "navigated": navigated,
        "url_changed": navigated,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": len(after) - len(added),
    }
