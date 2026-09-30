"""Unit tests for StreamResponse class in _streaming.py."""

from contextlib import asynccontextmanager, contextmanager
from typing import List

import httpx
import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock, IteratorStream
from pytest_mock import MockerFixture

from climateclaw_client._streaming import StreamResponse

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_response_httpx(httpx_mock: HTTPXMock):
    def custom_response(request: httpx.Request):
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "application/json"},
        )

    httpx_mock.add_callback(custom_response)


@pytest.fixture
def closed_response_httpx(httpx_mock: HTTPXMock):
    def custom_response(request: httpx.Request):
        r = httpx.Response(
            status_code=200,
            headers={"Content-Type": "application/json"},
        )
        # r.is_closed = True
        return r

    httpx_mock.add_callback(custom_response)


@pytest.fixture
def make_stream_response(mock_response_httpx):
    """Create a StreamResponse instance with a mock response."""
    with httpx.Client() as client:
        response = client.get("https://test.com/api")
        response.is_closed = False
        return response, StreamResponse(response)


@pytest_asyncio.fixture
async def make_async_stream_response(mock_response_httpx):
    """Create an async StreamResponse instance with a mock response."""
    async with httpx.AsyncClient() as client:
        response = await client.get("https://test.com/api")
        response.is_closed = False
        return response, StreamResponse(response)


@pytest.fixture
def make_closed_stream_response(closed_response_httpx):
    """Create an StreamResponse instance with a closed mock response."""
    with httpx.Client() as client:
        response = client.get("https://test.com/api")
    return response, StreamResponse(response)


@pytest_asyncio.fixture
async def make_closed_async_stream_response(closed_response_httpx):
    """Create an async StreamResponse instance with a closed mock response."""
    async with httpx.AsyncClient() as client:
        response = await client.get("https://test.com/api")
    return response, StreamResponse(response)


@pytest.fixture()
def make_stream_response_with_iterator(httpx_mock: HTTPXMock):
    @contextmanager
    def _prepare_stream(byte_iterator):
        httpx_mock.add_response(status_code=200, stream=byte_iterator)
        with httpx.Client() as client:
            with client.stream(method="GET", url="https://test.com/api") as response:
                yield response

    return _prepare_stream


@pytest_asyncio.fixture()
async def make_async_stream_response_with_iterator(httpx_mock: HTTPXMock):
    @asynccontextmanager
    async def _prepare_stream(byte_iterator):
        httpx_mock.add_response(status_code=200, stream=byte_iterator)
        async with httpx.AsyncClient() as client:
            async with client.stream(method="GET", url="https://test.com/api") as response:
                yield response

    return _prepare_stream


# =============================================================================
# Tests for __init__
# =============================================================================


def test_stream_response_init(make_stream_response):
    """Test StreamResponse __init__ sets all attributes correctly from httpx.Response."""
    response, stream_response = make_stream_response
    assert stream_response._response is response
    assert stream_response.status_code == 200
    assert stream_response.headers == {"Content-Type": "application/json"}
    assert stream_response.url == httpx.URL("https://test.com/api")
    # assert stream_response.request is mock_response.request


# =============================================================================
# Tests for is_closed property
# =============================================================================


def test_is_closed_false(make_stream_response):
    """Test is_closed returns False when the underlying response is not closed."""
    response, stream_response = make_stream_response
    assert stream_response.is_closed is False


def test_is_closed_true(make_closed_stream_response):
    """Test is_closed returns True when the underlying response is closed."""
    response, stream_response = make_closed_stream_response
    assert stream_response.is_closed is True


# =============================================================================
# Tests for _process_chunks (static method)
# =============================================================================


