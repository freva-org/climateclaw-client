"""Pytest fixtures for freva-gpt-client tests."""

import base64
import json
import re

import pytest
from pytest_httpx import HTTPXMock, IteratorStream

from freva_gpt_client._constants import FREVAGPT_API_ENDPOINTS


@pytest.fixture
def sample_code_content():
    """Sample valid Code message content."""
    return '{"code": "import xarray\\nprint(\\"hello!\\")"}'


@pytest.fixture
def sample_code_content_empty():
    """Sample Code message with empty code."""
    return '{"code": ""}'


@pytest.fixture
def sample_base64():
    """Sample base64 encoded image data."""
    return base64.b64encode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="
    ).decode("utf-8")


@pytest.fixture
def sample_base64_long():
    """Sample long base64 encoded image data."""
    data = b"iVBORw0KGgoAAAANSUhEUgAAAEYAAAAUCAAAAAAVAxSkAAABrUlEQVQ4y+3TPUvDQBgH8OdDOGa+oUMgk2MpdHIIgpSUiqC0OKirgxYX8QVFRQRpBRF8KShqLbgIYkUEteCgFVuqUEVxEIkvJFhae3m8S2KbSkcFBw9yHP88+eXucgH8kQZ/jSm4VDaIy9RKCpKac9NKgU4uEJNwhHhK3qvPBVO8rxRWmFXPF+NSM1KVMbwriAMwhDgVcrxeMZm85GR0PhvGJAAmyozJsbsxgNEir4iEjIK0SYqGd8sOR3rJAGN2BCEkOxhxMhpd8Mk0CXtZacxi1hr20mI/rzgnxayoidevcGuHXTC/q6QuYSMt1jC+gBIiMg12v2vb5NlklChiWnhmFZpwvxDGzuUzV8kOg+N8UUvNBp64vy9q3UN7gDXhwWLY2nMC3zRDibfsY7wjEkY79CdMZhrxSqqzxf4ZRPXwzWJirMicDa5KwiPeARygHXKNMQHEy3rMopDR20XNZGbJzUtrwDC/KshlLDWyqdmhxZzCsdYmf2fWZPoxCEDyfIvdtNQH0PRkH6Q51g8rFO3Qzxh2LbItcDCOpmuOsV7ntNaERe3v/lP/zO8yn4N+yNPrekmPAAAAAElFTkSuQmCC"
    return base64.b64encode(data).decode("utf-8")


@pytest.fixture
def base_url():
    """Base URL for FrevaGPT client tests."""
    return "http://frevagpt-testinstance.com"


@pytest.fixture
def mock_openapi_spec():
    """Sample OpenAPI spec matching backend structure."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "FrevaGPT Backend", "version": "0.1.0"},
        "paths": {
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['ping']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['help']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['chatbots']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['newthread']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['getthread']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['getuserthreads']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['deletethread']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['setthreadtopic']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['searchthreads']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['streamresponse']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['stop']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['editthread']}": {},
            f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['userfeedback']}": {},
        },
    }


@pytest.fixture
def mock_available_models():
    """Sample available models from backend."""
    return ["gpt-4.1", "gpt-4.1-mini", "ministral-3:14b", "qwen2.5:3b"]


@pytest.fixture
def mock_thread_id():
    """Sample thread ID."""
    return "test_thread_12345"


@pytest.fixture
def mock_new_thread_id():
    """Sample thread ID."""
    return "test_thread_6789"


@pytest.fixture
def mock_user_id():
    """Sample user ID."""
    return "janedoe"


@pytest.fixture
def mock_message_user():
    """Sample User message."""
    return {"variant": "User", "content": "What is ENSO?", "id": "msg_user_1"}


@pytest.fixture
def mock_message_assistant():
    """Sample Assistant message."""
    return {
        "variant": "Assistant",
        "content": "ENSO is a climate phenomenon.",
        "id": "msg_assistant_1",
    }


@pytest.fixture
def mock_thread_list(mock_user_id, mock_thread_id, mock_message_assistant, mock_message_user):
    return [
        {
            "user_id": mock_user_id,
            "thread_id": mock_thread_id,
            "date": "2024-01-01T12:00:00",
            "topic": "Test Topic",
            "content": [mock_message_user],
        },
        {
            "user_id": mock_user_id,
            "thread_id": "test_thread_6789",
            "date": "2024-01-01T13:00:00",
            "topic": "ENSO Discussion",
            "content": [mock_message_user, mock_message_assistant],
        },
    ]


@pytest.fixture
def mock_branched_thread(mock_thread_id, mock_message_assistant, mock_message_user):
    return {"new_thread_id": mock_thread_id, "history": [mock_message_user, mock_message_assistant]}


@pytest.fixture
def mock_request(
    httpx_mock: HTTPXMock,
    mock_openapi_spec,
    mock_available_models,
    mock_thread_id,
    mock_new_thread_id,
    mock_message_user,
    mock_message_assistant,
    mock_thread_list,
):
    """Configure mock responses for client tests."""

    def _make_request(endpoint, *arg, **kwargs):
        endpoint = str(endpoint)
        # Use is_optional=True by default to avoid unused mock errors
        use_optional = kwargs.pop("is_optional", True)
        response_kwargs = {
            "status_code": kwargs.pop("status_code", 200),
            "is_optional": use_optional,
            "is_reusable": kwargs.pop("is_reusable", False),
            "json": None,
            "text": None,
            "stream": None,
        }
        if "openapi" in endpoint:
            response_kwargs["json"] = mock_openapi_spec
        elif "availablechatbots" in endpoint:
            response_kwargs["json"] = mock_available_models
        elif "newthread" in endpoint:
            response_kwargs["json"] = mock_thread_id
        elif "getthread" in endpoint:
            response_kwargs["json"] = [mock_message_user, mock_message_assistant]
        elif "setthreadtopic" in endpoint:
            response_kwargs["json"] = {"detail": "Topic updated."}
        elif "getuserthreads" in endpoint:
            response_kwargs["json"] = [mock_thread_list, len(mock_thread_list)]
        elif "searchthreads" in endpoint:
            response_kwargs["json"] = [mock_thread_list, len(mock_thread_list)]
        elif "deletethread" in endpoint:
            response_kwargs["json"] = {"detail": "Thread deleted."}
        elif "editthread" in endpoint:
            response_kwargs["json"] = {
                "new_thread_id": mock_new_thread_id,
                "history": [mock_message_user, mock_message_assistant],
            }
        elif "userfeedback" in endpoint:
            response_kwargs["json"] = {"detail": "Successfully submitted feedback."}
        elif "stop" in endpoint:
            response_kwargs["json"] = {"detail": "Thread successfully stopped."}
        elif "streamresponse" in endpoint:
            if kwargs.get("stream"):
                stream_iterator = [
                    b'{"variant": "Assistant", "content": "Hello"}',
                    b'{"variant": "StreamEnd", "content": "Stream ended."}',
                ]
                response_kwargs["stream"] = IteratorStream(stream_iterator)
            else:
                response_kwargs["text"] = "\n".join(
                    [
                        json.dumps(mock_message_assistant),
                        json.dumps(
                            {"variant": "StreamEnd", "content": "Stream ended.", "id": None}
                        ),
                    ]
                )
        response_kwargs["json"] = kwargs.pop("json", None) or response_kwargs["json"]
        response_kwargs["text"] = kwargs.pop("text", None) or response_kwargs["text"]
        httpx_mock.add_response(url=re.compile(rf".*{endpoint}.*"), **response_kwargs)

    return _make_request
