import ipaddress
import logging
import platform
import socket
import urllib.parse
from functools import cached_property
from httpx import Response
from typing import Any, Dict, TypeVar, Union, Generic

import asyncio
import httpx
import time
import random

from ._auth import TokenAuth
from ._streaming import StreamResponse
from ._utils import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

_HttpxClientT = TypeVar("_HttpxClientT", bound=Union[httpx.Client, httpx.AsyncClient])
Headers = Dict[str, str]


class BaseClient(Generic[_HttpxClientT]):
    _client: _HttpxClientT
    _version: str
    _base_url: httpx.URL
    follow_redirects: bool
    max_retries: int
    timeout: float
    token_store_path: str

    def __init__(
            self, 
            *,
            version: str,
            base_url: str | httpx.URL, 
            token_store_path: str = "", 
            follow_redirects: bool = True, 
            max_retries: int = DEFAULT_MAX_RETRIES,
            timeout: float = DEFAULT_TIMEOUT,
            custom_headers: dict[str, str] | None = None,
        ):
        self._version = version
        self.base_url = self._validate_base_url(base_url)
        self.follow_redirects = follow_redirects
        self.timeout = timeout
        self.max_retries = max_retries
        self._token_store_path = token_store_path
        self._custom_headers = custom_headers 

    @cached_property
    def _auth(self) -> TokenAuth:
        return TokenAuth(
            base_url = self.base_url,
            token_store_path = self._token_store_path
        )

    @cached_property
    def default_headers(self) -> dict[str, Any]:
        # Lowercase all headers to ensure override
        headers={
            k.lower(): v
            for k, v in {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": f"frevagpt-python/{self._version} ({platform.machine()} {platform.system().lower()}) Python/{platform.python_version()}",
                "X-Freva-Vault-URL": f"{self.base_url}:5002",
                "X-Freva-Rest-URL": f"{self.base_url}:7777",
                "X-Freva-Config-Path": "/opt/freva/core/freva/evaluation_system.conf",
            }.items()
        }
        return headers
    
    def _build_headers(self, custom_headers: Headers) -> httpx.Headers:
        headers = {**self.default_headers, **custom_headers}
        return httpx.Headers(headers)
    
    def _validate_base_url(self, base_url) -> httpx.URL:
        return httpx.URL(self._parse_host(base_url))   
    

        
    
    @staticmethod  
    def _parse_host(host: Union[str, httpx.URL]) -> str:
        host = str(host)
        host, port = host, 80
        scheme, _, hostport = host.partition("://")
        if not hostport:
            scheme, hostport = "http", host
        elif scheme == "http":
            port = 80
        elif scheme == "https":
            port = 443

        split = urllib.parse.urlsplit("://".join([scheme, hostport]))
        host = split.hostname or "127.0.0.1"
        port = split.port or port

        try:
            if isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address):
                # Fix missing square brackets for IPv6 from urlsplit
                host = f"[{host}]"
        except ValueError:
            try:
                socket.gethostbyname(host)
            except socket.gaierror:
                raise ConnectionError(
                    (
                        f"Temporary failure in name resolution of host {host}. "
                        "Make sure host is reachable."
                    )
                )

        if path := split.path.strip("/"):
            return f"{scheme}://{host}:{port}/{path}"

        return f"{scheme}://{host}:{port}"
    

class AsyncAPIClient(BaseClient[httpx.AsyncClient]):
    _client: httpx.AsyncClient

    def __init__(
            self, 
            *,
            version: str,
            base_url: str | httpx.URL, 
            token_store_path: str = "", 
            follow_redirects: bool = True, 
            max_retries: int = DEFAULT_MAX_RETRIES,
            timeout: float = DEFAULT_TIMEOUT,
            http_client: httpx.AsyncClient | None = None,
    ):
        
        if http_client and not isinstance(http_client, httpx.AsyncClient):
            raise TypeError(f"Invalid `http_client` argument; Expected an instance of `httpx.AsyncClient`, but got {type(http_client)}.")
            
        super().__init__(
            version=version,
            base_url=base_url,
            token_store_path=token_store_path,
            follow_redirects=follow_redirects,
            max_retries=max_retries,
            timeout=timeout
        )
        if http_client:
            self._client = http_client
        else:
            self._client = self._default_client

    @property
    def _default_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.default_headers,
            auth=self._auth,
            follow_redirects=self.follow_redirects,
            timeout=self.timeout
        )

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed
    
    async def _sleep_for_retry(self, retries_taken: int):
        timeout = self.timeout * (1 + random.random())
        if retries_taken < self.max_retries:
            logger.debug(f"Retrying connection after sleeping {timeout} seconds. Attempt {retries_taken + 1}.")
        elif retries_taken == self.max_retries:
            logger.debug(f"Retrying connection after sleeping {timeout} seconds. Final attempt.")
        await asyncio.sleep(timeout)
    
    async def _stream(self, *args, **kwargs) -> StreamResponse:
        retries_taken = 0
        for retries_taken in range(self.max_retries + 1):
            try:
                req: httpx.Request = self._client.build_request(*args, **kwargs) 
                res: httpx.Response = await self._client.send(request=req, stream=True)
                res.raise_for_status()
                return StreamResponse(res)
            except httpx.HTTPError as e:
                if retries_taken < self.max_retries:
                    await self._sleep_for_retry(retries_taken=retries_taken)
                    continue
                if isinstance(e, httpx.RequestError):
                    raise ConnectionError(
                        f"Failed to connect to url {self._parse_host(e.request.url)}. Please try again.",
                    ) from None
                elif isinstance(e, httpx.HTTPStatusError):
                    await e.response.aread()
                    raise ConnectionError(
                        e.response.status_code,
                        f"Error connecting to url {self._parse_host(e.request.url)} with error: {e.response.text}",
                    ) from None
        raise ConnectionError("Unexpected error in _stream retry logic")
        
    async def _request_raw(self, *args, **kwargs) -> httpx.Response:
            retries_taken = 0
            for retries_taken in range(self.max_retries + 1):
                try:
                    r: httpx.Response = await self._client.request(*args, **kwargs)
                    r.raise_for_status()
                    break
                except httpx.HTTPError as e:
                    if retries_taken < self.max_retries:
                        await self._sleep_for_retry(retries_taken=retries_taken)
                        continue
                    if isinstance(e, httpx.RequestError):
                        raise ConnectionError(
                            f"Failed to connect to {self._parse_host(e.request.url)}. Please try again."
                        ) from None
                    elif isinstance(e, httpx.HTTPStatusError):
                        await e.response.aread()
                        raise ConnectionError(
                            e.response.status_code,
                            f"Error connecting to url {self._parse_host(e.request.url)} with error: {e.response.text}",
                        ) from None
            return r
    
    async def request(self, *args, stream=False, **kwargs) -> StreamResponse | httpx.Response:        
        if stream:
            return await self._stream(*args, **kwargs)
        else:
            return await self._request_raw(*args, **kwargs)
        
    async def get(
        self,
        path: str,
        *,
        stream: bool = False,
    ):
        return await self.request(
            method="GET",
            url=path,
            stream=stream,
        )


