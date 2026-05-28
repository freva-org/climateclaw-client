"""Unit tests for FrevaGPT class in client.py."""

import httpx
import pytest
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from freva_gpt_client._base_client import BaseClient
from freva_gpt_client._constants import FREVAGPT_API_ENDPOINTS
from freva_gpt_client.client import FrevaGPT, logger
from freva_gpt_client.models import Conversation, StreamConversation

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def create_client(mocker: MockerFixture, base_url, mock_request):
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
        # Mock the parsing of hosts
        mocked_validate_base_url = mocker.patch.object(BaseClient, "_parse_host")
        mocked_validate_base_url.return_value = base_url

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

    def test_init_all_params(self, base_url, create_client):
        """Test initialization with all parameters."""
        client: FrevaGPT = create_client(
            thread_id="test_thread",
            model="gpt-4.1",
        )
        assert client.base_url == httpx.URL(base_url)
        assert client.thread_id == "test_thread"
        assert client.model == "gpt-4.1"

    def test_init_minimal_params(self, base_url, create_client):
        """Test initialization with minimal parameters."""
        client: FrevaGPT = create_client()
        assert client.base_url == httpx.URL(base_url)
        assert client.thread_id is None
        assert client.model is None

    def test_init_with_http_client(self, base_url, create_client):
        """Test initialization with custom HTTP client."""
        # Create custom client with mock responses
        custom_client = httpx.Client()
        custom_client.base_url = httpx.URL(base_url)

        client: FrevaGPT = create_client(http_client=custom_client)
        assert client._client == custom_client

    def test_init_invalid_model(self, create_client):
        """Test that invalid model raises ValueError."""
        with pytest.raises(ValueError, match="is not a valid selection"):
            create_client(model="invalid_model")

    def test_root_api_path(self, create_client):
        """Test that _root_api_path is set correctly."""
        client: FrevaGPT = create_client()
        assert client._root_api_path == "/api/chatbot"

    def test_construct_path(self, create_client):
        """Test _construct_path method."""
        client = create_client()

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

    def test_validate_backend_endpoints_success(self, create_client):
        """Test successful validation of all endpoints."""
        client = create_client()
        assert client is not None

    def test_validate_backend_endpoints_missing_paths_key(self, create_client):
        """Test that missing 'paths' key raises KeyError."""
        mock_spec = {"openapi": "3.1.0", "info": {"version": "0.1.0"}}  # Missing 'paths'
        with pytest.raises(KeyError, match="Key 'paths' cannot be found"):
            create_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_missing_info_key(self, create_client):
        """Test that missing 'info' key raises KeyError."""
        mock_spec = {"openapi": "3.1.0", "paths": {}}  # Missing 'info'
        with pytest.raises(KeyError, match="Key 'info' cannot be found"):
            create_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_missing_version(self, create_client):
        """Test that missing version in info raises KeyError."""
        mock_spec = {
            "openapi": "3.1.0",
            "info": {},  # Missing 'version'
            "paths": {f"/api/chatbot/{FREVAGPT_API_ENDPOINTS['ping']}": {}},
        }
        with pytest.raises(KeyError, match="version information could not be retrieved"):
            create_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_missing_expected_endpoint(self, create_client):
        """Test that missing expected endpoint raises KeyError."""
        mock_spec = {"openapi": "3.1.0", "info": {"version": "0.1.0"}, "paths": {}}  # Empty paths
        with pytest.raises(KeyError, match="could not be found in backend specification"):
            create_client(openapi_spec=mock_spec)

    def test_validate_backend_endpoints_unexpected_endpoint(
        self,
        mocker: MockerFixture,
        create_client,
        mock_openapi_spec,
    ):
        mock_spec = mock_openapi_spec
        mock_spec["paths"]["/api/chatbot/unexpected_endpoint"] = {}
        spy_logger = mocker.spy(logger, "warning")
        create_client(openapi_spec=mock_spec)
        assert any(
            "API endpoint /api/chatbot/unexpected_endpoint not included in client specification"
            in call.args[0]
            for call in spy_logger.call_args_list
        )


# =============================================================================
# TestAuthenticate - Tests for available_models
# =============================================================================


class TestAuthenticate:
    """Test client authentication method"""

    def test_authenticate(self, mocker: MockerFixture, create_client):
        """Test that authenticate calls TokenAuth _authenticate method."""
        client: FrevaGPT = create_client()
        mock_authenticate = mocker.patch.object(client._auth, "_authenticate")
        client.authenticate()
        mock_authenticate.assert_called_once()


