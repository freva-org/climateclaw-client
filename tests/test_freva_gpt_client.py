"""Unit tests for FrevaGPT class in client.py."""

import json
import re

import httpx
import pytest
from pytest_httpx import HTTPXMock, IteratorStream
from pytest_mock import MockerFixture

from freva_gpt_client._base_client import BaseClient
from freva_gpt_client._constants import FREVAGPT_API_ENDPOINTS
from freva_gpt_client.client import FrevaGPT, logger
from freva_gpt_client.models import Conversation, StreamConversation

# =============================================================================
# Fixtures
# =============================================================================


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


# Configure mock responses for init validation
@pytest.fixture
def mock_request(
    httpx_mock: HTTPXMock,
    mock_available_models,
    mock_openapi_spec,
    mock_thread_id,
    mock_message_user,
    mock_message_assistant,
    mock_thread_list,
):
    def _make_request(url, *arg, **kwargs):
        endpoint = str(url)
        response_kwargs = {
            "status_code": kwargs.pop("status_code", 200),
            "is_optional": kwargs.pop("is_optional", False),
            "is_reusable": kwargs.pop("is_reusable", False),
            "json": None,
            "stream": None,
        }
        if "openapi" in endpoint:
            response_kwargs["json"] = kwargs.pop("json", None) or mock_openapi_spec
        elif "availablechatbots" in endpoint:
            response_kwargs["json"] = kwargs.pop("json", None) or mock_available_models
        elif "newthread" in endpoint:
            response_kwargs["json"] = kwargs.pop("json", None) or mock_thread_id
        elif "getthread" in endpoint:
            mock_thread_data = [mock_message_user, mock_message_assistant]
            response_kwargs["json"] = kwargs.pop("json", None) or mock_thread_data
        elif "newthread" in endpoint:
            response_kwargs["json"] = mock_thread_id
        elif "setthreadtopic" in endpoint:
            response_kwargs["json"] = {"detail": "Topic updated."}
        elif "getuserthreads" in endpoint:
            response_kwargs["json"] = [mock_thread_list, len(mock_thread_list)]
        elif "searchthreads" in endpoint:
            response_kwargs["json"] = [mock_thread_list, len(mock_thread_list)]
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
        httpx_mock.add_response(url=re.compile(rf".*{endpoint}.*"), **response_kwargs)

    return _make_request


@pytest.fixture()
def create_freva_gpt_client(mocker: MockerFixture, base_url, mock_request):
    """Helper to create FrevaGPT client with simple HTTP client."""

    def _create_client(**kwargs) -> FrevaGPT:
        # Mock call to openapi.json and availablechatbots (if model is set) for init
        mock_request("openapi", json=kwargs.pop("openapi_spec", None))
        if kwargs.get("model"):
            mock_request("availablechatbots", is_optional=False)
        else:
            mock_request("availablechatbots", is_optional=True)
        # Create a simple client if not supplied as a keyword argument
        http_client = kwargs.get("http_client") or httpx.Client(base_url=base_url)
        # Mock the token auth to avoid OIDC flow
        mocker.patch.object(BaseClient, "_auth", new_callable=mocker.PropertyMock)
        mocker.patch.object(BaseClient, "default_headers", new_callable=mocker.PropertyMock)
        # Mock the validation of the base url
        mocked_validate_base_url = mocker.patch.object(BaseClient, "_validate_base_url")
        mocked_validate_base_url.return_value = httpx.URL(base_url)

        defaults = {
            "base_url": base_url,
            "token_store_path": "",
            "http_client": http_client,
            "max_retries": 0,
        }
        defaults.update(kwargs)

        return FrevaGPT(**defaults)

    return _create_client


# =============================================================================
# TestInit - Tests for __init__
# =============================================================================


