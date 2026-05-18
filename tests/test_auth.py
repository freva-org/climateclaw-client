from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

import freva_gpt_client._auth as auth


def prepare_oidc_token(
    expires: datetime,
    refresh_expires: datetime,
) -> dict[str, Any]:
    return {
        "access_token": "XYZ",
        "token_type": "Bearer",
        "expires": expires.timestamp(),
        "refresh_token": "ABC",
        "refresh_expires": refresh_expires.timestamp(),
        "scope": "myinstance",
        "headers": {
            "Authorization": "Bearer XYZ",
        },
    }


@pytest.fixture(
    scope="module",
    params=[(True, 1), (False, 1), (True, 0), (True, -2)],
    ids=["with_valid_token", "without_valid_token", "with_refresh_token", "with_expired_token"],
)
def prepare_token_dict(request):
    token_contained, expired_factor = request.param
    if token_contained:
        expires = datetime.now() + timedelta(hours=1) * (expired_factor - 0.5)
        refresh_expires = datetime.now() + timedelta(hours=1) * (expired_factor + 1)
        stored_at = datetime.now() - timedelta(hours=4)
        token_dict = {
            "https://myinstance.com": {
                "token": prepare_oidc_token(expires, refresh_expires),
                "stored_at": stored_at.timestamp(),
            }
        }
    else:
        token_dict = {}
    return token_dict


@pytest.fixture(
    scope="function",
    params=[[True, None], [True, "/path/to/token.json"], [False, None]],
    ids=["without_token_store_path", "with_token_store_path", "without_token_set"],
)
def prepare_auth_token(request, mocker, prepare_token_dict):
    token_set, token_store_path = request.param
    MockedTokenStore = mocker.patch.object(auth, "TokenStore", spec=True)
    MockedToken = mocker.patch.object(auth, "Token", spec=True)
    MockedToken.return_value = {}
    if not token_store_path:
        MockedTokenStore.return_value._path = "/default/path/token.json"
    else:
        MockedTokenStore.return_value._path = token_store_path
    MockedTokenStore.return_value.get.side_effect = lambda key: prepare_token_dict.get(key, {}).get(
        "token"
    )
    if (base_url := "https://myinstance.com") in prepare_token_dict and token_set:
        MockedToken.return_value = prepare_token_dict[base_url]["token"]
        MockedToken.get.side_effect = lambda key: prepare_token_dict[base_url].get(key)
    token_auth = auth.TokenAuth(
        base_url="https://myinstance.com",
        token_store_path=token_store_path,
        timeout=10,
        app_name="auth-test",
    )
    return token_store_path, MockedTokenStore, MockedToken, token_auth


def test_token_auth_init(mocker, prepare_auth_token):
    """Test init method of TokenAuth class"""
    token_store_path, MockedTokenStore, _, token_auth = prepare_auth_token
    if token_store_path:
        assert (
            token_auth.token_store_path == token_store_path
        ), f"token store path was expected to be set as '{token_store_path}', but got '{token_auth.token_store_path}' instead!"
        MockedTokenStore.assert_called_once_with(app_name="auth-test", path=token_store_path)
    else:
        assert (
            token_auth.token_store_path == "/default/path/token.json"
        ), f"token store path was expected to be set to default '/default/path/token.json', but got {token_auth.token_store_path} instead!"
        MockedTokenStore.assert_has_calls(
            2 * [mocker.call(app_name="auth-test", path=token_store_path)]
        )
    assert token_auth.timeout == 10
    assert token_auth.app_name == "auth-test"
    assert token_auth.auth_token is None


def test_auth(mocker, prepare_auth_token):
    """Test helper method _auth to call py-oidc-client authenticate method"""
    _, MockedTokenStore, _, token_auth = prepare_auth_token
    mocked_authenticate = mocker.patch.object(auth, "authenticate")
    token_auth._authenticate()
    mocked_authenticate.assert_called_once_with(
        host="https://myinstance.com/api/freva-nextgen",
        store=MockedTokenStore.return_value,
        app_name="auth-test",
        timeout=10,
    )


def test_update_token_or_store(prepare_auth_token):
    """Test method to update token or store, depending if token can be found in token store"""
    _, MockedTokenStore, MockedToken, token_auth = prepare_auth_token
    token_auth.auth_token = MockedToken()
    token_auth._update_token_or_store()
    if stored_token := MockedTokenStore().get("https://myinstance.com"):
        assert token_auth.auth_token == stored_token
    else:
        MockedTokenStore().put.assert_called_once_with(
            host="https://myinstance.com", token=MockedToken()
        )


