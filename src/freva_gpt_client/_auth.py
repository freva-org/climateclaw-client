import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from py_oidc_auth_client import AuthError, Token, TokenStore, authenticate  # type: ignore

from ._utils import DEFAULT_AUTH_TIMEOUT

logger = logging.getLogger(__name__)


class TokenAuth(httpx.Auth):
    """Authentication handler for FrevaGPT API using OIDC tokens.

    This class manages token authentication for HTTP requests, including
    token storage, validation, and automatic refresh when tokens expire.

    Attributes:
        base_url: The base URL of the FrevaGPT API.
        app_name: The application name used for token storage.
        timeout: Timeout in seconds for authentication requests.
        token_store_path: Path to the token store file.
        token_store: TokenStore instance for managing tokens.
        auth_token: Current authentication token.
    """

    def __init__(
        self,
        base_url: httpx.URL,
        token_store_path: str | Path | None = None,
        timeout: float = DEFAULT_AUTH_TIMEOUT,
        app_name: str = "freva-gpt-client",
    ):
        """Initializes TokenAuth with base URL and token store configuration.

        Args:
            base_url: The base URL of the FrevaGPT API.
            token_store_path: Optional path to the token store file.
            timeout: Timeout in seconds for authentication requests.
            app_name: Application name for token storage identification.
        """
        self.base_url = base_url
        self.app_name = app_name
        self.timeout = timeout
        self.token_store = TokenStore(app_name=app_name, path=token_store_path)
        self.token_store_path = (
            token_store_path or TokenStore(app_name=app_name, path=token_store_path)._path
        )

    def _authenticate(self) -> Token:
        """Authenticates with the OIDC provider and returns a new token."""
        return authenticate(
            host=f"{self.base_url}/api/freva-nextgen",
            store=self.token_store,
            app_name=self.app_name,
            timeout=self.timeout,
        )

    def _update_token_or_store(self) -> Token:
        """Updates the token store with the current auth token."""
        stored_token = self.token_store.get(str(self.base_url))
        if stored_token:
            self.auth_token = stored_token
        else:
            self.token_store.put(host=str(self.base_url), token=self.auth_token)

    def _validate_token_store(self) -> TokenStore:
        """Validates and initializes the token store."""
        # load token store
        token_store = (
            self.token_store if hasattr(self, "token_store") else TokenStore(self.token_store_path)
        )
        auth_token = self.auth_token if hasattr(self, "auth_token") else None
        # if freva token store does not exist but token does, write token to store
        if not os.path.exists(token_store._path) and auth_token:
            token_store.put(host=self.base_url, token=auth_token)
        # if auth token is not set, but token store is, update token from token store
        elif not auth_token and token_store.get(str(self.base_url)):
            self.auth_token = token_store.get(str(self.base_url))
        # otherwise, prompt user to authenticate
        else:
            self.auth_token = self._authenticate()
        self.token_store = token_store
        self._update_token_or_store()
        return token_store

    def _validate_token(self) -> Token:
        """Validates the current authentication token."""
        self.token_store = self._validate_token_store()
        token_expires_at = datetime.fromtimestamp(self.auth_token["expires"])
        token_refresh_expires_at = datetime.fromtimestamp(self.auth_token["refresh_expires"])
        now = datetime.now()
        if now > token_refresh_expires_at:
            raise AuthError("Refresh token has expired.") from None
        elif now > token_expires_at:
            logger.debug(
                "Freva auth token expired. Using refresh token to generate new token and updating token store."
            )
            try:
                self.auth_token = self._authenticate()
                self.token_store.put(host=str(self.base_url), token=self.auth_token)
            except Exception as e:
                raise AuthError(
                    f"Could not generate a new token from the token file. Please try again or reauthenticate. {e}"
                )
        return self.auth_token

    def get_auth_headers(self) -> dict[str, str]:
        """Gets the authentication headers for HTTP requests.

        Returns:
            Dictionary containing authentication headers.
        """
        self._validate_token()
        return self.auth_token["headers"]

    def auth_flow(self, request: httpx.Request):
        """HTTP authentication flow handler.

        This generator yields requests with authentication headers added
        when a 401 Unauthorized response is received.

        Args:
            request: The HTTP request to authenticate.

        Yields:
            httpx.Request: The authenticated request.
        """
        response: httpx.Response = yield request
        if response.status_code == 401:
            # If the server issues a 401 response then resend the request,
            # with custom authentication headers.
            request.headers.update(self.get_auth_headers())
            yield request
