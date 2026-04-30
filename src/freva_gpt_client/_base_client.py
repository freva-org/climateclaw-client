import ipaddress
import json
import logging
import platform
import socket
import urllib.parse
from functools import cached_property
from typing import Any, Dict, TypeVar, Union, Generic

import asyncio
import httpx
import time
import random

from .auth import TokenAuth
from .utils import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

_HttpxClientT = TypeVar("_HttpxClientT", bound=Union[httpx.Client, httpx.AsyncClient])
Headers = Dict[str, str]
_StreamT = TypeVar("_StreamT", bound=httpx.SyncByteStream)
_AsyncStreamT = TypeVar("_AsyncStreamT", bound=httpx.AsyncByteStream)


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
            base_url: str, 
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
    def _process_chunks(chunk: str, partial_response: str = "") -> tuple[list[dict], str]:
        """
        Processes a chunk of string data, which represent JSON-like objects split across chunks.

        Args:
        chunk (str): A string that may contain full or partial JSON-like objects.
        partial_response (str): A string that stores an incomplete JSON-like object from the previous chunk.

        Returns:
        Tuple[List[str], str]: A list of complete JSON-like objects and the partial string (if any).
        """

        def recurse_dict(d: dict[str, Any]) -> dict[str, Any]:
            """
            Make sure that all (possibly escaped) json-strings within a dictionary are parsed as dicts
            """
            for key, value in d.items():
                if isinstance(value, str):
                    if value.startswith("{") and value.endswith("}"):
                        d[key] = recurse_dict(json.loads(value))
            return d

        # sanitize input string
        chunk = chunk.strip().replace("\n", "")
        # check that chunk is not empty
        if not chunk:
            return [], partial_response
        # Attempt to split the input chunk into potential JSON-like parts based on "}{"
        chunk_split = chunk.split("}{")
        # If there is no "}{", the chunk might represent a single or partial JSON-like object
        if len(chunk_split) == 1:
            # Case 1: The chunk starts with "{" and ends with "}" (a complete JSON object)
            if chunk[0] == "{" and chunk[-1] == "}":
                return [recurse_dict(json.loads(chunk))], ""

            # Case 2: The chunk starts with "{" but does not end with "}" (partial JSON object)
            elif chunk[0] == "{" and chunk[-1] != "}":
                partial_response = chunk  # Save the partial object for later
                return [], partial_response

            # Case 3: The chunk ends with "}" but does not start with "{" (completes a partial JSON object)
            elif chunk[-1] == "}":
                partial_response += chunk  # Append to the saved partial object
                return [recurse_dict(json.loads(partial_response))], ""  # Return the completed object

            # Case 4: Neither starts with "{" nor ends with "}" (still an incomplete JSON object)
            else:
                partial_response += chunk  # Append to the saved partial object
                return [], partial_response

        # If there are multiple parts after splitting, handle them as potential JSON objects
        else:
            complete_parts = []

            for i, part in enumerate(chunk_split):
                if i == 0:
                    fixed_part = part + "}"  # Add closing brace to make it a complete object
                    # Check if it is a continuation of a partial response
                    if part[0] != "{":
                        partial_response += fixed_part  # Append to the saved partial object
                        complete_parts.append(
                            recurse_dict(json.loads(partial_response))
                        )  # Add the completed object to the list
                        continue

                elif i == len(chunk_split) - 1:
                    fixed_part = "{" + part  # Add opening brace to make it a complete object
                    # If it is still incomplete, save it as the new partial response
                    if part[-1] != "}":
                        partial_response = fixed_part
                        return complete_parts, partial_response
                    # If it is complete, add to the list and clear partial response
                    complete_parts.append(recurse_dict(json.loads(fixed_part)))
                    return complete_parts, ""

                else:
                    fixed_part = "{" + part + "}"

                complete_parts.append(recurse_dict(json.loads(fixed_part)))
    
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
    
    async def _stream(self, *args, **kwargs) -> _AsyncStreamT:
        async def inner():
            async with self._client.stream(*args, **kwargs) as r:
                r.raise_for_status()
                complete_parts, partial_response = [], ""
                async for chunk in r.aiter_bytes():
                    chunk_decoded = chunk.decode("utf-8")
                    complete_parts, partial_response = self._process_chunks(
                        chunk_decoded, partial_response
                    )
                    if complete_parts:
                        for part in complete_parts:
                            yield part
        retries_taken = 0
        for retries_taken in range(self.max_retries + 1):
            try:            
                result = inner()
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
            return result
        
    async def _request_raw(self, *args, **kwargs) -> httpx.Response:
            retries_taken = 0
            for retries_taken in range(self.max_retries + 1):
                try:
                    r: httpx.Response = await self._client.request(*args, **kwargs)
                    r.raise_for_status()
                except httpx.HTTPError as e:
                    if retries_taken < self.max_retries:
                        await self._sleep_for_retry(retries_taken=retries_taken)
                        continue
                    if isinstance(e, httpx.RequestError):
                        raise ConnectionError(
                            f"Failed to connect to {self._parse_host(e.request.url)}. Please try again."
                        ) from None
                    elif isinstance(e, httpx.HTTPStatusError):
                        e.response.aread()
                        raise ConnectionError(
                            e.response.status_code,
                            f"Error connecting to url {self._parse_host(e.request.url)} with error: {e.response.text}",
                        ) from None
                return r
    
    async def request(self, *args, stream=False, **kwargs) -> _AsyncStreamT | httpx.Response:        
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
            base_url: str, 
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
            logger.debug(f"Retrying connection after sleeping {timeout} seconds. Attempt {retries_taken + 1}.")
        elif retries_taken == self.max_retries:
            logger.debug(f"Retrying connection after sleeping {timeout} seconds. Final attempt.")
        time.sleep(timeout)
    
    def _stream(self, *args, **kwargs) -> _StreamT:
        def inner():
            with self._client.stream(*args, **kwargs) as r:
                r.raise_for_status()
                complete_parts, partial_response = [], ""
                for chunk in r.iter_bytes():
                    chunk_decoded = chunk.decode("utf-8")
                    complete_parts, partial_response = self._process_chunks(
                        chunk_decoded, partial_response
                    )
                    if complete_parts:
                        for part in complete_parts:
                            yield part

        retries_taken = 0
        for retries_taken in range(self.max_retries + 1):
            try:
                result = inner()
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
            return result
        
    def _request_raw(self, *args, **kwargs) -> httpx.Response:
            retries_taken = 0
            for retries_taken in range(self.max_retries + 1):
                try:
                    r: httpx.Response = self._client.request(*args, **kwargs)
                    r.raise_for_status()
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
        
    def request(self, *args, stream=False, **kwargs) -> _StreamT | httpx.Response:        
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