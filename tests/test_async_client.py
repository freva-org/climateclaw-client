"""Unit tests for AsyncFrevaGPT class in client.py."""

import httpx
import pytest
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from freva_gpt_client._base_client import BaseClient
from freva_gpt_client._constants import FREVAGPT_API_ENDPOINTS
from freva_gpt_client.client import AsyncFrevaGPT, logger
from freva_gpt_client.models import Conversation, StreamConversation

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def create_async_client(mocker: MockerFixture, base_url, mock_request):
    """Helper to create AsyncFrevaGPT client with simple HTTP client."""

    def _create_client(**kwargs) -> AsyncFrevaGPT:
        # Mock TokenAuth to return None to avoid OIDC flow
        # Mock the token auth to avoid OIDC flow
        mocked_auth = mocker.patch.object(BaseClient, "_auth", new=httpx.Auth(), spec=True)
        mocked_auth._async_authenticate = mocker.AsyncMock()
        mocker.patch.object(BaseClient, "default_headers", new_callable=mocker.PropertyMock)
        # Mock the validation of the base url
        mocked_validate_base_url = mocker.patch.object(BaseClient, "_parse_host")
        mocked_validate_base_url.return_value = base_url

        # Mock call to openapi.json for init validation
        mock_request("openapi", json=kwargs.pop("openapi_spec", None))
        if kwargs.get("model"):
            mock_request("availablechatbots", is_optional=False)
        else:
            mock_request("availablechatbots", is_optional=True)

        defaults = {
            "base_url": base_url,
            "token_store_path": "",
            "max_retries": 0,
        }
        defaults.update(kwargs)
        return AsyncFrevaGPT(**defaults)

    return _create_client


# =============================================================================
# TestInit - Tests for __init__
# =============================================================================


class TestInit:
    """Tests for AsyncFrevaGPT class initialization."""

    @pytest.mark.asyncio
    async def test_init_all_params(self, base_url, create_async_client):
        """Test initialization with all parameters."""
        client: AsyncFrevaGPT = create_async_client(
            thread_id="test_thread",
            model="gpt-4.1",
        )
        assert client.base_url == httpx.URL(base_url)
        assert client.thread_id == "test_thread"
        assert client.model == "gpt-4.1"

    def test_init_minimal_params(self, base_url, create_async_client):
        """Test initialization with minimal parameters."""
        client: AsyncFrevaGPT = create_async_client()
        assert client.base_url == httpx.URL(base_url)
        assert client.thread_id is None
        assert client.model is None

    def test_init_with_http_client(self, base_url, create_async_client):
        """Test initialization with custom HTTP client."""
        # Create custom client with mock responses
        custom_client = httpx.AsyncClient()
        custom_client.base_url = httpx.URL(base_url)

        client: AsyncFrevaGPT = create_async_client(http_client=custom_client)
        assert client._client == custom_client

    def test_root_api_path(self, create_async_client):
        """Test that _root_api_path is set correctly."""
        client = create_async_client()
        assert client._root_api_path == "/api/chatbot"

    def test_construct_path(self, create_async_client):
        """Test _construct_path method."""
        client = create_async_client()

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

    def test_validate_backend_endpoints_success(self, create_async_client, httpx_mock: HTTPXMock):
        """Test that _validate_backend_endpoints succeeds with valid openapi spec."""
        client: AsyncFrevaGPT = create_async_client()
        # If no error, validation passed
        assert client is not None

    def test_validate_backend_endpoints_missing_paths_key(self, create_async_client):
        """Test that missing 'paths' key raises KeyError."""
        mock_spec = {"openapi": "3.1.0", "info": {"version": "0.1.0"}}  # Missing 'paths'
        with pytest.raises(KeyError, match="Key 'paths' cannot be found"):
            create_async_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_missing_info_key(self, create_async_client):
        """Test that missing 'info' key raises KeyError."""
        mock_spec = {"openapi": "3.1.0", "paths": {}}  # Missing 'info'
        with pytest.raises(KeyError, match="Key 'info' cannot be found"):
            create_async_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_missing_version(self, create_async_client):
        """Test that missing version in info raises KeyError."""
        mock_spec = {
            "openapi": "3.1.0",
            "info": {},  # Missing 'version'
            "paths": {f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['ping']}": {}},
        }
        with pytest.raises(KeyError, match="version information could not be retrieved"):
            create_async_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_missing_expected_endpoint(self, create_async_client):
        """Test that missing expected endpoint raises KeyError."""
        mock_spec = {"openapi": "3.1.0", "info": {"version": "0.1.0"}, "paths": {}}  # Empty paths
        with pytest.raises(KeyError, match="could not be found in backend specification"):
            create_async_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_unexpected_endpoint(
        self,
        mocker: MockerFixture,
        create_async_client,
        mock_openapi_spec,
    ):
        mock_spec = mock_openapi_spec
        mock_spec["paths"]["/api/chatbot/unexpected_endpoint"] = {}
        spy_logger = mocker.spy(logger, "warning")
        create_async_client(openapi_spec=mock_spec)
        assert any(
            "API endpoint /api/chatbot/unexpected_endpoint not included in client specification"
            in call.args[0]
            for call in spy_logger.call_args_list
        )