class TestInit:
    """Tests for FrevaGPT class initialization."""

    def test_init_all_params(self, base_url, create_freva_gpt_client):
        """Test initialization with all parameters."""
        client: FrevaGPT = create_freva_gpt_client(
            thread_id="test_thread",
            model="gpt-4.1",
        )
        assert client.base_url == httpx.URL(base_url)
        assert client._thread_id == "test_thread"
        assert client.model == "gpt-4.1"

    def test_init_minimal_params(self, base_url, create_freva_gpt_client):
        """Test initialization with minimal parameters."""
        client: FrevaGPT = create_freva_gpt_client()
        assert client.base_url == httpx.URL(base_url)
        assert client._thread_id is None
        assert client.model is None

    def test_init_with_http_client(self, base_url, create_freva_gpt_client):
        """Test initialization with custom HTTP client."""
        # Create custom client with mock responses
        custom_client = httpx.Client()
        custom_client.base_url = httpx.URL(base_url)

        client: FrevaGPT = create_freva_gpt_client(http_client=custom_client)
        assert client._client == custom_client

    def test_init_invalid_model(self, create_freva_gpt_client):
        """Test that invalid model raises ValueError."""
        with pytest.raises(ValueError, match="is not a valid selection"):
            create_freva_gpt_client(model="invalid_model")

    def test_root_api_path(self, create_freva_gpt_client):
        """Test that _root_api_path is set correctly."""
        client: FrevaGPT = create_freva_gpt_client()
        assert client._root_api_path == "/api/chatbot"

    def test_construct_path(self, create_freva_gpt_client):
        """Test _construct_path method."""
        client = create_freva_gpt_client()

        path = client._construct_path("ping")
        assert path == "/api/chatbot/ping"

        path = client._construct_path("newthread")
        assert path == "/api/chatbot/newthread"

        path = client._construct_path("streamresponse")
        assert path == "/api/chatbot/streamresponse"


# =============================================================================
# TestEndpointValidation - Tests for _validate_backend_endpoints
# =============================================================================


class TestEndpointValidation:
    """Tests for backend endpoint validation."""

    def test_validate_backend_endpoints_success(self, create_freva_gpt_client):
        """Test successful validation of all endpoints."""
        client = create_freva_gpt_client()
        assert client is not None

    def test_validate_backend_endpoints_missing_paths_key(
        self, create_freva_gpt_client, mock_request
    ):
        """Test that missing 'paths' key raises KeyError."""
        mock_spec = {"openapi": "3.1.0", "info": {"version": "0.1.0"}}  # Missing 'paths'
        with pytest.raises(KeyError, match="Key 'paths' cannot be found"):
            create_freva_gpt_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_missing_info_key(self, create_freva_gpt_client):
        """Test that missing 'info' key raises KeyError."""
        mock_spec = {"openapi": "3.1.0", "paths": {}}  # Missing 'info'
        with pytest.raises(KeyError, match="Key 'info' cannot be found"):
            create_freva_gpt_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_missing_version(self, create_freva_gpt_client):
        """Test that missing version in info raises KeyError."""
        mock_spec = {
            "openapi": "3.1.0",
            "info": {},  # Missing 'version'
            "paths": {f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['ping']}": {}},
        }
        with pytest.raises(KeyError, match="version information could not be retrieved"):
            create_freva_gpt_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_missing_expected_endpoint(self, create_freva_gpt_client):
        """Test that missing expected endpoint raises KeyError."""
        mock_spec = {"openapi": "3.1.0", "info": {"version": "0.1.0"}, "paths": {}}  # Empty paths
        with pytest.raises(KeyError, match="could not be found in backend specification"):
            create_freva_gpt_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_unexpected_endpoint(
        self,
        mocker: MockerFixture,
        create_freva_gpt_client,
        mock_openapi_spec,
    ):
        mock_spec = mock_openapi_spec
        mock_spec["paths"]["/api/chatbot/unexpected_endpoint"] = {}
        spy_logger = mocker.spy(logger, "warning")
        create_freva_gpt_client(openapi_spec=mock_spec)
        assert any(
            "API endpoint /api/chatbot/unexpected_endpoint not included in client specification"
            in call.args[0]
            for call in spy_logger.call_args_list
        )


# =============================================================================
# TestAuthenticate - Tests for available_models
# =============================================================================


class TestAuthenticate:

    def test_authenticate(self, mocker: MockerFixture, create_freva_gpt_client):
        """Test that authenticate calls TokenAuth _authenticate method."""
        client: FrevaGPT = create_freva_gpt_client()
        mock_authenticate = mocker.patch.object(client._auth, "_authenticate")
        client.authenticate()
        mock_authenticate.assert_called_once()


