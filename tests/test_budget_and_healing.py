"""Tests for the token budget engine and the delta/diff behaviour.

These are the load-bearing tests of the project: if the budget or the delta
stopped working, the entire premise of Hound would be false. The browser-backed
behaviour is exercised separately in ``test_engine_live.py``.
"""

import json

import pytest

from hound.core.budget import (
    Budget,
    BudgetExceeded,
    Profile,
    estimate_tokens,
    fit_to_budget,
)
from hound.core.refs import build_state, diff, short_hash
from hound.healing.selectors import (
    SelectorStore,
    generate_candidates,
    heal,
    score_candidate,
)


# -- budget ----------------------------------------------------------------


def test_estimate_tokens_is_positive_and_scales():
    small = estimate_tokens("hello")
    large = estimate_tokens("hello" * 1000)
    assert small > 0
    assert large > small * 100


def test_estimate_tokens_handles_structures():
    assert estimate_tokens(None) == 0
    assert estimate_tokens({"a": 1}) > 0
    assert estimate_tokens([1, 2, 3]) > 0


def test_response_within_budget_is_untouched():
    payload = {"url": "https://example.com", "elements": [{"ref": "e1", "role": "button"}]}
    report_budget = Budget(max_tokens=10_000)
    out, report = fit_to_budget(payload, report_budget)
    assert out == payload
    assert report.tokens_used <= 10_000
    assert report.degraded is False
    assert report.profile_effective is Profile.BALANCED


def test_oversized_response_degrades_to_a_cheaper_profile():
    payload = {"elements": [{"ref": f"e{i}", "role": "link", "name": "x" * 400} for i in range(200)]}
    budget = Budget(max_tokens=200, profile=Profile.FULL)

    def rebuild(profile: Profile):
        if profile is Profile.MINIMAL:
            return {"elements": [{"ref": f"e{i}", "role": "link"} for i in range(5)]}
        if profile is Profile.BALANCED:
            return {"elements": [{"ref": f"e{i}", "role": "link", "name": "x" * 40} for i in range(20)]}
        return None

    out, report = fit_to_budget(payload, budget, rebuild=rebuild)
    assert report.tokens_used <= 200
    assert report.degraded is True
    assert report.profile_effective is Profile.MINIMAL


def test_minimal_request_is_never_upgraded_by_degradation():
    payload = {"elements": [{"ref": f"e{i}", "name": "y" * 500} for i in range(50)]}
    budget = Budget(max_tokens=100, profile=Profile.MINIMAL)
    out, report = fit_to_budget(payload, budget, rebuild=lambda p: {"elements": []})
    assert report.profile_effective is Profile.MINIMAL
    assert report.profile_requested is Profile.MINIMAL


def test_hard_fail_raises_when_nothing_fits():
    payload = {"text": "z" * 20_000}
    budget = Budget(max_tokens=10, profile=Profile.MINIMAL, hard_fail=True)
    with pytest.raises(BudgetExceeded):
        fit_to_budget(payload, budget, rebuild=lambda p: None)


def test_last_resort_trims_oversized_text():
    payload = {"text": "a" * 50_000, "url": "https://x.test"}
    budget = Budget(max_tokens=100, profile=Profile.MINIMAL)
    out, report = fit_to_budget(payload, budget, rebuild=lambda p: None)
    assert report.truncated_text is True
    assert len(out["text"]) < 50_000
    assert out["url"] == "https://x.test"


def test_budget_report_serialises_and_renders():
    _, report = fit_to_budget({"a": "b" * 100}, Budget(max_tokens=1_000))
    data = report.to_dict()
    assert set(data) >= {"tokens", "max_tokens", "profile", "degraded", "utilisation"}
    assert "tok" in report.render()


# -- refs and deltas -------------------------------------------------------


def _sample(n=30):
    return [
        {"role": "link", "name": f"Item {i}", "selector": f"a.item-{i}"}
        for i in range(n)
    ]


def test_refs_are_assigned_and_stable():
    first = build_state("https://x.test", "T", "body", _sample())
    second = build_state("https://x.test", "T", "body", _sample())
    assert [e.ref for e in first.elements][:3] == ["e1", "e2", "e3"]
    assert first.signature == second.signature


def test_signature_changes_when_an_element_changes():
    a = build_state("https://x.test", "T", "body", _sample())
    elements = _sample()
    elements[3]["name"] = "Renamed"
    b = build_state("https://x.test", "T", "body", elements)
    assert a.signature != b.signature


