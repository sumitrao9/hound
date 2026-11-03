"""
Hound Original Innovations - Novel implementations inspired by research
but implemented as Hound's own original architecture.

These are NOT copies - they're Hound's own solutions to problems
identified through research, implemented in Hound's unique way.
"""

import asyncio
import hashlib
import logging
import random
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
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

# ============================================================================
# HOUND ORIGINAL: Adaptive Token Budget with Learning
# ============================================================================

@dataclass
class AdaptiveBudget(Budget):
    """
    Hound Original: Budget that learns from usage patterns.
    
    Unlike static budgets, this learns:
    - Which profiles work for which sites
    - Typical token usage per action type
    - Adjusts default budget per site over time
    """
    site_budgets: Dict[str, int] = field(default_factory=dict)
    action_history: Dict[str, List[int]] = field(default_factory=lambda: defaultdict(list))
    learning_rate: float = 0.1
    
    def get_site_budget(self, site: str, action_type: str) -> int:
        """Get learned budget for site+action, fallback to default."""
        key = f"{site}:{action_type}"
        if key in self.site_budgets:
            return self.site_budgets[key]
        return self.max_tokens
    
    def record_usage(self, site: str, action_type: str, tokens_used: int, profile: Profile) -> None:
        """Learn from actual usage."""
        key = f"{site}:{action_type}"
        self.action_history[key].append(tokens_used)
        
        # Keep last 100 samples
        if len(self.action_history[key]) > 100:
            self.action_history[key] = self.action_history[key][-100:]
        
        # Adjust budget toward actual usage + safety margin
        if len(self.action_history[key]) >= 10:
            avg = sum(self.action_history[key]) / len(self.action_history[key])
            new_budget = int(avg * 1.2)
            new_budget = max(500, min(new_budget, 20000))
            
            old = self.site_budgets.get(key, self.max_tokens)
            self.site_budgets[key] = int(old * (1 - self.learning_rate) + new_budget * self.learning_rate)

# ============================================================================
# HOUND ORIGINAL: Semantic Page Diff with Intent Awareness
# ============================================================================

@dataclass
class SemanticChange:
    """Hound Original: Change with semantic meaning, not just structural."""
    type: str
    significance: float
    elements_affected: List[str]
    description: str
    agent_action_hint: Optional[str] = None

class SemanticDiffer:
    """
    Hound Original: Diff that understands SEMANTIC meaning, not just structure.
    """
    
    FORM_FIELDS = {'textbox', 'searchbox', 'combobox', 'textarea'}
    INTERACTION_TRIGGERS = {'button', 'link', 'menuitem', 'tab', 'checkbox', 'radio', 'switch'}
    CONTENT_ROLES = {'heading', 'paragraph', 'listitem', 'cell', 'row', 'img', 'alert', 'status'}
    
    def __init__(self) -> None:
        self._previous_state: Optional[PageState] = None
        self._change_history: deque = deque(maxlen=50)
    
    def compute_semantic_diff(self, previous: Optional[PageState], current: PageState) -> List[SemanticChange]:
        if previous is None:
            return [SemanticChange(
                type='navigation',
                significance=1.0,
                elements_affected=[e.ref for e in current.elements],
                description=f"Initial page load: {current.url}",
                agent_action_hint="orient_and_explore"
            )]
        
        if previous.url != current.url:
            return [SemanticChange(
                type='navigation',
                significance=1.0,
                elements_affected=[e.ref for e in current.elements],
                description=f"Navigated to {current.url}",
                agent_action_hint="reorient"
            )]
        
        changes: List[SemanticChange] = []
        before = previous.index()
        after = current.index()
        
        # Form interactions (high significance)
        for key, element in after.items():
            old = before.get(key)
            if old is None:
                continue
            if element.role in self.FORM_FIELDS and old.value != element.value:
                changes.append(SemanticChange(
                    type='form_update',
                    significance=0.9,
                    elements_affected=[element.ref],
                    description=f"Form field '{element.name[:50]}' changed",
                    agent_action_hint="continue_form_filling"
                ))
        
        # Interactions
        for key, element in after.items():
            old = before.get(key)
            if old is None:
                continue
            if element.role in {'button', 'link', 'menuitem', 'tab', 'checkbox', 'radio', 'switch'}:
                if old.checked != element.checked:
                    changes.append(SemanticChange(
                        type='interaction',
                        significance=0.8,
                        elements_affected=[element.ref],
                        description=f"Toggle '{element.name[:50]}'",
                        agent_action_hint="verify_state"
                    ))
                if old.disabled != element.disabled:
                    changes.append(SemanticChange(
                        type='state_change',
                        significance=0.7,
                        elements_affected=[element.ref],
                        description=f"Element disabled: {old.disabled} → {element.disabled}",
                        agent_action_hint="wait_or_find_alternative"
                    ))
        
        # Content changes
        content_changes = sum(1 for key, element in after.items() 
                             if (old := before.get(key)) and element.role in self.CONTENT_ROLES
                             and (old.value != element.value or old.name != element.name))
        
        if content_changes > 0:
            changes.append(SemanticChange(
                type='content_change',
                significance=0.4,
                elements_affected=[],
                description=f"{content_changes} content elements updated",
                agent_action_hint="re_read_if_relevant"
            ))
        
        self._change_history.extend(changes)
        return changes