# =============================================================================
# TestModels - Tests for model property and available_models
# =============================================================================


class TestModels:
    """Tests for model-related methods."""

    def test_available_models_property(self, create_async_client):
        """Test available_models property."""
        client: AsyncFrevaGPT = create_async_client()
        assert hasattr(client, "available_models")

    def test_available_models_success(self, create_async_client, mock_available_models):
        """Test retrieving available models."""
        client: AsyncFrevaGPT = create_async_client()
        models = client.available_models
        assert models == mock_available_models

    def test_available_models_cached(self, create_async_client):
        """Test that available_models is cached."""
        client: AsyncFrevaGPT = create_async_client()
        models1 = client.available_models
        models2 = client.available_models
        assert models1 is models2

    def test_model_getter(self, create_async_client):
        """Test model property getter returns _model attribute."""
        client: AsyncFrevaGPT = create_async_client()
        assert client.model is None
        client._model = "test_model"
        assert client.model == "test_model"

    def test_model_setter(self, mocker: MockerFixture, create_async_client):
        """Test model property setter updates _model attribute."""
        client: AsyncFrevaGPT = create_async_client()
        client.available_models = ["test_model", "test_model2"]
        client.model = "test_model"
        assert client._model == "test_model"

    def test_model_setter_invalid_model_raises(self, mocker: MockerFixture, create_async_client):
        """Test model setter raises a ValueError if an invalid model is set."""
        client: AsyncFrevaGPT = create_async_client()
        client.available_models = ["test_model", "test_model2"]
        with pytest.raises(ValueError, match=r"Value .* is not a valid selection.*"):
            client.model = "invalid_model"


# =============================================================================
# TestAuthenticate - Tests for available_models
# =============================================================================


class TestAuthenticate:
    """Test client authentication method"""

    @pytest.mark.asyncio
    async def test_authenticate(self, mocker: MockerFixture, create_async_client):
        """Test that authenticate calls TokenAuth _authenticate method."""
        client: AsyncFrevaGPT = create_async_client()
        mock_authenticate = mocker.patch.object(
            client._auth, "_async_authenticate", new_callable=mocker.AsyncMock
        )
        await client.authenticate()
        mock_authenticate.assert_called_once()


# =============================================================================
# TestThreadManagement - Tests for thread management methods
# =============================================================================


