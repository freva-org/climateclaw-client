import json
from typing import Any, AsyncGenerator, Dict, Generator, List, Tuple

import httpx


class StreamResponse:
    """Wrapper around httpx.Response that streams complete JSON objects.

    This class wraps an httpx.Response object and provides methods to iterate
    over the response stream, yielding only complete JSON objects. It handles
    cases where JSON objects may be split across multiple chunks in the stream.

    Attributes:
        _response: The underlying httpx.Response object.
        status_code: HTTP status code from the response.
        headers: Response headers.
        url: The URL of the response.
        request: The original request.
        is_closed: Whether the response has been closed.
    """

    def __init__(self, response: httpx.Response):
        """Initializes StreamResponse with an httpx.Response.

        Args:
            response: The httpx.Response object to wrap.
        """
        self._response = response
        self.status_code = response.status_code
        self.headers = response.headers
        self.url = response.url
        self.request = response.request

    @property
    def is_closed(self):
        """Whether the underlying response has been closed.

        Returns:
            True if the response is closed, False otherwise.
        """
        return self._response.is_closed

    @staticmethod
    def _process_chunks(chunk: str, partial_response: str = "") -> Tuple[List[Dict], str]:
        """Processes a chunk of string data containing newline-delimited JSON objects.

        Handles incomplete JSON objects at chunk boundaries by tracking brace depth
        and properly handling string literals.

        Args:
            chunk: A string that may contain full or partial JSON-like objects.
            partial_response: A string storing an incomplete JSON object from
                the previous chunk.

        Returns:
            A tuple of (list of complete JSON dicts, remaining partial string).
        """

        def recurse_dict(d: Dict[str, Any]) -> Dict[str, Any]:
            """Recursively parses JSON strings within a dictionary as dicts."""
            for key, value in d.items():
                if isinstance(value, str):
                    if value.startswith("{") and value.endswith("}"):
                        d[key] = recurse_dict(json.loads(value))
            return d

        # Combine with partial response from previous chunks
        combined = partial_response + chunk
        results: List[Dict] = []
        remaining = ""

        i = 0
        while i < len(combined):
            # Skip whitespace and newlines
            while i < len(combined) and combined[i] in " \t\n\r":
                i += 1

            if i >= len(combined):
                break
            # Only process if we find a starting brace
            if combined[i] == "{":
                brace_depth = 1
                in_string = False
                escape_next = False
                json_start = i
                parsed = {}
                for j in range(i + 1, len(combined)):
                    char = combined[j]
                    if escape_next:
                        escape_next = False
                        continue

                    if char == "\\":
                        escape_next = True
                        continue

                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue

                    if not in_string:
                        if char == "{":
                            brace_depth += 1
                        elif char == "}":
                            brace_depth -= 1
                            if brace_depth == 0:
                                # Found complete JSON object
                                json_str = combined[json_start : j + 1]
                                try:
                                    remaining = ""
                                    parsed = recurse_dict(json.loads(json_str))
                                    results.append(parsed)
                                    i = j + 1
                                    break
                                except json.JSONDecodeError:
                                    # Not valid JSON, treat as partial
                                    break
                if not parsed:
                    # Reached end without finding complete object
                    remaining = combined[json_start:]
                    i = len(combined)
                    break
            else:
                # Skip non-JSON content
                i += 1
        return results, remaining

    def iter_json_objects(self) -> Generator[Dict[str, Any], None, None]:
        """Generator that yields complete JSON dicts from the stream.

        Iterates over the response bytes, processes chunks, and yields
        only complete JSON objects.

        Yields:
            dict: Complete JSON objects parsed from the stream.
        """
        complete_parts: List[Dict]
        partial_response: str
        complete_parts, partial_response = [], ""
        for chunk in self._response.iter_bytes():
            chunk_decoded = chunk.decode("utf-8")
            complete_parts, partial_response = self._process_chunks(chunk_decoded, partial_response)
            for part in complete_parts:
                yield part

    async def aiter_json_objects(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Async generator that yields complete JSON dicts from the stream.

        Asynchronously iterates over the response bytes, processes chunks,
        and yields only complete JSON objects.

        Yields:
            dict: Complete JSON objects parsed from the stream.
        """
        complete_parts: List[dict]
        partial_response: str
        complete_parts, partial_response = [], ""
        async for chunk in self._response.aiter_bytes():
            chunk_decoded = chunk.decode("utf-8")
            complete_parts, partial_response = self._process_chunks(chunk_decoded, partial_response)
            for part in complete_parts:
                yield part

    def close(self) -> None:
        """Closes the underlying response if not already closed."""
        if not self.is_closed:
            self._response.close()

    async def aclose(self) -> None:
        """Closes the underlying response if not already closed (used for asynchronous streams)."""
        if not self.is_closed:
            await self._response.aclose()
