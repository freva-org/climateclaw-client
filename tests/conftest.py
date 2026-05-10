"""Pytest fixtures for freva-gpt-client tests."""

import base64

import pytest


@pytest.fixture
def sample_code_content():
    """Sample valid Code message content."""
    return '{"code": "import xarray\\nprint(xarray)"}'


@pytest.fixture
def sample_code_content_empty():
    """Sample Code message with empty code."""
    return '{"code": ""}'


@pytest.fixture
def sample_code_content_multiline():
    """Sample Code message with multi-line code."""
    return '{"code": "x = 1\\ny = 2\\nz = 3"}'


@pytest.fixture
def sample_base64():
    """Sample base64 encoded image data."""
    return base64.b64encode(b"test image data").decode("utf-8")


@pytest.fixture
def sample_base64_long():
    """Sample long base64 encoded image data."""
    data = b"x" * 100  # 100 bytes of data
    return base64.b64encode(data).decode("utf-8")


@pytest.fixture
def temp_dir(tmp_path):
    """Temporary directory for file tests."""
    return tmp_path