# =============================================================================
# TestModels - Tests for available_models
# =============================================================================


class TestModels:
    """Tests for available models endpoint and getter and setter methods for the model attribute."""

    def test_available_models_success(self, create_client, mock_available_models):
        """Test retrieving available models."""
        client: FrevaGPT = create_client()
        models = client.available_models
        assert models == mock_available_models

    def test_available_models_cached(self, create_client):
        """Test that available_models is cached."""
        client: FrevaGPT = create_client()
        models1 = client.available_models
        models2 = client.available_models
        assert models1 is models2

    def test_available_models_property(self, create_client):
        """Test available_models property."""
        client: FrevaGPT = create_client()
        assert hasattr(client, "available_models")

    def test_model_getter(self, create_client):
        """Test model property getter returns _model attribute."""
        client: FrevaGPT = create_client()
        assert client.model is None
        client._model = "test_model"
        assert client.model == "test_model"

    def test_model_setter(self, create_client):
        """Test model property setter updates _model attribute."""
        client: FrevaGPT = create_client()
        client.available_models = ["test_model", "test_model2"]
        client.model = "test_model"
        assert client._model == "test_model"

    def test_model_setter_invalid_model_raises(self, create_client):
        """Test model setter raises a ValueError if an invalid model is set."""
        client: FrevaGPT = create_client()
        client.available_models = ["test_model", "test_model2"]
        with pytest.raises(ValueError, match=r"Model .* is not a valid selection.*"):
            client.model = "invalid_model"


# =============================================================================
# TestThreadManagement - Tests for thread management methods
# =============================================================================