class SyncAPIClient(BaseClient[httpx.Client]):
    _client : httpx.Client

    def __init__(
            self, 
            *,
            version: str,
            base_url: str | httpx.URL, 
            token_store_path: str = "", 
            follow_redirects: bool = True, 
            max_retries: int = DEFAULT_MAX_RETRIES,
            timeout: float = DEFAULT_TIMEOUT,
            http_client: httpx.Client | None = None ,
    ):
        
        if http_client and not isinstance(http_client, httpx.Client):
            raise TypeError(f"Invalid `http_client` argument; Expected an instance of `httpx.Client`, but got {type(http_client)}.")
        
        super().__init__(
            version=version,
            base_url=base_url,
            token_store_path=token_store_path,
            follow_redirects=follow_redirects,
            max_retries=max_retries,
            timeout=timeout,
        )
        if http_client:
            self._client = http_client
        else:
            self._client = self._default_client

    @cached_property
    def _default_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            follow_redirects=self.follow_redirects,
            timeout=self.timeout,
            headers=self.default_headers,
            auth=self._auth,
        )
    
    @property
    def is_closed(self) -> bool:
        return self._client.is_closed
    
    def _sleep_for_retry(self, retries_taken: int):
        timeout = self.timeout * (1 + random.random())
        if retries_taken < self.max_retries:
            logger.debug(f"Retrying connection after sleeping {timeout} seconds. Retry attempt {retries_taken + 1}.")
        elif retries_taken == self.max_retries:
            logger.debug(f"Retrying connection after sleeping {timeout} seconds. Final attempt.")
        time.sleep(timeout)
    
    def _stream(self, *args, **kwargs) -> StreamResponse:
        retries_taken = 0
        for retries_taken in range(self.max_retries + 1):
            try:
                req: httpx.Request = self._client.build_request(*args, **kwargs) 
                res: httpx.Response = self._client.send(request=req, stream=True)
                res.raise_for_status()
                return StreamResponse(res)
            except httpx.HTTPError as e:
                if retries_taken < self.max_retries:
                    self._sleep_for_retry(retries_taken=retries_taken)
                    continue
                if isinstance(e, httpx.RequestError):
                    raise ConnectionError(
                        f"Failed to connect to url {self._parse_host(e.request.url)}. Please try again.",
                    ) from None
                elif isinstance(e, httpx.HTTPStatusError):
                    e.response.read()
                    raise ConnectionError(
                        e.response.status_code,
                        f"Error connecting to url {self._parse_host(e.request.url)} with error: {e.response.text}",
                    ) from None
        raise RuntimeError("Unexpected error in _stream retry logic")
        
    def _request_raw(self, *args, **kwargs) -> Response:
            retries_taken = 0
            for retries_taken in range(self.max_retries + 1):
                try:
                    r: httpx.Response = self._client.request(*args, **kwargs)
                    r.raise_for_status()
                    break
                except httpx.HTTPError as e:
                    if retries_taken < self.max_retries:
                        self._sleep_for_retry(retries_taken=retries_taken)
                        continue
                    if isinstance(e, httpx.RequestError):
                        raise ConnectionError(
                            f"Failed to connect to {self._parse_host(e.request.url)}. Please try again."
                        ) from None
                    elif isinstance(e, httpx.HTTPStatusError):
                        e.response.read()
                        raise ConnectionError(
                            e.response.status_code,
                            f"Error connecting to url {self._parse_host(e.request.url)} with error: {e.response.text}",
                        ) from None
            return r
        
    def request(self, *args, stream=False, **kwargs) -> StreamResponse | Response:        
        if stream:
            return self._stream(*args, **kwargs)
        else:
            return self._request_raw(*args, **kwargs)
        
    def get(
        self,
        path: str,
        *,
        stream: bool = False,
        **kwargs
    ):
        # cast is required because mypy complains about returning Any even though
        # it understands the type variables
        return self.request(
            method="GET",
            url=path,
            stream=stream,
            **kwargs
        )