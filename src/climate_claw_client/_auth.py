import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, cast

import httpx
from py_oidc_auth_client import (  # type: ignore
    AuthError,
    DeviceCode,
    DeviceFlow,
    Token,
    TokenStore,
    authenticate,
    authenticate_async,
)

from ._constants import DEFAULT_AUTH_TIMEOUT

logger = logging.getLogger(__name__)


class TokenAuth(httpx.Auth):
    """Authentication handler for ClimateClaw API using OIDC tokens.

    This class manages token authentication for HTTP requests, including
    token storage, validation, and automatic refresh when tokens expire.

    Attributes:
        base_url: The base URL of the ClimateClaw API.
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
        app_name: str = "climate-claw-client",
        interactive: bool = True,
    ):
        """Initializes TokenAuth with base URL and token store configuration.

        Args:
            base_url: The base URL of the ClimateClaw API.
            token_store_path: Optional path to the token store file.
            timeout: Timeout in seconds for authentication requests.
            app_name: Application name for token storage identification.
            interactive: Boolean to determine if authentication can be performed interactively (prompting the user to log in if necessary).
        """
        self.base_url: httpx.URL = base_url
        self.app_name: str = app_name
        self.timeout: float = timeout
        self.token_store: TokenStore = TokenStore(app_name=app_name, path=token_store_path)
        self.token_store_path: str | Path = (
            token_store_path or TokenStore(app_name=app_name, path=token_store_path)._path
        )
        self.auth_token: Token | None = None
        self._interactive = interactive

    def _authenticate(self) -> Token:
        """Authenticates with the OIDC provider and returns a new token."""
        try:
            return authenticate(
                host=f"{self.base_url}/api/freva-nextgen",
                store=self.token_store,
                app_name=self.app_name,
                timeout=self.timeout,
            )
        except Exception as e:
            raise AuthError(
                f"Could not generate a new token. Please try again or reauthenticate. {e}"
            )

    def _update_token_or_store(self) -> None:
        """Updates the token store with the current auth token."""
        stored_token = self.token_store.get(str(self.base_url))
        if stored_token and not self.auth_token:
            self.auth_token = stored_token
        else:
            self.token_store.put(host=str(self.base_url), token=self.auth_token)

    def _validate_token_store(self) -> TokenStore:
        """Validates and initializes the token store."""
        # load token store
        token_store = self.token_store
        auth_token = self.auth_token
        test_token = token_store.get(str(self.base_url))
        # if auth token is not set, but token store contains correct token, update token from token store
        if not auth_token and test_token:
            self.auth_token = test_token
        # if not in interactive mode, and no auth token set, raise AuthError
        elif not (self._interactive or self.auth_token):
            raise AuthError("New token can only be generated in interactive mode.") from None
        # else start oidc device flow
        else:
            self.auth_token = self._authenticate()
        self._update_token_or_store()
        return token_store

    def _validate_token(self) -> Token:
        """Validates the current authentication token."""
        self.token_store = self._validate_token_store()
        self.auth_token = cast(Token, self.auth_token)
        token_expires_at = datetime.fromtimestamp(self.auth_token["expires"], tz=timezone.utc)
        token_refresh_expires_at = datetime.fromtimestamp(
            self.auth_token["refresh_expires"], tz=timezone.utc
        )
        now = datetime.now(timezone.utc)
        if now > token_refresh_expires_at:
            if self._interactive:
                logger.debug(
                    "Both auth and refresh token expired. Prompting user to log in to generate new token."
                )
                self.auth_token = self._authenticate()
                self.token_store.put(host=str(self.base_url), token=self.auth_token)
            else:
                raise AuthError(
                    "Refresh token has expired. New one can only be generated in interactive mode."
                ) from None
        elif now > token_expires_at:
            logger.debug(
                "Freva auth token expired. Using refresh token to generate new token and updating token store."
            )
            self.auth_token = self._authenticate()
            self.token_store.put(host=str(self.base_url), token=self.auth_token)
        return self.auth_token

    def get_auth_headers(self) -> Dict[str, str]:
        """Gets the authentication headers for HTTP requests.

        Returns:
            Dictionary containing authentication headers.
        """
        auth_token = self._validate_token()
        return auth_token.get("headers")

    def sync_auth_flow(self, request: httpx.Request):
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

    async def _async_authenticate(self) -> Token | tuple[DeviceFlow, DeviceCode]:
        """Authenticates asynchronously with the OIDC provider and returns a new token."""
        try:
            return await authenticate_async(
                host=f"{self.base_url}/api/freva-nextgen",
                store=self.token_store,
                app_name=self.app_name,
                timeout=self.timeout,
            )
        except Exception as e:
            raise AuthError(
                f"Could not generate a new token. Please try again or reauthenticate. {e}"
            )

    async def _async_validate_token_store(self) -> TokenStore:
        """Validates and initializes the token store."""
        # load token store
        token_store = self.token_store
        auth_token = self.auth_token
        test_token = token_store.get(str(self.base_url))
        # if auth token is not set, but token store contains correct token, update token from token store
        if not auth_token and test_token:
            self.auth_token = test_token
        # if not in interactive mode, and no auth token set, raise AuthError
        elif not (self._interactive or self.auth_token):
            raise AuthError("New token can only be generated in interactive mode.") from None
        # else start oidc device flow
        else:
            self.auth_token = await self._async_authenticate()
        self._update_token_or_store()

    async def _async_validate_token(self) -> Token:
        """Validates the current authentication token."""
        await self._async_validate_token_store()
        self.auth_token = cast(Token, self.auth_token)
        token_expires_at = datetime.fromtimestamp(self.auth_token["expires"], tz=timezone.utc)
        token_refresh_expires_at = datetime.fromtimestamp(
            self.auth_token["refresh_expires"], tz=timezone.utc
        )
        now = datetime.now(timezone.utc)
        if now > token_refresh_expires_at:
            if self._interactive:
                self.auth_token = await self._async_authenticate()
                self.token_store.put(host=str(self.base_url), token=self.auth_token)
            else:
                raise AuthError(
                    "Refresh token has expired. New one can only be generated in interactive mode."
                ) from None
        elif now > token_expires_at:
            logger.debug(
                "Freva auth token expired. Using refresh token to generate new token and updating token store."
            )
            self.auth_token = await self._async_authenticate()
            self.token_store.put(host=str(self.base_url), token=self.auth_token)
        return self.auth_token

    async def async_get_auth_headers(self) -> Dict[str, str]:
        """Gets the authentication headers for HTTP requests.

        Returns:
            Dictionary containing authentication headers.
        """
        auth_token = await self._async_validate_token()
        return auth_token.get("headers")

    async def async_auth_flow(self, request: httpx.Request):
        """Async HTTP authentication flow handler.

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
            auth_headers = await self.async_get_auth_headers()
            request.headers.update(auth_headers)
            yield request
