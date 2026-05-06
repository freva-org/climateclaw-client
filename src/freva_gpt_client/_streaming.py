import json
from typing import Any, AsyncGenerator, Generator

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
        self.is_closed = response.is_closed

    @staticmethod
    def _process_chunks(chunk: str, partial_response: str = "") -> tuple[list[dict], str]:
        """Processes a chunk of string data containing JSON-like objects.

        Handles cases where JSON objects are split across chunks by tracking
        partial responses and combining them when complete objects are received.

        Args:
            chunk: A string that may contain full or partial JSON-like objects.
            partial_response: A string storing an incomplete JSON object from
                the previous chunk.

        Returns:
            A tuple of (list of complete JSON dicts, remaining partial string).
        """

        def recurse_dict(d: dict[str, Any]) -> dict[str, Any]:
            """Recursively parses JSON strings within a dictionary as dicts."""
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
                return [
                    recurse_dict(json.loads(partial_response))
                ], ""  # Return the completed object

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
                    # If it is complete, add to the list and clear partial response
                    complete_parts.append(recurse_dict(json.loads(fixed_part)))
                    partial_response = ""

                else:
                    fixed_part = "{" + part + "}"

                complete_parts.append(recurse_dict(json.loads(fixed_part)))
        return complete_parts, partial_response

    def iter_json_objects(self) -> Generator[dict]:
        """Generator that yields complete JSON dicts from the stream.

        Iterates over the response bytes, processes chunks, and yields
        only complete JSON objects.

        Yields:
            dict: Complete JSON objects parsed from the stream.
        """
        complete_parts, partial_response = [], ""
        for chunk in self._response.iter_bytes():
            chunk_decoded = chunk.decode("utf-8")
            complete_parts, partial_response = self._process_chunks(chunk_decoded, partial_response)
            for part in complete_parts:
                yield part

    async def aiter_json_objects(self) -> AsyncGenerator[dict]:
        """Async generator that yields complete JSON dicts from the stream.

        Asynchronously iterates over the response bytes, processes chunks,
        and yields only complete JSON objects.

        Yields:
            dict: Complete JSON objects parsed from the stream.
        """
        complete_parts, partial_response = [], ""
        async for chunk in self._response.aiter_bytes():
            chunk_decoded = chunk.decode("utf-8")
            complete_parts, partial_response = self._process_chunks(chunk_decoded, partial_response)
            for part in complete_parts:
                yield part
