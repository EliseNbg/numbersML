"""
End-to-End tests for Phase 4 (manual checklist automated).

Uses Playwright for browser automation.
Run with: pytest tests/e2e/test_phase4_e2e.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def base_url():
    return "http://localhost:8000"


@pytest.fixture
def api_base():
    return "http://localhost:8000/api"


class TestConfigurationSetsE2E:
    """E2E tests for ConfigurationSet management."""

    def test_create_config_set(self, page: Page, base_url):
        """Test creating a ConfigurationSet via dashboard."""
        page.goto(f"{base_url}/dashboard/config_sets.html")

        # Click create button
        page.click("text=New Config Set")

        # Fill form
        page.fill("#config-name", "E2E Test Config")
        page.fill("#config-description", "Created by E2E test")
        page.fill("#config-symbols", "BTC/USDT, ETH/USDT")
        page.fill("#config-initial-balance", "5000")

        # Add custom parameter
        page.click("#btn-add-param")
        page.fill(".dynamic-param-row input[placeholder='Parameter name']", "custom_param")
        page.fill(".dynamic-param-row input[placeholder='Value']", "test_value")

        # Save
        page.click("#btn-save")

        # Verify success alert
        expect(page.locator(".alert-success")).to_be_visible()

        # Verify in table
        expect(page.locator("text=E2E Test Config")).to_be_visible()

    def test_edit_config_set(self, page: Page, base_url):
        """Test editing a ConfigurationSet."""
        page.goto(f"{base_url}/dashboard/config_sets.html")

        # Click edit button (first row)
        page.click(".config-set-row:first-child .bi-pencil")

        # Modify
        page.fill("#config-description", "Updated by E2E")

        # Save
        page.click("#btn-save")

        # Verify success
        expect(page.locator(".alert-success")).to_be_visible()

    def test_delete_config_set(self, page: Page, base_url):
        """Test deactivating a ConfigurationSet."""
        page.goto(f"{base_url}/dashboard/config_sets.html")

        # Click delete button (first row)
        page.click(".config-set-row:first-child .bi-trash")

        # Confirm
        page.on("dialog", lambda dialog: dialog.accept())

        # Verify success
        expect(page.locator(".alert-success")).to_be_visible()


class TestAlgorithmInstancesE2E:
    """E2E tests for AlgorithmInstance management."""

    def test_create_instance(self, page: Page, base_url):
        """Test creating a AlgorithmInstance."""
        page.goto(f"{base_url}/dashboard/algorithm-instances.html")

        # Click create
        page.click("text=New Instance")

        # Select algorithm
        page.select_option("#instance-algorithm", index=1)

        # Select config set
        page.select_option("#instance-config-set", index=1)

        # Save
        page.click("#btn-save")

        # Verify success
        expect(page.locator(".alert-success")).to_be_visible()

    def test_start_instance(self, page: Page, base_url):
        """Test starting (hot-plug) a AlgorithmInstance."""
        page.goto(f"{base_url}/dashboard/algorithm-instances.html")

        # Click start button (play icon, first row)
        page.click(".instance-row:first-child .bi-play-fill")

        # Verify status changes (wait for it)
        page.wait_for_selector("text=Running", timeout=5000)

    def test_stop_instance(self, page: Page, base_url):
        """Test stopping (unplug) a AlgorithmInstance."""
        page.goto(f"{base_url}/dashboard/algorithm-instances.html")

        # Click stop button (stop icon)
        page.click(".instance-row:first-child .bi-stop-fill")

        # Confirm
        page.on("dialog", lambda dialog: dialog.accept())

        # Verify status changes
        page.wait_for_selector("text=Stopped", timeout=5000)


class TestBacktestE2E:
    """E2E tests for Backtest page."""

    def test_submit_backtest(self, page: Page, base_url):
        """Test submitting a backtest job."""
        page.goto(f"{base_url}/dashboard/backtest.html")

        # Select instance
        page.select_option("#backtest-instance", index=1)

        # Select time range
        page.click("button[data-range='1d']")

        # Submit
        page.click("#btn-start-backtest")

        # Verify job submitted
        expect(page.locator(".alert-success")).to_be_visible()

        # Wait for completion (poll)
        page.wait_for_selector("text=Completed", timeout=60000)

        # Verify results section visible
        expect(page.locator("#results-section")).to_be_visible()

        # Verify metrics
        expect(page.locator("#metric-return")).to_be_visible()
        expect(page.locator("#metric-sharpe")).to_be_visible()

    def test_backtest_chart_renders(self, page: Page, base_url):
        """Test that equity curve chart renders."""
        page.goto(f"{base_url}/dashboard/backtest.html")

        # Select instance and submit backtest
        page.select_option("#backtest-instance", index=1)
        page.click("button[data-range='1d']")
        page.click("#btn-start-backtest")

        # Wait for completion
        page.wait_for_selector("text=Completed", timeout=60000)

        # Verify Chart.js canvas has content
        page.wait_for_function("""
            () => {
                const canvas = document.getElementById('equity-chart');
                const ctx = canvas.getContext('2d');
                const pixel = ctx.getImageData(100, 100, 1, 1).data;
                return pixel[3] > 0;  // Has drawn content
            }
        """)