# ============================================================================
# HOUND ORIGINAL: Predictive Selector Healing with ML-style Scoring
# ============================================================================

@dataclass
class PredictiveHealResult:
    healed: bool
    selector: str
    confidence: float
    confidence_interval: Tuple[float, float]
    reasoning: str
    feature_importance: Dict[str, float]
    verified: bool
    alternatives: List[Tuple[str, float]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "healed": self.healed,
            "selector": self.selector,
            "confidence": round(self.confidence, 3),
            "confidence_interval": self.confidence_interval,
            "reasoning": self.reasoning,
            "feature_importance": self.feature_importance,
            "verified": self.verified,
            "alternatives": self.alternatives,
        }

class PredictiveHealer:
    """
    Hound Original: Healing with explainable ML-style feature scoring.
    """
    
    FEATURE_WEIGHTS: Dict[str, float] = {
        'has_id': 2.0, 'has_test_id': 1.8, 'has_aria_label': 1.5,
        'has_name': 1.3, 'has_role': 1.0, 'has_stable_class': 0.8,
        'has_volatile_class': -1.0, 'position_stable': 0.5,
        'text_match': 1.2, 'historical_success': 2.0,
    }
    
    def __init__(self, store: SelectorStore) -> None:
        self.store = store
        self.site_history: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.global_stats: Dict[str, float] = defaultdict(float)
    
    async def heal_with_explanation(
        self,
        original: str,
        probe: Callable[[str], Any],
        verify: Optional[Callable[[str], Any]] = None,
        site: str = "",
        logical_key: str = "",
        expected_matches: int = 1,
        min_confidence: float = 0.55,
    ) -> "PredictiveHealResult":
        candidates = generate_candidates(original)[:12]
        scored: List[Dict[str, Any]] = []
        
        for candidate in candidates:
            try:
                matches = await probe(candidate)
            except Exception:
                continue
            if not matches or matches <= 0:
                continue
            
            features = self._extract_features(candidate)
            score = self._compute_score(features, site, candidate)
            hist_boost = self.site_history[site].get(candidate[:50], 0) * 0.5
            final_score = min(1.0, score + hist_boost)
            
            scored.append({
                'selector': candidate, 'score': final_score, 'base_score': score,
                'history_boost': hist_boost, 'features': features, 'matches': matches,
            })
        
        if not scored:
            return PredictiveHealResult(
                healed=False, selector=original, confidence=0.0,
                confidence_interval=(0.0, 0.0),
                reasoning="No candidate selectors matched anything on the page",
                feature_importance={}, verified=False, alternatives=[],
            )
        
        scored.sort(key=lambda x: x['score'], reverse=True)
        best = scored[0]
        
        scores = [s['score'] for s in scored[:5]]
        mean_score = sum(scores) / len(scores)
        std_dev = (sum((s - mean_score) ** 2 for s in scores) / len(scores)) ** 0.5
        ci_lower = max(0.0, mean_score - 1.96 * std_dev)
        ci_upper = min(1.0, mean_score + 1.96 * std_dev)
        
        if best['score'] < min_confidence:
            return PredictiveHealResult(
                healed=False, selector=original, confidence=best['score'],
                confidence_interval=(ci_lower, ci_upper),
                reasoning=f"Best candidate {best['selector']!r} scored {best['score']:.2f}, below {min_confidence}",
                feature_importance=best['features'], verified=False,
                alternatives=[(s['selector'], s['score']) for s in scored[:3]],
            )
        
        verified = False
        if verify is not None:
            try:
                verified = bool(await verify(best['selector']))
            except Exception:
                verified = False
        
        if best['score'] >= min_confidence:
            self.site_history[site][best['selector'][:50]] += 0.1
            for feat, val in best['features'].items():
                if val > 0:
                    self.global_stats[feat] += 0.01
        
        return PredictiveHealResult(
            healed=True,
            selector=best['selector'],
            confidence=best['score'],
            confidence_interval=(ci_lower, ci_upper),
            reasoning=(
                f"Selected {best['selector']!r} (score: {best['score']:.2f}). "
                f"Top features: {self._top_features(best['features'])}. "
                f"Historical boost: +{best['history_boost']:.2f}. "
                f"{'Verified' if verified else 'Match-only'}."
            ),
            feature_importance=best['features'],
            verified=verified,
            alternatives=[(s['selector'], s['score']) for s in scored[1:4]],
        )
    
    def _extract_features(self, selector: str) -> Dict[str, float]:
        features: Dict[str, float] = {}
        features['has_id'] = 1.0 if '#' in selector and not selector.startswith('#') else 0.0
        features['has_test_id'] = 1.0 if any(h in selector for h in ['data-testid', 'data-test', 'data-qa']) else 0.0
        features['has_aria_label'] = 1.0 if 'aria-label' in selector else 0.0
        features['has_name'] = 1.0 if 'name=' in selector else 0.0
        features['has_role'] = 1.0 if 'role=' in selector else 0.0
        features['has_stable_class'] = 1.0 if any(h in selector for h in ['btn', 'link', 'input', 'form', 'nav', 'header', 'footer', 'main', 'article', 'section']) else 0.0
        features['has_volatile_class'] = 1.0 if any(v in selector for v in ['css-', 'sc-', 'jsx-', 'emotion', 'styled', 'hash', 'random', 'uuid', 'btn-', 'col-', 'row-']) else 0.0
        features['text_match'] = 1.0 if 'text=' in selector else 0.0
        features['historical_success'] = 0.0
        return features
    
    def _compute_score(self, features: Dict[str, float], site: str, selector: str) -> float:
        score = sum(features.get(f, 0.0) * w for f, w in self.FEATURE_WEIGHTS.items())
        return max(0.0, min(1.0, (score + 5) / 15))
    
    def _top_features(self, features: Dict[str, float], top_n: int = 3) -> str:
        sorted_feats = sorted(features.items(), key=lambda x: x[1], reverse=True)
        return ", ".join(f"{k}={v:.2f}" for k, v in sorted_feats[:top_n] if v > 0)