def test_delta_reports_a_renamed_element_as_add_plus_remove():
    """Identity is role+name+value, so a rename is genuinely a different node.

    Reporting it as remove+add is correct: the old ref is gone and the new
    element has never been seen, so the agent must not assume continuity.
    """
    before = build_state("https://x.test", "T", "body", _sample(30))
    after_elements = _sample(30)
    after_elements[5]["name"] = "Changed"
    after = build_state("https://x.test", "T", "body", after_elements)

    result = diff(before, after)
    assert result["navigated"] is False
    assert len(result["added"]) == 1
    assert len(result["removed"]) == 1
    assert result["added"][0]["name"] == "Changed"
    assert result["unchanged_count"] == 29


def test_delta_reports_a_value_change_on_a_stable_element():
    before = build_state(
        "https://x.test", "T", "body", [{"role": "textbox", "name": "Search", "value": ""}]
    )
    after = build_state(
        "https://x.test", "T", "body", [{"role": "textbox", "name": "Search", "value": "django"}]
    )
    result = diff(before, after)
    assert result["navigated"] is False
    assert len(result["changed"]) == 1
    assert result["changed"][0]["to"]["value"] == "django"
    assert result["added"] == []


def test_identical_pages_produce_an_empty_delta():
    before = build_state("https://x.test", "T", "body", _sample(10))
    after = build_state("https://x.test", "T", "body", _sample(10))
    result = diff(before, after)
    assert result["added"] == []
    assert result["removed"] == []
    assert result["changed"] == []
    assert result["unchanged_count"] == 10


def test_first_snapshot_is_treated_as_navigation():
    current = build_state("https://x.test", "T", "body", _sample(5))
    result = diff(None, current)
    assert result["navigated"] is True
    assert len(result["added"]) == 5


def test_navigation_is_flagged_so_refs_are_not_trusted():
    before = build_state("https://x.test", "T", "body", _sample())
    after = build_state("https://y.test", "U", "body", _sample())
    result = diff(before, after)
    assert result["navigated"] is True
    assert result["url_changed"] is True


def test_added_and_removed_elements_are_detected():
    before = build_state("https://x.test", "T", "body", _sample(10))
    after = build_state("https://x.test", "T", "body", _sample(15))
    result = diff(before, after)
    assert len(result["added"]) == 5
    assert len(result["removed"]) == 0


def test_minimal_profile_returns_only_interactive_elements():
    state = build_state(
        "https://x.test",
        "T",
        "body",
        [
            {"role": "heading", "name": "Title"},
            {"role": "button", "name": "Go"},
            {"role": "generic", "name": "blob"},
        ],
    )
    minimal = state.render(Profile.MINIMAL)
    roles = {e["role"] for e in minimal["elements"]}
    assert roles == {"button"}


def test_full_profile_includes_selectors():
    state = build_state("https://x.test", "T", "body", _sample(3))
    full = state.render(Profile.FULL)
    assert all("selector" in e for e in full["elements"])


def test_balanced_profile_caps_element_count():
    state = build_state("https://x.test", "T", "body", _sample(500))
    balanced = state.render(Profile.BALANCED)
    assert len(balanced["elements"]) == Profile.BALANCED.max_elements


def test_headings_survive_truncation_over_generic_nodes():
    elements = [{"role": "generic", "name": f"blob {i}"} for i in range(200)]
    elements.insert(0, {"role": "heading", "name": "Important Heading"})
    state = build_state("https://x.test", "T", "body", elements)
    rendered = state.render(Profile.BALANCED)["elements"]
    assert any(e["role"] == "heading" for e in rendered)


def test_short_hash_is_deterministic():
    assert short_hash("abc") == short_hash("abc")
    assert short_hash("abc") != short_hash("abd")


def test_identity_ignores_position():
    from hound.core.refs import Element

    a = Element(role="button", name="Save")
    b = Element(role="button", name="save")
    assert a.identity == b.identity


# -- healing ---------------------------------------------------------------


def test_candidates_are_derived_from_the_original_selector():
    """Healing can only re-derive attributes the original already carried.

    It has no way to invent a testid value it was never given, so candidates are
    always grounded in the broken selector itself.
    """
    original = 'div.css-1x2y3 > button[data-testid="submit"]'
    candidates = generate_candidates(original)
    assert '[data-testid="submit"]' in candidates
    assert candidates[0] == '[data-testid="submit"]', "most durable candidate first"
    assert original not in candidates


def test_candidates_include_aria_label_and_text():
    assert '[aria-label="Close"]' in generate_candidates('text="Close"')
    assert any("Close" in c for c in generate_candidates("text=Close"))