# =============================================================================
# TestFrevaGPTModels - Tests for available_models
# =============================================================================


class TestModels:
    """Tests for available models endpoint."""

    def test_available_models_success(self, create_freva_gpt_client, mock_available_models):
        """Test retrieving available models."""
        client: FrevaGPT = create_freva_gpt_client()
        models = client.available_models
        assert models == mock_available_models

    def test_available_models_cached(self, create_freva_gpt_client):
        """Test that available_models is cached."""
        client: FrevaGPT = create_freva_gpt_client()
        models1 = client.available_models
        models2 = client.available_models
        assert models1 is models2


# =============================================================================
# TestThreadManagement - Tests for thread management methods
# =============================================================================


class TestThreadManagement:
    """Tests for thread management methods."""

    def test_newthread_success(self, create_freva_gpt_client, mock_request, mock_thread_id):
        """Test creating a new thread."""
        client: FrevaGPT = create_freva_gpt_client()
        assert client._thread_id is None
        mock_request("newthread")
        thread_id = client.newthread()
        assert thread_id == mock_thread_id
        assert client._thread_id == thread_id

    def test_getthread_success(self, create_freva_gpt_client, mock_request, mock_thread_id):
        """Test retrieving a thread by ID."""
        client: FrevaGPT = create_freva_gpt_client()
        client._thread_id = mock_thread_id
        mock_request("getthread", is_reusable=True)
        thread = client.getthread()
        assert len(thread.messages) == 2
        assert thread.messages[0].message.variant == "User"
        assert thread.messages[1].message.variant == "Assistant"

    def test_getthread_no_thread_raises_typeerror(self, create_freva_gpt_client):
        """Test that getthread raises TypeError if no thread_id provided."""
        client: FrevaGPT = create_freva_gpt_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to specified"):
            client.getthread()

    def test_setthreadtopic_success(self, create_freva_gpt_client, mock_request, mock_thread_id):
        """Test setting thread topic."""
        client: FrevaGPT = create_freva_gpt_client()
        mock_request("setthreadtopic")

        new_topic = "Test Topic"

        result = client.setthreadtopic(new_topic=new_topic, thread_id=mock_thread_id)
        assert result == new_topic

    def test_setthreadtopic_no_thread_raises_typeerror(self, create_freva_gpt_client):
        """Test that setthreadtopic raises TypeError if no thread_id provided."""
        client: FrevaGPT = create_freva_gpt_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to specified"):
            client.setthreadtopic(new_topic="Test")


# =============================================================================
# TestPrompting - Tests for prompt method
# =============================================================================