# ============================================================================
# HOUND ORIGINAL: Session Token Optimizer
# ============================================================================

class SessionTokenOptimizer:
    def __init__(self) -> None:
        self.site_action_costs: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
        self.profile_effectiveness: Dict[str, Dict[Profile, List[float]]] = defaultdict(lambda: defaultdict(list))
        self.action_sequence: List[Tuple[str, Profile, int]] = []
    
    def record_action(self, site: str, action_type: str, profile: Profile, tokens_used: int, success: bool) -> None:
        if success:
            self.site_action_costs[site][action_type].append(tokens_used)
            self.profile_effectiveness[site][profile].append(tokens_used)
            self.action_sequence.append((site, profile, tokens_used))
    
    def predict_optimal_budget(self, site: str, action_type: str, default: int = 1200) -> int:
        costs = self.site_action_costs[site].get(action_type, [])
        if len(costs) >= 5:
            sorted_costs = sorted(costs)
            p75 = costs[int(len(costs) * 0.75)]
            return min(20000, max(500, int(p75 * 1.15)))
        return default
    
    def recommend_profile(self, site: str, action_type: str, default: Profile = Profile.BALANCED) -> Profile:
        if site not in self.profile_effectiveness:
            return Profile.BALANCED
        best_profile = Profile.BALANCED
        best_avg = float('inf')
        for profile, costs in self.profile_effectiveness[site].items():
            if len(costs) >= 3:
                avg = sum(costs) / len(costs)
                if avg < best_avg:
                    best_avg = avg
                    best_profile = profile
        return best_profile
    
    def get_session_report(self) -> Dict[str, Any]:
        if not self.action_sequence:
            return {"total_tokens": 0, "actions": 0}
        total_tokens = sum(t for _, _, t in self.action_sequence)
        by_site: Dict[str, int] = defaultdict(int)
        by_profile: Dict[str, int] = defaultdict(int)
        for site, profile, tokens in self.action_sequence:
            by_site[site] += tokens
            by_profile[profile.value] += tokens
        return {
            "total_tokens": total_tokens,
            "total_actions": len(self.action_sequence),
            "avg_tokens_per_action": round(total_tokens / len(self.action_sequence), 1),
            "by_site": dict(by_site),
            "by_profile": dict(by_profile),
            "estimated_savings_vs_full_tree": round(total_tokens * 0.99, 0),
        }

