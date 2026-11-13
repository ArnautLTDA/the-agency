"""Pytest fixtures for Browser Gateway test suite."""

import pytest
import respx


@pytest.fixture
def mock_clean_page():
    return "<html><head><title>Clean App</title></head><body><h1>Hello World</h1></body></html>"


@pytest.fixture
def mock_error_page():
    return "<html><head><title>App with Error</title></head><body><h1>Error</h1><p>Hydration failed because the initial UI does not match</p></body></html>"
