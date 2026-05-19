import httpx
import pytest
from pytest_httpx import HTTPXMock  # noqa
from pytest_mock import MockerFixture

import freva_gpt_client._base_client
from freva_gpt_client._base_client import AsyncAPIClient, BaseClient, SyncAPIClient  # noqa
from freva_gpt_client._constants import DEFAULT_TIMEOUT

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def base_url_https():
    return "https://myinstance.com"


@pytest.fixture
def base_url_http():
    return "https://myinstance.com"


@pytest.fixture
def base_url_no_protocol():
    return "myinstance.com"


@pytest.fixture
def base_url_ip():
    return "192.168.2.1"


@pytest.fixture
def base_client_config(base_url_https):
    return {
        "version": "1.0.0",
        "base_url": base_url_https,
        "token_store_path": "/path/to/token/store.json",
        "follow_redirects": True,
        "max_retries": 42,
        "timeout": 123,
        "custom_headers": {},
    }


@pytest.fixture
def make_base_client(mocker: MockerFixture, base_client_config):
    mock_validate_base_url = mocker.patch.object(BaseClient, "_validate_base_url")
    mock_validate_base_url.return_value = base_client_config["base_url"]
    return BaseClient(**base_client_config)


# =============================================================================
# BaseMessage Tests
# =============================================================================


def test_base_client_init(base_client_config, make_base_client):
    """Test that __init__ method of BaseClient class initializes properties correctly."""
    base_client = make_base_client
    assert base_client.base_url == base_client_config["base_url"]
    assert base_client.follow_redirects == base_client_config["follow_redirects"]
    assert base_client.max_retries == base_client_config["max_retries"]
    assert base_client.timeout == httpx.Timeout(
        DEFAULT_TIMEOUT, connect=base_client_config["timeout"]
    )
    assert base_client._custom_headers == base_client_config["custom_headers"]
    assert base_client._version == base_client_config["version"]


def test_base_client_auth(mocker: MockerFixture, make_base_client):
    """Test that _auth property can be accessed correctly."""
    base_client = make_base_client
    mocked_token_auth = mocker.patch.object(freva_gpt_client._base_client, "TokenAuth")
    mocked_token_auth.return_value = {}
    assert base_client._auth == {}
    assert base_client._auth == {}
    # because the auth token is cached, the underlying TokenAuth should only be called once.
    mocked_token_auth.assert_called_once_with(
        base_url=base_client.base_url, token_store_path=base_client._token_store_path
    )


def test_base_client_default_headers(make_base_client):
    """Test that default_headers are set correctly for a given instance of the base client"""
    base_client = make_base_client
    default_headers = base_client.default_headers
    assert "content-type" in default_headers
    assert default_headers["content-type"] == "application/json"
    assert "user-agent" in default_headers
    assert "freva-gpt-python" in default_headers["user-agent"]
    assert "x-freva-vault-url" in default_headers
    assert base_client.base_url in default_headers["x-freva-vault-url"]
    assert "x-freva-rest-url" in default_headers
    assert base_client.base_url in default_headers["x-freva-rest-url"]
    assert "x-freva-config-path" in default_headers


def test_base_client_build_headers():
    pass


def test_base_client_validate_base_url_https():
    pass


def test_base_client_validate_base_url_http():
    pass


def test_base_client_validate_base_url_ip():
    pass


# =============================================================================
# SyncAPIClient Tests
# =============================================================================

# =============================================================================
# AsyncAPIClient Tests
# =============================================================================