class TestThreadManagement:
    """Tests for thread management methods."""

    @pytest.mark.asyncio
    async def test_newthread_success(self, create_async_client, mock_request):
        """Test newthread creates a new thread and returns thread ID."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("newthread")
        thread_id = await client.newthread()
        assert thread_id == "test_thread_12345"
        assert client.thread_id == thread_id

    @pytest.mark.asyncio
    async def test_getthread_success(self, create_async_client, mock_thread_id, mock_request):
        """Test getthread retrieves thread by ID."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("getthread")
        client.thread_id = mock_thread_id
        result = await client.getthread()
        assert isinstance(result, Conversation)
        assert len(result.messages) == 2

    @pytest.mark.asyncio
    async def test_getthread_with_explicit_thread_id(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test getthread retrieves thread by explicit thread_id parameter."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("getthread")
        result = await client.getthread(thread_id=mock_thread_id)
        assert isinstance(result, Conversation)

    @pytest.mark.asyncio
    async def test_getthread_instance_thread_success(
        self,
        mocker: MockerFixture,
        create_async_client,
        mock_request,
        mock_thread_id,
        mock_new_thread_id,
    ):
        """Test retrieving a thread by ID when instance has different thread_id."""
        client: AsyncFrevaGPT = create_async_client()
        spy = mocker.spy(client, "get")
        client.thread_id = mock_thread_id
        mock_request("getthread", is_reusable=True)
        thread = await client.getthread(mock_new_thread_id)
        assert spy.call_args_list[-1].kwargs["params"].get("thread_id") == mock_new_thread_id
        assert len(thread.messages) == 2
        assert thread.messages[0].message.variant == "User"
        assert thread.messages[1].message.variant == "Assistant"

    @pytest.mark.asyncio
    async def test_getthread_no_thread_raises_type_error(self, create_async_client):
        """Test getthread raises TypeError when no thread_id is specified."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to be specified"):
            await client.getthread()

    @pytest.mark.asyncio
    async def test_deletethread_success(self, create_async_client, mock_thread_id, mock_request):
        """Test deleting an existing thread without specifying thread, results in instance thread being deleted and reset."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("deletethread")
        await client.deletethread()
        assert client.thread_id is None

    @pytest.mark.asyncio
    async def test_deletethread_with_explicit_thread_id(
        self, create_async_client, mock_request, mock_thread_id, mock_new_thread_id
    ):
        """Test deletethread deletes thread by explicit thread_id parameter."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("deletethread")
        await client.deletethread(thread_id=mock_thread_id)

    @pytest.mark.asyncio
    async def test_deletethread_different_thread_success(
        self,
        create_async_client,
        mock_request,
        mock_thread_id,
        mock_new_thread_id,
    ):
        """Test deleting an existing thread that is not the instance thread is successful but does not reset instance thread id."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("deletethread")
        await client.deletethread(mock_new_thread_id)
        # Should not reset client.thread_id since it's different
        assert client.thread_id is not None
        assert client.thread_id == mock_thread_id

    @pytest.mark.asyncio
    async def test_deletethread_no_thread_raises_type_error(self, create_async_client):
        """Test deletethread raises TypeError when no thread_id is specified."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to be specified"):
            await client.deletethread()

    @pytest.mark.asyncio
    async def test_setthreadtopic_success(self, create_async_client, mock_thread_id, mock_request):
        """Test setthreadtopic sets topic for a thread."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("setthreadtopic")
        result = await client.setthreadtopic(new_topic="New Topic", thread_id=mock_thread_id)
        assert result == "New Topic"

    @pytest.mark.asyncio
    async def test_setthreadtopic_with_instance_thread_success(
        self, mocker: MockerFixture, create_async_client, mock_request, mock_thread_id
    ):
        """Test that setthreadtopic correctly uses instance thread id when setting new topic."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("setthreadtopic")
        client.thread_id = mock_thread_id
        spy_get = mocker.spy(client, "get")
        await client.setthreadtopic("Test topic")
        assert spy_get.call_args_list[-1].kwargs["params"]["thread_id"] == client.thread_id

    @pytest.mark.asyncio
    async def test_setthreadtopic_no_thread_raises_type_error(self, create_async_client):
        """Test setthreadtopic raises TypeError when no thread_id is specified."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to be specified"):
            await client.setthreadtopic("New Topic")

    @pytest.mark.asyncio
    async def test_stop_success(self, create_async_client, mock_thread_id, mock_request):
        """Test stop stops a streaming conversation."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("stop")
        result = await client.stop()
        assert result is True

    @pytest.mark.asyncio
    async def test_stop_with_explicit_thread_id(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test stop stops thread by explicit thread_id parameter."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("stop")
        result = await client.stop(thread_id=mock_thread_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_stop_no_thread_raises_type_error(self, create_async_client):
        """Test stop raises TypeError when no thread_id is specified."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to be specified"):
            await client.stop()

    @pytest.mark.asyncio
    async def test_stop_no_active_thread_success(
        self, mocker: MockerFixture, create_async_client, mock_thread_id, mock_request
    ):
        """Test stop returns True even if no active thread is found on the backend."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("stop", status_code=404)
        spy_logger = mocker.spy(logger, "warning")
        result = await client.stop()
        spy_logger.assert_called_with(
            f"No active thread could be found under thread_id {mock_thread_id}."
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_stop_internal_server_error_raises(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test that stop raises ConnectionError when backend responds with 505 internal server error."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("stop", status_code=505, json={"detail": "Internal server error"})
        with pytest.raises(
            ConnectionError, match="Could not stop thread due to an internal server error."
        ):
            await client.stop()

    @pytest.mark.asyncio
    async def test_stop_other_http_error_raises(
        self, mocker: MockerFixture, create_async_client, mock_request, mock_thread_id
    ):
        """Test that stop handles http statuses that are not 200, 404, 505 differently"""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("stop", status_code=401)
        with pytest.raises(ConnectionError, match=r"\[Errno 401\] Error connecting to url.*"):
            await client.stop()

    @pytest.mark.asyncio
    async def test_editthread_minimal_params_success(
        self, create_async_client, mock_request, mock_thread_id, mock_new_thread_id
    ):
        """Test that editthread passes successfully and returns with expected result for minimal parameters."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("editthread")
        new_thread_id, branched_conv = await client.editthread(user_index=1)
        assert new_thread_id == mock_new_thread_id
        assert isinstance(branched_conv, Conversation)

    @pytest.mark.asyncio
    async def test_editthread_thread_specified_success(
        self, create_async_client, mock_request, mock_thread_id, mock_new_thread_id
    ):
        """Test that editthread passes successfully and returns with expected result if source_thread_id is specified."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("editthread")
        new_thread_id, branched_conv = await client.editthread(
            user_index=1, source_thread_id=mock_thread_id
        )
        assert new_thread_id == mock_new_thread_id
        assert isinstance(branched_conv, Conversation)

    @pytest.mark.asyncio
    async def test_editthread_no_thread_raises_type_error(self, create_async_client):
        """Test editthread raises TypeError when no source_thread_id is specified."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(TypeError, match="Argument 'source_thread_id' has to be specified"):
            await client.editthread(user_index=0)

    @pytest.mark.asyncio
    async def test_editthread_thread_not_found_raises_value_error(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test editthread raises ValueError when source thread is not found."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("editthread", status_code=404, json={"detail": "No thread found"})
        with pytest.raises(ValueError, match=f"No thread found for id '{mock_thread_id}'"):
            await client.editthread(user_index=0)

    @pytest.mark.asyncio
    async def test_editthread_index_out_of_bounds_raises_index_error(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test editthread raises IndexError when user_index is out of bounds."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("editthread", status_code=422, json={"detail": "Index out of bounds"})
        with pytest.raises(IndexError, match="User message index 200 out of bounds!"):
            await client.editthread(user_index=200)

    @pytest.mark.asyncio
    async def test_editthread_internal_server_error_raises(
        self, mocker: MockerFixture, create_async_client, mock_request, mock_thread_id
    ):
        """Test that editthread raises a ConnectionError if backend returns a status code other than 200, 404, 422."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("editthread", status_code=500)
        with pytest.raises(
            ConnectionError, match="Editing thread failed due to an internal server error."
        ):
            await client.editthread(user_index=200)

    @pytest.mark.asyncio
    async def test_editthread_missing_keys_in_response_raises(
        self, mocker: MockerFixture, create_async_client, mock_request, mock_thread_id
    ):
        """Test that editthread raises a KeyError if returned json does not contain expected keys."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("editthread", json={"wrong_key": "value"})
        with pytest.raises(
            KeyError,
            match=f"The response to editing thread '{mock_thread_id}' did not include keys",
        ):
            await client.editthread(user_index=1)


# =============================================================================
# TestPrompting - Tests for prompt method
# =============================================================================


class TestPrompting:
    """Tests for the prompt method."""

    @pytest.mark.asyncio
    async def test_prompt_non_stream_success(
        self, create_async_client, mock_available_models, mock_thread_id, mock_request
    ):
        """Test prompt with stream=False returns Conversation."""
        client: AsyncFrevaGPT = create_async_client(model=mock_available_models[0])
        client.thread_id = mock_thread_id
        mock_request("streamresponse", stream=False)
        result = await client.prompt("test", stream=False)

        assert isinstance(result, Conversation)

    @pytest.mark.asyncio
    async def test_prompt_non_stream_minimal_params_success(
        self, create_async_client, mock_available_models, mock_request
    ):
        """Test prompt with stream=False and minimal params returns Conversation."""
        client: AsyncFrevaGPT = create_async_client(model=mock_available_models[0])
        mock_request("newthread")
        mock_request("streamresponse", stream=False)
        result = await client.prompt(input="test", stream=False)
        assert isinstance(result, Conversation)

    @pytest.mark.asyncio
    async def test_prompt_non_stream_minimal_params_set_thread_success(
        self, create_async_client, mock_available_models, mock_thread_id, mock_request
    ):
        """Test prompt with stream=False uses set thread_id when available."""
        client: AsyncFrevaGPT = create_async_client(model=mock_available_models[0])
        client.thread_id = mock_thread_id
        mock_request("streamresponse", stream=False)
        result = await client.prompt(input="test", stream=False)
        assert isinstance(result, Conversation)

    @pytest.mark.asyncio
    async def test_prompt_stream_success(
        self, create_async_client, mock_available_models, mock_thread_id, mock_request
    ):
        """Test prompt with stream=True returns StreamConversation."""
        client: AsyncFrevaGPT = create_async_client(model=mock_available_models[0])
        mock_request("streamresponse", stream=True)
        result = await client.prompt("test", thread_id=mock_thread_id, stream=True)
        assert isinstance(result, StreamConversation)

    @pytest.mark.asyncio
    async def test_prompt_no_model_raises_typeerror(self, create_async_client):
        """Test prompt raises TypeError when model is not specified."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(TypeError, match="Argument 'model' has to be specified"):
            await client.prompt("test")

    @pytest.mark.asyncio
    async def test_prompt_invalid_model_raises_valueerror(
        self, create_async_client, mock_available_models, httpx_mock: HTTPXMock
    ):
        """Test prompt raises ValueError when model is invalid."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(ValueError, match="is not a valid selection for param 'model'"):
            await client.prompt("test", model="invalid_model")

    @pytest.mark.asyncio
    async def test_prompt_keyboard_interrupt_sends_stop(
        self, mocker: MockerFixture, create_async_client, mock_available_models, mock_thread_id
    ):
        "Test that a KeyboardInterrupt event leads to a call to the stop method."
        client: AsyncFrevaGPT = create_async_client(model=mock_available_models[0])
        client.thread_id = mock_thread_id
        client.stop = mocker.AsyncMock()
        client.get = mocker.Mock(side_effect=KeyboardInterrupt)
        with pytest.raises(KeyboardInterrupt):
            await client.prompt("Test prompt", model=client.model, stream=False)
        client.get.assert_called_once()
        client.stop.assert_called_once()


# =============================================================================
# TestThreadSearch - Tests for getuserthreads and searchthreads
# =============================================================================


class TestThreadSearch:
    """Tests for user thread search methods."""

    @pytest.mark.asyncio
    async def test_getuserthreads_success(
        self, create_async_client, mock_thread_list, mock_thread_id, mock_request
    ):
        """Test retrieving user threads."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("getuserthreads")
        total, threads = await client.getuserthreads(num_threads=5)

        assert total == min(5, len(mock_thread_list))
        assert len(threads) == total
        assert threads[0]["thread_id"] == mock_thread_id
        assert threads[0]["topic"] == "Test Topic"
        assert isinstance(threads[0]["content"], Conversation)

    @pytest.mark.asyncio
    async def test_getuserthreads_zero_num_threads_raises_valueerror(self, create_async_client):
        """Test that getuserthreads raises ValueError for num_threads <= 0."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(ValueError, match="has to be at least 1"):
            await client.getuserthreads(num_threads=0)

    @pytest.mark.asyncio
    async def test_searchthreads_success(self, create_async_client, mock_request, mock_thread_list):
        """Test searching user threads."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("searchthreads")
        total, results = await client.searchthreads(query="test", num_threads=5)
        assert total == min(5, len(mock_thread_list))
        assert len(results) == total
        assert results[1]["topic"] == "ENSO Discussion"

    @pytest.mark.asyncio
    async def test_searchthreads_zero_num_threads_raises_valueerror(self, create_async_client):
        """Test that searchthreads raises ValueError for num_threads <= 0."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(ValueError, match="has to be at least 1"):
            await client.searchthreads(query="test", num_threads=0)


# =============================================================================
# TestUserFeedback - Tests for userfeedback method
# =============================================================================


class TestUserFeedback:
    """Tests for userfeedback method."""

    @pytest.mark.asyncio
    async def test_userfeedback_up_success(self, create_async_client, mock_thread_id, mock_request):
        """Test userfeedback with 'up' feedback."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback")
        result = await client.userfeedback(feedback_index=0, feedback="up")
        assert result == "Successfully submitted feedback."

    @pytest.mark.asyncio
    async def test_userfeedback_down_success(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test userfeedback with 'down' feedback."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback")
        result = await client.userfeedback(feedback_index=0, feedback="down")
        assert result == "Successfully submitted feedback."

    @pytest.mark.asyncio
    async def test_userfeedback_remove_success(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test userfeedback with 'remove' feedback."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback")
        result = await client.userfeedback(feedback_index=0, feedback="remove")
        assert result == "Successfully submitted feedback."

    @pytest.mark.asyncio
    async def test_userfeedback_thread_specified_success(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test userfeedback with specified thread_id."""
        client: AsyncFrevaGPT = create_async_client()
        mock_request("userfeedback")
        result = await client.userfeedback(
            feedback_index=0, feedback="up", thread_id=mock_thread_id
        )
        assert result == "Successfully submitted feedback."

    @pytest.mark.asyncio
    async def test_userfeedback_no_thread_raises_type_error(self, create_async_client):
        """Test userfeedback raises TypeError when no thread_id is specified."""
        client: AsyncFrevaGPT = create_async_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to be specified"):
            await client.userfeedback(feedback_index=0, feedback="up")

    @pytest.mark.asyncio
    async def test_userfeedback_invalid_feedback_raises_value_error(
        self, create_async_client, mock_thread_id
    ):
        """Test userfeedback raises ValueError for invalid feedback."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        with pytest.raises(ValueError, match="Feedback string must be one of"):
            await client.userfeedback(feedback_index=0, feedback="invalid")

    @pytest.mark.asyncio
    async def test_userfeedback_thread_not_found_raises_value_error(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test userfeedback raises ValueError when thread is not found."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request(
            "userfeedback",
            status_code=404,
            json={"detail": "Thread not found"},
        )
        with pytest.raises(ValueError, match=f"No thread found for id '{mock_thread_id}'"):
            await client.userfeedback(feedback_index=0, feedback="up")

    @pytest.mark.asyncio
    async def test_userfeedback_feedback_not_found_raises_index_error(
        self, mocker: MockerFixture, create_async_client, mock_request, mock_thread_id
    ):
        """Test that userfeedback raises an IndexError if backend returns a 404 status error with a 'feedback not found' message."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback", status_code=404, text="feedback not found")
        with pytest.raises(IndexError, match="Feedback not found at index "):
            await client.userfeedback(feedback_index=2, feedback="remove")

    @pytest.mark.asyncio
    async def test_userfeedback_general_404_error_raises(
        self, mocker: MockerFixture, create_async_client, mock_request, mock_thread_id
    ):
        """Test that userfeedback raises an Connection if backend returns a 404 status that's not related to previous two cases."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback", status_code=404, text="resource not found")
        with pytest.raises(ConnectionError):
            await client.userfeedback(feedback_index=2, feedback="up")

    @pytest.mark.asyncio
    async def test_userfeedback_index_oob_raises_index_error(
        self, create_async_client, mock_thread_id, mock_request
    ):
        """Test userfeedback raises IndexError when index is out of bounds."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request(
            "userfeedback",
            status_code=422,
            json={"detail": "Index out of bounds"},
        )
        with pytest.raises(IndexError, match="Index 0 is out of bounds."):
            await client.userfeedback(feedback_index=0, feedback="up")

    @pytest.mark.asyncio
    async def test_userfeedback_internal_server_error_raises_connection_error(
        self, mocker: MockerFixture, create_async_client, mock_request, mock_thread_id
    ):
        """Test that userfeedback raises a ConnectionError if backend responds with a internal server error status code (500/503)."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback", status_code=500)
        with pytest.raises(
            ConnectionError, match="Error on the backend saving/modifying feedback."
        ):
            await client.userfeedback(feedback_index=1, feedback="up")
        mock_request("userfeedback", status_code=503)
        with pytest.raises(
            ConnectionError, match="Error on the backend saving/modifying feedback."
        ):
            await client.userfeedback(feedback_index=1, feedback="remove")

    @pytest.mark.asyncio
    async def test_userfeedback_other_status_error_raises(
        self, mocker: MockerFixture, create_async_client, mock_request, mock_thread_id
    ):
        """Test that userfeedback raises an IndexError if backend returns a 422 status error (feedback index out of bounds)."""
        client: AsyncFrevaGPT = create_async_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback", status_code=401)
        with pytest.raises(ConnectionError, match=r"\[Errno 401\] Error connecting to url.*"):
            await client.userfeedback(feedback_index=20, feedback="remove")