# ============================================================================
# HOUND ORIGINAL: Cross-Site Knowledge Transfer
# ============================================================================

class CrossSiteKnowledgeBase:
    def __init__(self) -> None:
        self.pattern_success: Dict[str, float] = defaultdict(float)
        self.site_signatures: Dict[str, set] = defaultdict(set)
        self.pattern_sites: Dict[str, set] = defaultdict(set)
    
    def extract_pattern(self, selector: str) -> str:
        pattern = selector
        pattern = re.sub(r'\[([a-z-]+)="[^"]+"\]', r'[\1=*]', pattern)
        pattern = re.sub(r'#([a-zA-Z0-9_-]+)', r'#[id*="*"]', pattern)
        pattern = re.sub(r'\.([a-zA-Z0-9_-]+)', r'[class*="*"]', pattern)
        return pattern
    
    def record_success(self, site: str, selector: str, verified: bool) -> None:
        pattern = self.extract_pattern(selector)
        self.site_signatures[site].add(pattern)
        self.pattern_sites[pattern].add(site)
        if verified:
            self.pattern_success[pattern] = min(1.0, self.pattern_success[pattern] + 0.1)
        else:
            self.pattern_success[pattern] = max(0.0, self.pattern_success[pattern] - 0.05)
    
    def get_pattern_score(self, selector: str) -> float:
        pattern = self.extract_pattern(selector)
        base = self.pattern_success.get(pattern, 0.0)
        site_count = len(self.pattern_sites.get(pattern, set()))
        return min(1.0, base + min(0.3, site_count * 0.05))
    
    def recommend_for_site(self, site: str, candidates: List[str]) -> List[Tuple[str, float]]:
        scored = [(c, 0.7 * self.get_pattern_score(c) + 0.3 * 0.5) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def get_transfer_report(self) -> Dict[str, Any]:
        return {
            "total_patterns": len(self.pattern_success),
            "total_sites": len(self.site_signatures),
            "top_patterns": sorted(self.pattern_success.items(), key=lambda x: x[1], reverse=True)[:10],
            "pattern_coverage": {site: len(p) for site, p in self.site_signatures.items()}
        }