def test_validate_token_store(mocker, prepare_auth_token):
    """Test that _validate_token_store either reads token from store or triggers oidc auth flow"""
    _, MockedTokenStore, MockedToken, token_auth = prepare_auth_token
    mocked_authenticate = mocker.patch.object(auth.TokenAuth, "_authenticate")
    mocked_update_token_or_store = mocker.patch.object(auth.TokenAuth, "_update_token_or_store")
    test_token = MockedTokenStore().get("https://myinstance.com")
    token_auth.auth_token = MockedToken()
    token_auth._validate_token_store()
    token_set = True if MockedToken() else False
    # token store does not contain key (or does not exist) and auth token is not set -> self._authenticate
    if not (test_token or token_set):
        mocked_authenticate.assert_called_once()
    # token  -> update token store
    elif test_token and not token_set:
        assert token_auth.auth_token == test_token
        mocked_authenticate.assert_not_called()
    else:
        mocked_authenticate.assert_not_called()
    mocked_update_token_or_store.assert_called_once()


def test_validate_token(mocker, prepare_auth_token):
    """Test that _validate_token checks expiration of token, refreshes if necessary and raises appropriate errors."""
    _, MockedTokenStore, MockedToken, token_auth = prepare_auth_token
    mocked_authenticate = mocker.patch.object(auth.TokenAuth, "_authenticate")
    fresh_token = prepare_oidc_token(
        expires=datetime.now() + timedelta(days=1),
        refresh_expires=datetime.now() + timedelta(days=2),
    )
    mocked_authenticate.return_value = fresh_token
    spy_logger = mocker.spy(auth, "logger")
    test_token = MockedToken() or MockedTokenStore().get("https://myinstance.com")
    auth_token = test_token or fresh_token
    if datetime.fromtimestamp(auth_token["refresh_expires"]) < datetime.now():
        with pytest.raises(auth.AuthError, match="Refresh token has expired."):
            token_auth._validate_token()
    elif datetime.fromtimestamp(auth_token["expires"]) < datetime.now():
        token_auth._validate_token()
        spy_logger.debug.assert_called_once_with(
            "Freva auth token expired. Using refresh token to generate new token and updating token store."
        )
        mocked_authenticate.assert_called_once()
        MockedTokenStore().put.assert_called_once()
        # repeat, but lets assume the call to _authenticate results in an error
        mocked_authenticate.side_effect = Exception
        with pytest.raises(
            auth.AuthError, match=r"Could not generate a new token from the token file.*"
        ):
            token_auth._validate_token()
    else:
        returned_token = token_auth._validate_token()
        assert returned_token == auth_token


def test_get_auth_headers(mocker, prepare_auth_token):
    """Test that get_auth_headers"""
    _, MockedTokenStore, MockedToken, token_auth = prepare_auth_token
    fresh_token = prepare_oidc_token(
        expires=datetime.now() + timedelta(days=1),
        refresh_expires=datetime.now() + timedelta(days=2),
    )
    mocked_authenticate = mocker.patch.object(auth.TokenAuth, "_authenticate")
    mocked_authenticate.return_value = fresh_token
    test_token = MockedToken() or MockedTokenStore().get("https://myinstance.com")
    auth_token = test_token or fresh_token

    if datetime.fromtimestamp(auth_token["refresh_expires"]) < datetime.now():
        with pytest.raises(auth.AuthError, match="Refresh token has expired."):
            token_auth.get_auth_headers()
    elif datetime.fromtimestamp(auth_token["expires"]) < datetime.now():
        auth_headers = token_auth.get_auth_headers()
        mocked_authenticate.assert_called_once()
        MockedTokenStore().put.assert_called_once()
        assert "Authorization" in auth_headers
        assert "Bearer" in auth_headers["Authorization"]
        assert auth_token["access_token"] in auth_headers["Authorization"]
        # repeat, but lets assume the call to _authenticate results in an error
        mocked_authenticate.side_effect = Exception
        with pytest.raises(
            auth.AuthError, match=r"Could not generate a new token from the token file.*"
        ):
            token_auth.get_auth_headers()
    else:
        auth_headers = token_auth.get_auth_headers()
        assert "Authorization" in auth_headers
        assert "Bearer" in auth_headers["Authorization"]
        assert auth_token["access_token"] in auth_headers["Authorization"]


def test_auth_flow(mocker, httpx_mock: HTTPXMock):
    """Test that auth flow handles 401 status codes correctly"""
    mocked_get_auth_headers = mocker.patch.object(auth.TokenAuth, "get_auth_headers")
    mocked_get_auth_headers.return_value = {"Authorization": "Bearer XYZ"}
    httpx_mock.add_response(status_code=401)
    httpx_mock.add_response(status_code=200)
    with httpx.Client(
        base_url="https://myinstance.com",
        auth=auth.TokenAuth(
            base_url="https://myinstance.com",
            token_store_path=None,
            timeout=10,
            app_name="auth-test",
        ),
    ) as client:
        response = client.get("/test")
        response.raise_for_status()
        mocked_get_auth_headers.assert_called_once()
        assert "authorization" in response.request.headers
        assert "Bearer XYZ" in response.request.headers["authorization"]