def test_candidates_narrow_from_class_chains_to_the_target_tag():
    candidates = generate_candidates("div.wrapper.inner > span.label > button.go")
    assert "button" in candidates, "the target is the last segment, not the first"
    assert "button.go" in candidates
    assert "div" not in candidates, "candidates must not target the wrong element"
    assert candidates.index("button") == len(candidates) - 1, "bare tag is the last resort"


def test_candidates_never_include_the_original():
    original = "div.wrapper > span.label"
    assert original not in generate_candidates(original)


def test_volatile_selectors_score_lower():
    stable = score_candidate('[data-testid="submit"]', matches=1)
    volatile = score_candidate("div.css-1x2y3z", matches=1)
    assert stable > volatile


def test_non_unique_match_scores_lower_than_unique():
    unique = score_candidate('[data-testid="submit"]', matches=1)
    everything = score_candidate("div", matches=400)
    assert unique > everything


def test_heal_adopts_a_verified_candidate():
    original = 'div.css-1x2y3 > button[data-testid="submit"]'
    outcome = heal(
        original,
        probe=lambda c: 1 if c == '[data-testid="submit"]' else 0,
        verify=lambda c: True,
    )
    assert outcome.healed is True
    assert outcome.selector == '[data-testid="submit"]'
    assert outcome.verified is True
    assert outcome.confidence > 0.5


def test_heal_refuses_to_adopt_when_verification_fails():
    original = 'div.css-1x2y3 > button[data-testid="submit"]'
    outcome = heal(
        original,
        probe=lambda c: 1 if c == '[data-testid="submit"]' else 0,
        verify=lambda c: False,
    )
    assert outcome.healed is True
    assert outcome.verified is False
    assert "not verified" in outcome.detail


def test_heal_gives_up_when_nothing_matches():
    outcome = heal("div.gone", probe=lambda c: 0, verify=lambda c: True)
    assert outcome.healed is False
    assert outcome.confidence == 0.0


def test_heal_refuses_low_confidence_candidates():
    outcome = heal(
        "div.wrapper",
        probe=lambda c: 50 if c == "div" else 0,
        verify=lambda c: True,
        min_confidence=0.9,
    )
    assert outcome.healed is False
    assert "threshold" in outcome.detail


def test_heal_explains_itself_when_it_cannot_heal():
    outcome = heal("div.wrapper", probe=lambda c: 0, verify=lambda c: True)
    assert "no candidate selector matched" in outcome.detail
    assert outcome.selector == "div.wrapper", "must not claim a selector it never verified"


def test_heal_survives_a_raising_probe():
    def probe(candidate):
        raise RuntimeError("bad selector")

    outcome = heal("div.x", probe=probe, verify=lambda c: True)
    assert outcome.healed is False


# -- selector store --------------------------------------------------------


def test_store_round_trips_an_override():
    from hound.healing.selectors import HealingOutcome

    store = SelectorStore(":memory:")
    outcome = HealingOutcome(
        healed=True,
        original="div.old",
        selector='[data-testid="go"]',
        confidence=0.9,
        verified=True,
    )
    store.record_heal(outcome, site="example.com", logical_key="submit")
    assert store.get("example.com", "submit") == '[data-testid="go"]'
    assert store.get("other.com", "submit") is None
    assert store.stats() == {"overrides": 1, "verified": 1, "unverified": 0}


def test_store_heal_increments_hits():
    from hound.healing.selectors import HealingOutcome

    store = SelectorStore(":memory:")
    for _ in range(3):
        store.record_heal(
            HealingOutcome(True, "div.old", "[data-testid='go']", 0.9, True),
            site="example.com",
            logical_key="submit",
        )
    row = store.history("example.com")
    assert len(row) == 3


def test_store_marks_an_override_unverified_on_repeat_failure():
    from hound.healing.selectors import HealingOutcome

    store = SelectorStore(":memory:")
    store.record_heal(
        HealingOutcome(True, "div.old", "[data-testid='go']", 0.9, True),
        site="example.com",
        logical_key="submit",
    )
    store.record_miss("example.com", "submit")
    stats = store.stats()
    assert stats["verified"] == 0
    assert stats["unverified"] == 1


def test_store_persists_across_instances(tmp_path):
    from hound.healing.selectors import HealingOutcome

    path = str(tmp_path / "selectors.db")
    store = SelectorStore(path)
    store.record_heal(
        HealingOutcome(True, "div.old", "[data-testid='go']", 0.9, True),
        site="example.com",
        logical_key="submit",
    )
    store.close()

    reopened = SelectorStore(path)
    assert reopened.get("example.com", "submit") == "[data-testid='go']"
    reopened.close()
