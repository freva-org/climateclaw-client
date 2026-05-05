import json
from typing import Any

import httpx


class StreamResponse:
    """Wrapper around httpx.Response that streams complete JSON objects."""

    def __init__(self, response: httpx.Response):
        self._response = response
        self.status_code = response.status_code
        self.headers = response.headers
        self.url = response.url
        self.request = response.request
        self.is_closed = response.is_closed

    @staticmethod
    def _process_chunks(chunk: str, partial_response: str = "") -> tuple[list[dict], str]:
        """
        Processes a chunk of string data, which represent JSON-like objects split across chunks.
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

    def iter_json_objects(self):
        """Generator that yields complete JSON dicts from the stream."""
        complete_parts, partial_response = [], ""
        for chunk in self._response.iter_bytes():
            chunk_decoded = chunk.decode("utf-8")
            complete_parts, partial_response = self._process_chunks(chunk_decoded, partial_response)
            for part in complete_parts:
                yield part

    async def aiter_json_objects(self):
        """Async generator that yields complete JSON dicts from the stream."""
        complete_parts, partial_response = [], ""
        async for chunk in self._response.aiter_bytes():
            chunk_decoded = chunk.decode("utf-8")
            complete_parts, partial_response = self._process_chunks(chunk_decoded, partial_response)
            for part in complete_parts:
                yield part