class TestThreadManagement:
    """Tests for thread management methods."""

    def test_newthread_success(self, create_client, mock_request, mock_thread_id):
        """Test creating a new thread."""
        client: FrevaGPT = create_client()
        assert client.thread_id is None
        mock_request("newthread")
        thread_id = client.newthread()
        assert thread_id == mock_thread_id
        assert client.thread_id == thread_id

    def test_getthread_success(self, create_client, mock_request, mock_thread_id):
        """Test retrieving a thread by ID."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("getthread", is_reusable=True)
        thread = client.getthread()
        assert len(thread.messages) == 2
        assert thread.messages[0].message.variant == "User"
        assert thread.messages[1].message.variant == "Assistant"

    def test_getthread_no_thread_raises_typeerror(self, create_client):
        """Test that getthread raises TypeError if no thread_id provided."""
        client: FrevaGPT = create_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to be specified"):
            client.getthread()

    def test_setthreadtopic_success(self, create_client, mock_request, mock_thread_id):
        """Test setting thread topic."""
        client: FrevaGPT = create_client()
        mock_request("setthreadtopic")

        new_topic = "Test Topic"

        result = client.setthreadtopic(new_topic=new_topic, thread_id=mock_thread_id)
        assert result == new_topic

    def test_setthreadtopic_with_instance_thread_success(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that setthreadtopic correctly uses instance thread id when setting new topic."""
        client: FrevaGPT = create_client()
        mock_request("setthreadtopic")
        client.thread_id = mock_thread_id
        spy_get = mocker.spy(client, "get")
        client.setthreadtopic("Test topic")
        assert spy_get.call_args_list[-1].kwargs["params"]["thread_id"] == client.thread_id

    def test_setthreadtopic_no_thread_raises_typeerror(self, create_client):
        """Test that setthreadtopic raises TypeError if no thread_id provided."""
        client: FrevaGPT = create_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to be specified"):
            client.setthreadtopic(new_topic="Test")

    def test_deletethread_with_specified_thread_success(
        self, create_client, mock_request, mock_thread_id
    ):
        """Test deleting an existing thread as specified in deletethread argument."""
        client: FrevaGPT = create_client()
        mock_request("deletethread")
        client.deletethread(mock_thread_id)

    def test_deletethread_without_specified_thread_success(
        self, create_client, mock_request, mock_thread_id
    ):
        """Test deleting an existing thread without specifying thread, results in instance thread being deleted and reset."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("deletethread")
        client.deletethread()
        assert client.thread_id is None

    def test_deletethread_another_thread_specified_success(
        self, create_client, mock_request, mock_thread_id
    ):
        """Test deleting an existing thread that is not the instance thread is successful but does not reset instance thread id."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("deletethread")
        client.deletethread("another_thread_id")
        assert client.thread_id is not None
        assert client.thread_id == mock_thread_id

    def test_deletethread_no_thread_raises_error(self, create_client):
        """Test that calling deletethread raises a TypeError if no thread is specified and no instance thread id set."""
        client: FrevaGPT = create_client()
        with pytest.raises(TypeError, match=r"Argument 'thread_id' has to be specified.*"):
            client.deletethread()

    def test_editthread_minimal_params_success(
        self, create_client, mock_request, mock_thread_id, mock_new_thread_id
    ):
        """Test that editthread passes successfully and returns with expected result for minimal parameters."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("editthread")
        new_thread_id, branched_conv = client.editthread(user_index=1)
        assert new_thread_id == mock_new_thread_id
        assert isinstance(branched_conv, Conversation)

    def test_editthread_thread_specified_success(
        self, create_client, mock_request, mock_thread_id, mock_new_thread_id
    ):
        """Test that editthread passes successfully and returns with expected result if source_thread_id is specified."""
        client: FrevaGPT = create_client()
        mock_request("editthread")
        new_thread_id, branched_conv = client.editthread(
            user_index=1, source_thread_id=mock_thread_id
        )
        assert new_thread_id == mock_new_thread_id
        assert isinstance(branched_conv, Conversation)

    def test_editthread_not_thread_raises_type_error(self, create_client):
        """Test that calling editthread raises a TypeError if no thread is specified and no instance thread set."""
        client: FrevaGPT = create_client()
        with pytest.raises(TypeError, match="Argument 'source_thread_id' has to be specified"):
            client.editthread(user_index=1)

    def test_editthread_no_thread_found_raises(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that editthread raises a ValueError if backend returns a 404 status error."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("editthread", status_code=404)
        with pytest.raises(ValueError, match=f"No thread found for id '{mock_thread_id}'"):
            client.editthread(user_index=1)

    def test_editthread_user_index_oob_raises(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that editthread raises an IndexError if backend returns a 422 error (indicating user index is out of bounds)."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("editthread", status_code=422)
        with pytest.raises(IndexError, match="User message index 200 out of bounds!"):
            client.editthread(user_index=200)

    def test_editthread_internal_server_error_raises(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that editthread raises a ConnectionError if backend returns a status code other than 200, 404, 422."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("editthread", status_code=500)
        with pytest.raises(
            ConnectionError, match="Editing thread failed due to an internal server error."
        ):
            client.editthread(user_index=200)

    def test_editthread_missing_keys_in_response_raises(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that editthread raises a KeyError if returned json does not contain expected keys."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("editthread", json={"wrong_key": "value"})
        with pytest.raises(
            KeyError,
            match=f"The response to editing thread '{mock_thread_id}' did not include keys",
        ):
            client.editthread(user_index=1)

    def test_userfeedback_minimal_params_success(self, create_client, mock_request, mock_thread_id):
        """Test that user feedback can be successfully submitted using minimal allowd amount of params."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback")
        client.userfeedback(feedback_index=2, feedback="up")

    def test_userfeedback_thread_specified_success(
        self, create_client, mock_request, mock_thread_id
    ):
        """Test that user feedback can be successfully submitted using minimal allowd amount of params."""
        client: FrevaGPT = create_client()
        mock_request("userfeedback")
        client.userfeedback(feedback_index=2, feedback="up", thread_id=mock_thread_id)

    def test_userfeedback_no_thread_raises_type_error(self, create_client):
        """Test that user feedback raises TypeError if no thread is specified and no instance thread set."""
        client: FrevaGPT = create_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to be specified"):
            client.userfeedback(feedback_index=2, feedback="up")

    def test_userfeedback_invalid_feedback_raises_value_error(self, create_client, mock_thread_id):
        """Test that user feedback raises ValueError if string describing feedback is not valid."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        with pytest.raises(ValueError, match="Feedback string must be one of"):
            client.userfeedback(feedback_index=2, feedback="invalid_feedback")

    def test_userfeedback_thread_not_found_raises_value_error(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that userfeedback raises a ValueError if backend returns a 404 status error with a 'thread not found' message."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback", status_code=404, text="thread not found")
        with pytest.raises(ValueError, match="No thread found for id"):
            client.userfeedback(feedback_index=2, feedback="up")

    def test_userfeedback_feedback_not_found_raises_index_error(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that userfeedback raises an IndexError if backend returns a 404 status error with a 'feedback not found' message."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback", status_code=404, text="feedback not found")
        with pytest.raises(IndexError, match="Feedback not found at index "):
            client.userfeedback(feedback_index=2, feedback="remove")

    def test_userfeedback_index_oob_raises_index_error(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that userfeedback raises an IndexError if backend returns a 422 status error (feedback index out of bounds)."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback", status_code=422)
        with pytest.raises(IndexError, match="Index 20 is out of bounds."):
            client.userfeedback(feedback_index=20, feedback="remove")

    def test_userfeedback_internal_server_error_raises_connection_error(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that userfeedback raises a ConnectionError if backend responds with a internal server error status code (500/503)."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback", status_code=500)
        with pytest.raises(
            ConnectionError, match="Error on the backend saving/modifying feedback."
        ):
            client.userfeedback(feedback_index=1, feedback="up")
        mock_request("userfeedback", status_code=503)
        with pytest.raises(
            ConnectionError, match="Error on the backend saving/modifying feedback."
        ):
            client.userfeedback(feedback_index=1, feedback="remove")

    def test_userfeedback_other_status_error_raises(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that userfeedback raises an IndexError if backend returns a 422 status error (feedback index out of bounds)."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("userfeedback", status_code=401)
        with pytest.raises(ConnectionError, match=r"\[Errno 401\] Error connecting to url.*"):
            client.userfeedback(feedback_index=20, feedback="remove")


# =============================================================================
# TestPrompting - Tests for prompt method
# =============================================================================


class TestPrompting:
    """Tests for streaming and non-streaming prompting."""

    def test_prompt_non_stream_success(
        self, create_client, mock_request, mock_available_models, mock_thread_id
    ):
        """Test non-streaming prompt returns Conversation."""
        client: FrevaGPT = create_client(model=mock_available_models[0])
        client.thread_id = mock_thread_id
        mock_request("streamresponse", stream=False)
        result = client.prompt("Test prompt", model=client.model, stream=False)

        assert isinstance(result, Conversation)

    def test_prompt_non_stream_minimal_params_success(
        self,
        create_client,
        mock_request,
        mock_available_models,
    ):
        """Test non-streaming prompt with minimal parameters."""
        client: FrevaGPT = create_client(
            model=mock_available_models[0]
        )  # set model, so it can be skipped in the prompt
        assert client.thread_id is None
        mock_request("newthread")
        mock_request("streamresponse", stream=False)
        result = client.prompt(
            "Test prompt",
        )
        assert isinstance(result, Conversation)
        assert len(result.messages) == 2

    def test_prompt_non_stream_minimal_params_set_thread_success(
        self,
        create_client,
        mock_request,
        mock_available_models,
        mock_thread_id,
    ):
        """Test non-streaming prompt with minimal parameters and set thread id."""
        client: FrevaGPT = create_client(model=mock_available_models[0])

        client.thread_id = mock_thread_id
        mock_request("streamresponse", stream=False)
        result = client.prompt(
            "Test prompt",
        )
        assert isinstance(result, Conversation)
        assert len(result.messages) == 2

    def test_prompt_stream_success(
        self,
        httpx_mock: HTTPXMock,
        create_client,
        mock_request,
        mock_available_models,
        mock_thread_id,
    ):
        """Test streaming prompt returns Conversation."""
        client: FrevaGPT = create_client()
        client.model = mock_available_models[0]
        mock_request("streamresponse", stream=True)

        result = client.prompt(
            "Test prompt", model=client.model, thread_id=mock_thread_id, stream=True
        )

        assert isinstance(result, StreamConversation)
        conv = result.translate_to_conversation()
        assert len(conv.messages) == 2

    def test_prompt_no_model_raises_typeerror(self, create_client, mock_thread_id):
        """Test that prompt raises TypeError if no model specified."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id

        with pytest.raises(TypeError, match="Argument 'model' has to be specified"):
            client.prompt(input="Test", thread_id=mock_thread_id)

    def test_prompt_invalid_model_raises_valueerror(self, create_client, mock_thread_id):
        """Test that prompt raises ValueError for invalid model."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id

        with pytest.raises(ValueError, match=r"Value .* is not a valid selection"):
            client.prompt(input="Test", model="invalid_model", thread_id=mock_thread_id)

    def test_prompt_keyboard_interrupt_sends_stop(
        self, mocker: MockerFixture, create_client, mock_available_models, mock_thread_id
    ):
        "Test that a KeyboardInterrupt event leads to a call to the stop method."
        client: FrevaGPT = create_client(model=mock_available_models[0])
        client.thread_id = mock_thread_id
        client.stop = mocker.MagicMock()
        client.get = mocker.Mock(side_effect=KeyboardInterrupt)
        with pytest.raises(KeyboardInterrupt):
            client.prompt("Test prompt", model=client.model, stream=False)
        client.get.assert_called_once()
        client.stop.assert_called_once()

    def test_stop_with_specified_thread_id_success(
        self, create_client, mock_thread_id, mock_request
    ):
        """Test that stop for a specified thread is executed as expected."""
        client: FrevaGPT = create_client()
        mock_request("stop")
        result = client.stop(mock_thread_id)
        assert result is True

    def test_stop_with_default_thread_id_success(
        self,
        mocker: MockerFixture,
        create_client,
        mock_thread_id,
        mock_request,
    ):
        """Test that stop for a specified thread is executed as expected."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("stop")
        spy_get = mocker.spy(client, "get")
        result = client.stop()
        assert result is True
        assert spy_get.call_args_list[-1].kwargs["params"]["thread_id"] == client.thread_id

    def test_stop_no_thread_raises_type_error(self, create_client):
        """Test that stop raises a TypeError if no thread is specified and no instance thread id is set."""
        client: FrevaGPT = create_client()
        with pytest.raises(TypeError, match="Argument 'thread_id' has to be specified"):
            client.stop()

    def test_stop_no_active_thread_success(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that stop triggers a warning message if no active thread can be found for given thread id."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("stop", status_code=404)
        spy_logger = mocker.spy(logger, "warning")
        result = client.stop()
        spy_logger.assert_called_with(
            f"No active thread could be found under thread_id {mock_thread_id}."
        )
        assert result is True

    def test_stop_internal_server_error_raises(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that stop triggers an error if backend responds with a 505 internal-error status message."""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("stop", status_code=505)
        with pytest.raises(
            ConnectionError, match="Could not stop thread due to an internal server error."
        ):
            client.stop()

    def test_stop_other_http_error_raises(
        self, mocker: MockerFixture, create_client, mock_request, mock_thread_id
    ):
        """Test that stop handles http statuses that are not 200, 404, 505 differently"""
        client: FrevaGPT = create_client()
        client.thread_id = mock_thread_id
        mock_request("stop", status_code=401)
        with pytest.raises(ConnectionError, match=r"\[Errno 401\] Error connecting to url.*"):
            client.stop()


# =============================================================================
# TestThreadSearch - Tests for getuserthreads and searchthreads
# =============================================================================


class TestThreadSearch:
    """Tests for user thread search methods."""

    def test_getuserthreads_success(
        self, create_client, mock_request, mock_thread_list, mock_thread_id
    ):
        """Test retrieving user threads."""
        client: FrevaGPT = create_client()
        mock_request("getuserthreads")

        total, threads = client.getuserthreads(num_threads=5)

        assert total == min(5, len(mock_thread_list))
        assert len(threads) == total
        assert threads[0]["thread_id"] == mock_thread_id
        assert threads[0]["topic"] == "Test Topic"
        assert isinstance(threads[0]["content"], Conversation)

    def test_getuserthreads_zero_num_threads_raises_valueerror(self, create_client):
        """Test that getuserthreads raises ValueError for num_threads <= 0."""
        client: FrevaGPT = create_client()
        with pytest.raises(ValueError, match="has to be at least 1"):
            client.getuserthreads(num_threads=0)

    def test_searchthreads_success(self, create_client, mock_request, mock_thread_list):
        """Test searching threads by query."""
        client: FrevaGPT = create_client()
        mock_request("searchthreads")

        total, results = client.searchthreads(query="ENSO", num_threads=5)

        assert total == min(5, len(mock_thread_list))
        assert len(results) == total
        assert results[1]["topic"] == "ENSO Discussion"

    def test_searchthreads_zero_num_threads_raises_valueerror(self, create_client):
        """Test that searchthreads raises ValueError for num_threads <= 0."""
        client: FrevaGPT = create_client()
        with pytest.raises(ValueError, match="has to be at least 1"):
            client.searchthreads(query="test", num_threads=0)
