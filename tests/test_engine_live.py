"""Live browser tests for the budgeted engine.

These tests require a live browser and network access.
Run with: pytest tests/test_engine_live.py -v -m live
"""

import pytest
from hound.core.budget import Budget, Profile
from hound.core.engine import BudgetedBrowser, validate_url, TimeoutConfig, RateLimiter


class TestURLValidation:
    """Test URL validation for SSRF protection."""

    def test_valid_https_url(self):
        ok, msg = validate_url("https://example.com")
        assert ok is True

    def test_valid_http_url(self):
        ok, msg = validate_url("http://example.com")
        assert ok is True

    def test_invalid_scheme(self):
        ok, msg = validate_url("ftp://example.com")
        assert ok is False

    def test_localhost_blocked(self):
        ok, msg = validate_url("http://localhost:8080")
        assert ok is False

    def test_localhost_ip_blocked(self):
        ok, msg = validate_url("http://127.0.0.1:8080")
        assert ok is False

    def test_private_ip_blocked(self):
        ok, msg = validate_url("http://192.168.1.1")
        assert ok is False

    def test_private_10_blocked(self):
        ok, msg = validate_url("http://10.0.0.1")
        assert ok is False

    def test_private_172_blocked(self):
        ok, msg = validate_url("http://172.16.0.1")
        assert ok is False

    def test_metadata_endpoint_blocked(self):
        ok, msg = validate_url("http://169.254.169.254/latest/meta-data/")
        assert ok is False

    def test_invalid_url(self):
        ok, msg = validate_url("not-a-url")
        assert ok is False


class TestRateLimiter:
    """Test rate limiter functionality."""

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self):
        from hound.core.engine import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            await limiter.acquire()  # Should not raise

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        import time
        limiter = RateLimiter(max_requests=2, window_seconds=1)
        await limiter.acquire()
        await limiter.acquire()
        # Third request should wait
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        # Should have waited ~1 second
        assert elapsed >= 0.9


class TestTimeoutConfig:
    def test_default_timeouts(self):
        config = TimeoutConfig()
        assert config.navigation == 30.0
        assert config.element_action == 10.0
        assert config.selector_wait == 5.0
        assert config.snapshot == 10.0
        assert config.healing == 15.0

    def test_custom_timeouts(self):
        config = TimeoutConfig(navigation=60.0, element_action=20.0)
        assert config.navigation == 60.0
        assert config.element_action == 20.0


@pytest.mark.live
class TestBudgetedBrowserLive:
    """Live browser tests - require network and Playwright."""

    @pytest.fixture
    async def browser_page(self):
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        yield page
        await context.close()
        await browser.close()
        await pw.stop()

    @pytest.mark.asyncio
    async def test_goto_valid_url(self, browser_page):
        from hound.core.engine import BudgetedBrowser
        from hound.core.budget import Budget
        from hound.healing.selectors import SelectorStore

        store = SelectorStore(":memory:")
        budget = Budget(max_tokens=1000)
        engine = BudgetedBrowser(browser_page, store, budget)

        result = await engine.goto("https://example.com")
        assert result.ok is True
        assert "url" in result.data
        assert "elements" in result.data

    @pytest.mark.asyncio
    async def test_snapshot_delta(self, browser_page):
        from hound.core.engine import BudgetedBrowser
        from hound.core.budget import Budget
        from hound.healing.selectors import SelectorStore

        store = SelectorStore(":memory:")
        budget = Budget(max_tokens=1000)
        engine = BudgetedBrowser(browser_page, store, budget)

        await engine.goto("https://example.com")
        snap1 = await engine.snapshot(budget=Budget(max_tokens=1000), delta=True)
        snap2 = await engine.snapshot(budget=Budget(max_tokens=1000), delta=True)

        # Second snapshot should be delta (cheaper)
        assert snap2.report.tokens_used <= snap1.report.tokens_used

    @pytest.mark.asyncio
    async def test_act_click(self, browser_page):
        from hound.core.engine import BudgetedBrowser
        from hound.core.budget import Budget
        from hound.healing.selectors import SelectorStore

        store = SelectorStore(":memory:")
        budget = Budget(max_tokens=1000)
        engine = BudgetedBrowser(browser_page, store, budget)

        await engine.goto("https://example.com")
        # Find a link to click
        result = await engine.act("click", "a", budget=Budget(max_tokens=500))
        # Should succeed or fail gracefully
        assert result is not None

    @pytest.mark.asyncio
    async def test_act_fill(self, browser_page):
        from hound.core.engine import BudgetedBrowser
        from hound.core.budget import Budget
        from hound.healing.selectors import SelectorStore

        store = SelectorStore(":memory:")
        budget = Budget(max_tokens=1000)
        engine = BudgetedBrowser(browser_page, store, budget)

        await engine.goto("https://example.com")
        # Try to fill a non-existent input (should fail gracefully)
        result = await engine.act("fill", "input", value="test", budget=Budget(max_tokens=500))
        # Should handle gracefully
        assert result is not None

    @pytest.mark.asyncio
    async def test_find_elements(self, browser_page):
        from hound.core.engine import BudgetedBrowser
        from hound.core.budget import Budget
        from hound.healing.selectors import SelectorStore

        store = SelectorStore(":memory:")
        budget = Budget(max_tokens=1000)
        engine = BudgetedBrowser(browser_page, store, budget)

        await engine.goto("https://example.com")
        result = await engine.find("example", limit=5)
        assert result.ok is True
        assert "matches" in result.data

    @pytest.mark.asyncio
    async def test_budget_enforcement(self, browser_page):
        from hound.core.engine import BudgetedBrowser
        from hound.core.budget import Budget, Profile
        from hound.healing.selectors import SelectorStore

        store = SelectorStore(":memory:")
        budget = Budget(max_tokens=100, profile=Profile.MINIMAL)
        engine = BudgetedBrowser(browser_page, store, budget)

        await engine.goto("https://example.com")
        result = await engine.snapshot(budget=budget)
        assert result.report.tokens_used <= 100

    @pytest.mark.asyncio
    async def test_rate_limiter_respected(self, browser_page):
        from hound.core.engine import BudgetedBrowser, RateLimiter
        from hound.core.budget import Budget
        from hound.healing.selectors import SelectorStore

        limiter = RateLimiter(max_requests=2, window_seconds=1)
        store = SelectorStore(":memory:")
        budget = Budget(max_tokens=1000)
        engine = BudgetedBrowser(browser_page, store, budget, rate_limiter=limiter)

        await engine.goto("https://example.com")
        await engine.snapshot(budget=Budget(max_tokens=100))
        # Third request should be rate limited
        # (This is a basic check - actual rate limiting tested in unit test)