@pytest.mark.parametrize(
    "chunk,partial,expected_objects,expected_partial",
    [
        # Single complete JSON object
        (
            '{"key": "value"}',
            "",
            [{"key": "value"}],
            "",
        ),
        # Single complete JSON object with whitespace
        (
            '  {"key": "value"}  ',
            "",
            [{"key": "value"}],
            "",
        ),
        # Partial JSON at start (missing closing brace)
        (
            '{"key": "value"',
            "",
            [],
            '{"key": "value"',
        ),
        # Partial JSON at end (missing opening brace) - continuation
        (
            'key": "value"}',
            '{"',
            [{"key": "value"}],
            "",
        ),
        # Middle part of JSON (no { or })
        # Note: partial '{"' + chunk '"key": "value"' = '{""key": "value"}'
        # because the partial already contains a quote character
        (
            '"key": "value"',
            '{"',
            [],
            '{""key": "value"',
        ),
        # Empty chunk
        (
            "",
            "",
            [],
            "",
        ),
        # Whitespace-only chunk
        (
            "   \n  ",
            "",
            [],
            "",
        ),
        # Chunk with newlines
        (
            '{\n"key": "value"\n}',
            "",
            [{"key": "value"}],
            "",
        ),
        # Split across boundary: first chunk partial, second completes
        (
            'key": "value"}',
            '{"',
            [{"key": "value"}],
            "",
        ),
        # Continuation of partial with more partial
        (
            '"value"',
            '{"key": ',
            [],
            '{"key": "value"',
        ),
        # Second part of split object (completes it)
        (
            "1}",
            '{"a": ',
            [{"a": 1}],
            "",
        ),
        # Multiple complete JSON objects
        (
            '{"a": 1}{"b": 2}',
            "",
            [{"a": 1}, {"b": 2}],
            "",
        ),
        # Three complete JSON objects
        (
            '{"a": 1}{"b": 2}{"c": 3}',
            "",
            [{"a": 1}, {"b": 2}, {"c": 3}],
            "",
        ),
        # Multiple objects split across chunk with first chunk completing a partial
        (
            ': 1}{"b": 2}{"c": 3}',
            '{"a"',
            [{"a": 1}, {"b": 2}, {"c": 3}],
            "",
        ),
        # Multiple objects split across chunk with last chunk being incomplete
        ('{"a": 1}{"b": 2}{"c":', "", [{"a": 1}, {"b": 2}], '{"c":'),
        # Recursive dict that is completed by a final part
        (
            '2}"}',
            '{"a": "{\\"b\\":',
            [{"a": {"b": 2}}],
            "",
        ),
        # json-string contains dictionary
        (
            '{"a":{"b":{"c":1}}}',
            "",
            [{"a": {"b": {"c": 1}}}],
            "",
        ),
        # Object contains "}{" token as a value
        (
            '{"a": "}{"}{"b":5}',
            "",
            [{"a": "}{"}, {"b": 5}],
            "",
        ),
        # malformed json-string returns unchanged
        ('{"a": "ab"c}', "", [], '{"a": "ab"c}'),
        # non json content
        (
            "Hello my darling",
            "",
            [],
            "",
        ),
    ],
    ids=[
        "single_complete",
        "single_complete_with_whitespace",
        "partial_start",
        "partial_end_continuation",
        "middle_part",
        "empty_chunk",
        "whitespace_only",
        "chunk_with_newlines",
        "split_boundary_complete",
        "continuation_more_partial",
        "split_second_part",
        "multiple_complete",
        "three_complete",
        "multiple_with_partial",
        "multiple_with_incomplete_end",
        "recursive_dict_continuation",
        "json_chunk_with_nested_dictionary",
        "curly_braces_as_value",
        "malformed_json_string_returns_incomplete",
        "non_json_content_gets_ignored",
    ],
)
def test_process_chunks(
    chunk: str,
    partial: str,
    expected_objects: List[dict],
    expected_partial: str,
):
    """Test _process_chunks correctly processes various chunk patterns."""
    result_objects, result_partial = StreamResponse._process_chunks(chunk, partial)
    assert result_objects == expected_objects
    assert result_partial == expected_partial


# =============================================================================
# Tests for iter_json_objects
# =============================================================================


