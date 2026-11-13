"""Tests for Browser Pool automation driver (TC-158, TC-159, TC-160, TC-161)."""

import pytest
import respx

from browser_pool import BrowserPool


@pytest.mark.asyncio
async def test_capture_screenshot_desktop_and_mobile_tc158():
    """TC-158: Captures screenshots in desktop and mobile viewport with DPR 3."""
    with respx.mock(base_url="https://preview.agency.dev") as mock:
        mock.get("/").respond(200, html="<h1>Preview</h1>")

        pool = BrowserPool()

        # Desktop
        res_desktop = await pool.capture_screenshot(
            url="https://preview.agency.dev",
            viewport_width=1280,
            viewport_height=800,
            device_scale_factor=1.0,
        )
        assert res_desktop.width == 1280
        assert res_desktop.height == 800
        assert res_desktop.device_scale_factor == 1.0
        assert len(res_desktop.image_base64) > 0

        # Mobile WhatsApp Demo (375x812 DPR 3)
        res_mobile = await pool.capture_screenshot(
            url="https://preview.agency.dev",
            viewport_width=375,
            viewport_height=812,
            device_scale_factor=3.0,
        )
        assert res_mobile.width == 375
        assert res_mobile.height == 812
        assert res_mobile.device_scale_factor == 3.0


@pytest.mark.asyncio
async def test_inspect_console_detects_hydration_error_tc159(mock_error_page: str):
    """TC-159: Inspects page and detects React hydration error."""
    with respx.mock(base_url="https://preview.agency.dev") as mock:
        mock.get("/").respond(200, html=mock_error_page)

        pool = BrowserPool()
        report = await pool.inspect_console("https://preview.agency.dev")

        assert not report.clean
        assert any("Hydration" in err for err in report.errors)


@pytest.mark.asyncio
async def test_inspect_console_clean_page(mock_clean_page: str):
    """Console inspection passes on clean page."""
    with respx.mock(base_url="https://clean.agency.dev") as mock:
        mock.get("/").respond(200, html=mock_clean_page)

        pool = BrowserPool()
        report = await pool.inspect_console("https://clean.agency.dev")

        assert report.clean
        assert len(report.errors) == 0


@pytest.mark.asyncio
async def test_interact_executes_action_sequence_tc160():
    """TC-160: Executes sequence of click, fill, and wait actions."""
    pool = BrowserPool()
    actions = [
        {"type": "fill", "selector": "#name", "value": "João"},
        {"type": "fill", "selector": "#phone", "value": "11999998888"},
        {"type": "click", "selector": "#submit-btn"},
    ]

    res = await pool.interact("https://lead-form.agency.dev", actions)
    assert res.success
    assert res.actions_executed == 3
    assert len(res.logs) == 3


@pytest.mark.asyncio
async def test_run_e2e_tests_tc161():
    """TC-161: Executes E2E Playwright test journey suite."""
    pool = BrowserPool()
    res = await pool.run_e2e_tests(workspace_id="ws_barbearia", test_filter="smoke")

    assert res.passed
    assert res.total_tests == 5
    assert res.passed_tests == 5
    assert res.failed_tests == 0