class TestPrompting:
    """Tests for streaming and non-streaming prompting."""

    def test_prompt_non_stream_success(
        self, create_freva_gpt_client, mock_request, mock_available_models, mock_thread_id
    ):
        """Test non-streaming prompt returns Conversation."""
        client: FrevaGPT = create_freva_gpt_client()
        client.model = mock_available_models[0]
        client._thread_id = mock_thread_id
        mock_request("streamresponse", stream=False)
        result = client.prompt("Test prompt", model=client.model, stream=False)

        assert isinstance(result, Conversation)
        assert len(result.messages) == 2

    def test_prompt_non_stream_minimal_params_success(
        self,
        create_freva_gpt_client,
        mock_request,
        mock_available_models,
    ):
        """Test non-streaming prompt with minimal parameters."""
        client: FrevaGPT = create_freva_gpt_client(
            model=mock_available_models[0]
        )  # set model, so it can be skipped in the prompt
        assert client._thread_id is None
        mock_request("newthread")
        mock_request("streamresponse", stream=False)
        result = client.prompt(
            "Test prompt",
        )
        assert isinstance(result, Conversation)
        assert len(result.messages) == 2

    def test_prompt_non_stream_minimal_params_set_thread_success(
        self,
        create_freva_gpt_client,
        mock_request,
        mock_available_models,
        mock_thread_id,
    ):
        """Test non-streaming prompt with minimal parameters and set thread id."""
        client: FrevaGPT = create_freva_gpt_client(model=mock_available_models[0])

        client._thread_id = mock_thread_id
        mock_request("streamresponse", stream=False)
        result = client.prompt(
            "Test prompt",
        )
        assert isinstance(result, Conversation)
        assert len(result.messages) == 2

    def test_prompt_stream_success(
        self,
        httpx_mock: HTTPXMock,
        create_freva_gpt_client,
        mock_request,
        mock_available_models,
        mock_thread_id,
    ):
        """Test streaming prompt returns Conversation."""
        client: FrevaGPT = create_freva_gpt_client()
        client.model = mock_available_models[0]
        mock_request("streamresponse", stream=True)

        result = client.prompt(
            "Test prompt", model=client.model, thread_id=mock_thread_id, stream=True
        )

        assert isinstance(result, StreamConversation)
        conv = result.translate_to_conversation()
        assert len(conv.messages) == 2

    def test_prompt_no_model_raises_typeerror(self, create_freva_gpt_client, mock_thread_id):
        """Test that prompt raises TypeError if no model specified."""
        client: FrevaGPT = create_freva_gpt_client()
        client._thread_id = mock_thread_id

        with pytest.raises(TypeError, match="Argument 'model' has to specified"):
            client.prompt(input="Test", thread_id=mock_thread_id)

    def test_prompt_invalid_model_raises_valueerror(self, create_freva_gpt_client, mock_thread_id):
        """Test that prompt raises ValueError for invalid model."""
        client: FrevaGPT = create_freva_gpt_client()
        client._thread_id = mock_thread_id

        with pytest.raises(ValueError, match=r"Value .* is not a valid selection"):
            client.prompt(input="Test", model="invalid_model", thread_id=mock_thread_id)

    def test_prompt_keyboard_interrupt_sends_stop(
        self, mocker: MockerFixture, create_freva_gpt_client, mock_available_models, mock_thread_id
    ):
        "Test that a KeyboardInterrupt event leads to a call to the stop method."
        client: FrevaGPT = create_freva_gpt_client()
        client.model = mock_available_models[0]
        client._thread_id = mock_thread_id
        client.stop = mocker.MagicMock()
        client.get = mocker.Mock(side_effect=KeyboardInterrupt)
        with pytest.raises(KeyboardInterrupt):
            client.prompt("Test prompt", model=client.model, stream=False)
            client.get.assert_called_once()
            client.stop.assert_called_once()


# =============================================================================
# TestThreadSearch - Tests for getuserthreads and searchthreads
# =============================================================================


class TestThreadSearch:
    """Tests for user thread search methods."""

    def test_getuserthreads_success(
        self, create_freva_gpt_client, mock_request, mock_thread_list, mock_thread_id
    ):
        """Test retrieving user threads."""
        client: FrevaGPT = create_freva_gpt_client()
        mock_request("getuserthreads")

        total, threads = client.getuserthreads(num_threads=5)

        assert total == min(5, len(mock_thread_list))
        assert len(threads) == total
        assert threads[0]["thread_id"] == mock_thread_id
        assert threads[0]["topic"] == "Test Topic"
        assert isinstance(threads[0]["content"], Conversation)

    def test_getuserthreads_zero_num_threads_raises_valueerror(self, create_freva_gpt_client):
        """Test that getuserthreads raises ValueError for num_threads <= 0."""
        client: FrevaGPT = create_freva_gpt_client()
        with pytest.raises(ValueError, match="has to be at least 1"):
            client.getuserthreads(num_threads=0)

    def test_searchthreads_success(self, create_freva_gpt_client, mock_request, mock_thread_list):
        """Test searching threads by query."""
        client: FrevaGPT = create_freva_gpt_client()
        mock_request("searchthreads")

        total, results = client.searchthreads(query="ENSO", num_threads=5)

        assert total == min(5, len(mock_thread_list))
        assert len(results) == total
        assert results[1]["topic"] == "ENSO Discussion"

    def test_searchthreads_zero_num_threads_raises_valueerror(self, create_freva_gpt_client):
        """Test that searchthreads raises ValueError for num_threads <= 0."""
        client: FrevaGPT = create_freva_gpt_client()
        with pytest.raises(ValueError, match="has to be at least 1"):
            client.searchthreads(query="test", num_threads=0)