@pytest.mark.parametrize(
    argnames="chunks,expected_result",
    argvalues=[
        ([b'{"key": "value"}'], [{"key": "value"}]),
        ([b'{"key": ', b'"value"}'], [{"key": "value"}]),
        ([b'{"a": 1}', b'{"b": 2}'], [{"a": 1}, {"b": 2}]),
        ([b""], []),
        ([b"   \n  "], []),
        ([b'{"a": 1}{"b": 2}'], [{"a": 1}, {"b": 2}]),
    ],
    ids=[
        "complete_object",
        "single_object_split",
        "multiple_complete_objects",
        "empty_response",
        "whitespace_only",
        "multiple_objects_in_one_chunk",
    ],
)
def test_iter_json_objects(
    mocker: MockerFixture, make_stream_response_with_iterator, chunks, expected_result
):
    """Test iter_json_objects yields the correct results for a given stream of chunks."""
    with make_stream_response_with_iterator(IteratorStream(chunks)) as response:
        stream_response = StreamResponse(response)
        spy_iter_bytes = mocker.spy(response, "iter_bytes")
        result = list(stream_response.iter_json_objects())
    assert result == expected_result
    spy_iter_bytes.call_count == 1


# =============================================================================
# Tests for aiter_json_objects
# =============================================================================


@pytest.mark.parametrize(
    argnames="chunks,expected_result",
    argvalues=[
        ([b'{"key": "value"}'], [{"key": "value"}]),
        ([b'{"key": ', b'"value"}'], [{"key": "value"}]),
        ([b'{"a": 1}', b'{"b": 2}'], [{"a": 1}, {"b": 2}]),
        ([b""], []),
        ([b"   \n  "], []),
        ([b'{"a": 1}{"b": 2}'], [{"a": 1}, {"b": 2}]),
    ],
    ids=[
        "complete_object",
        "single_object_split",
        "multiple_complete_objects",
        "empty_response",
        "whitespace_only",
        "multiple_objects_in_one_chunk",
    ],
)
@pytest.mark.asyncio
async def test_aiter_json_objects(
    mocker: MockerFixture, make_async_stream_response_with_iterator, chunks, expected_result
):
    """Test aiter_json_objects yields the correct results for a given stream of chunks."""

    async with make_async_stream_response_with_iterator(IteratorStream(chunks)) as response:
        stream_response = StreamResponse(response)
        spy_aiter_bytes = mocker.spy(response, "aiter_bytes")
        result = []
        async for obj in stream_response.aiter_json_objects():
            result.append(obj)

    assert result == expected_result
    assert spy_aiter_bytes.call_count == 1


# =============================================================================
# Tests for close / aclose
# =============================================================================


def test_close(mocker: MockerFixture, make_stream_response):
    """Test close calls the underlying response.close() method."""
    response, stream_response = make_stream_response
    spy_response = mocker.spy(response, "close")
    stream_response.close()
    spy_response.assert_called_once()


def test_close_already_closed(mocker: MockerFixture, make_closed_stream_response):
    """Test close does not raise when the response is already closed."""
    response, stream_response = make_closed_stream_response
    spy_response = mocker.spy(response, "close")
    stream_response.close()
    spy_response.assert_not_called()


def test_close_multiple_calls(mocker: MockerFixture, make_stream_response):
    """Test close can be called multiple times without error."""
    response, stream_response = make_stream_response
    spy_response = mocker.spy(response, "close")
    stream_response.close()
    stream_response.close()
    # underlying stream should already be closed the from the first call of close
    spy_response.assert_called_once()


@pytest.mark.asyncio
async def test_aclose(mocker: MockerFixture, make_async_stream_response):
    """Test aclose calls the underlying response.aclose() method."""
    response, stream_response = make_async_stream_response
    spy_response = mocker.spy(response, "aclose")
    await stream_response.aclose()
    spy_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_aclose_already_closed(mocker: MockerFixture, make_closed_async_stream_response):
    """Test aclose does not raise when the response is already closed."""
    response, stream_response = make_closed_async_stream_response
    spy_response = mocker.spy(response, "aclose")
    await stream_response.aclose()
    spy_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_aclose_multiple_calls(mocker: MockerFixture, make_async_stream_response):
    """Test aclose can be called multiple times without error."""
    response, stream_response = make_async_stream_response
    spy_response = mocker.spy(response, "aclose")
    await stream_response.aclose()
    await stream_response.aclose()
    # underlying stream should already be closed the from the first call of close
    spy_response.assert_awaited_once()
