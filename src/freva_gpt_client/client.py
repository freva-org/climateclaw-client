import getpass
import json
import logging
from functools import cached_property
from importlib import metadata
from typing import Iterator, Union

import httpx
from httpx import URL

from ._base_client import AsyncAPIClient, SyncAPIClient
from ._models import Conversation, Image, MessageModel, StreamConversation
from ._utils import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, FREVAGPT_API_ENDPOINTS, OPENAPI_SPEC_PATH

try:
    __version__ = metadata.version("jupyter_freva_gpt")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"

logger = logging.getLogger(__name__)


class FrevaGPT(SyncAPIClient):
    """Synchronous client for interacting with the FrevaGPT API.

    This class provides a high-level interface for communicating with the
    FrevaGPT chatbot API, including methods for managing threads, sending
    prompts, and retrieving conversation history.

    Attributes:
        _root_api_path: Base path for API endpoints.
        _user: Current system user.
        _thread_id: Current active thread ID.
        model: Selected chatbot model.
    """

    _root_api_path: str = "/api/chatbot"
    _user: str = getpass.getuser()
    _thread_id: str | None
    model: str | None

    def __init__(
        self,
        *,
        base_url: str | URL,
        token_store_path: str = "",
        follow_redirects: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
        thread_id: str | None = None,
        model: str | None = None,
    ):
        """Initializes the FrevaGPT client.

        Args:
            base_url: Base URL for the FrevaGPT API.
            token_store_path: Path to store authentication tokens.
            follow_redirects: Whether to follow HTTP redirects.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
            http_client: Optional pre-configured httpx.Client.
            thread_id: Optional thread ID for an existing conversation.
            model: Optional chatbot model to use for requests.

        Raises:
            ValueError: If the specified model is not in available_models.
        """
        super().__init__(
            version=__version__,
            base_url=base_url,
            token_store_path=token_store_path,
            follow_redirects=follow_redirects,
            max_retries=max_retries,
            timeout=timeout,
            http_client=http_client,
        )
        self._validate_backend_endpoints()
        self._thread_id = thread_id
        if model and model not in self.available_models:
            raise ValueError(
                f"Model {model} is not a valid selection. Please select from available models: {self.available_models} instead."
            )
        self.model = model

    @cached_property
    def available_models(self) -> list[str]:
        """Gets the list of available chatbot models.

        Returns:
            List of available model names.
        """
        response = self.get(path=self._construct_path("chatbots"))
        available_models = response.json()
        return available_models

    def _validate_backend_endpoints(self) -> None:
        """Validates chatbot endpoints available on the backend against those expected by the client.

        Fetches the OpenAPI spec from the backend and verifies that all expected
        endpoints are available. Also checks for unexpected endpoints and logs warnings.

        Raises:
            KeyError: If required keys ('paths', 'info') are missing from the OpenAPI spec,
                or if expected endpoints are not found in the backend specification.
        """
        r: httpx.Response = self.get(
            path=f"{self._root_api_path}/{OPENAPI_SPEC_PATH}", stream=False
        )
        openapi_spec = r.json()
        if (key := "paths") not in openapi_spec or (key := "info") not in openapi_spec:
            raise KeyError(
                f"Key '{key}' cannot be found in openapi spec file located under {self.base_url.join(f'{self._root_api_path}/{OPENAPI_SPEC_PATH}')}. Make sure backend is configured correctly."
            )
        # get version info from openapi spec file
        if "version" not in openapi_spec["info"]:
            raise KeyError(
                "FrevaGPT backend version information could not be retrieved from openapi spec file. Make sure backend is configured correctly."
            )
        frevagpt_backend_version = openapi_spec["info"]["version"]
        # filter relevant paths specific to chatbot
        chatbot_paths = list(
            filter(lambda p: self._root_api_path in p, openapi_spec["paths"].keys())
        )
        # first check that all endpoints located on the backend are included in the client specification, raise warnings if unexpected enpoints are encountered
        for found_path in chatbot_paths:
            if found_path not in map(self._construct_path, FREVAGPT_API_ENDPOINTS.keys()):
                logger.warning(
                    f"API endpoint {found_path} not included in client specification. The client (version {self._version}) might not be compatible with the backend (version {frevagpt_backend_version})."
                )
        # now check that all endpoints expected by the client are available on the backend, raise a KeyError if at least one cannot be found.
        for endpoint in FREVAGPT_API_ENDPOINTS.keys():
            if (expected_endpoint := self._construct_path(endpoint)) not in chatbot_paths:
                raise KeyError(
                    f"FrevaGPT client expected endpoint {expected_endpoint} could not be found in backend specification. Make sure that client (version {self._version}) and backend (version {frevagpt_backend_version}) are up-to-date."
                )

    def authenticate(self) -> None:
        """Authenticates the client with the FrevaGPT API.

        Triggers the OIDC authentication flow.
        """
        self._auth._authenticate()

    def newthread(self) -> str:
        """Creates a new conversation thread.

        Returns:
            The ID of the newly created thread.
        """
        response = self.get(path=self._construct_path("newthread"))
        thread_id = response.json()
        return thread_id

    def prompt(
        self,
        input: str,
        model: str | None = None,
        thread_id: str | None = None,
        stream=False,
    ) -> Conversation | StreamConversation:
        """Sends a prompt to the chatbot and gets the response.

        Args:
            input: The user input/prompt to send.
            model: Optional model to use for this request. Falls back to
                instance attribute if not specified.
            thread_id: Optional thread ID for the conversation. Creates a
                new thread if not specified and no active thread exists.
            stream: If True, returns a StreamConversation for streaming.

        Returns:
            If stream=False: Conversation containing all messages.
            If stream=True: StreamConversation, allowing for incremental streaming as markdown strings.

        Raises:
            ValueError: If model is specified but not in available_models.
            TypeError: If model is not specified and instance has no model set.
        """

        if not model and self.model:
            model = self.model
        elif model and model not in self.available_models:
            raise ValueError(
                f"Model {model} is not a valid selection. Please select from available models: {self.available_models} instead."
            )
        elif not model and not self.model:
            raise TypeError(
                f"Argument model has to specified, unless instance attribute {self.__class__.__name__}.model is set."
            )

        if not (self._thread_id or thread_id):
            thread_id = self.newthread()
            self._thread_id = thread_id
        elif thread_id:
            self._thread_id = thread_id
        else:
            thread_id = self._thread_id

        response = self.get(
            path=self._construct_path("streamresponse"),
            params={
                "input": input,
                "thread_id": thread_id,
                "chatbot": model,
            },
            stream=stream,
        )
        if not stream:
            messages = [
                MessageModel(message=json.loads(el)) for el in response.text.split("\n") if el
            ]
            return Conversation(raw_messages=messages)
        else:
            return StreamConversation(stream=response)

    def getthread(self, thread_id: str | None = None):
        """Retrieves a conversation thread by ID.

        Args:
            thread_id: The ID of the thread to retrieve. If not specified,
                uses the current active thread ID.

        Returns:
            Conversation containing all messages in the thread.

        Raises:
            TypeError: If thread_id is not specified and no active thread exists.
        """
        if not thread_id and self._thread_id:
            thread_id = self._thread_id
        else:
            raise TypeError(
                "Argument thread_id has to specified, if no conversation was started previously."
            )
        response = self.get(
            path=self._construct_path("getthread"),
            params={"thread_id": thread_id},
        )
        messages = [MessageModel(message=m) for m in response.json()]
        return Conversation(raw_messages=messages)

    def _cast_message(self, message: MessageModel) -> Union[MessageModel, Image]:
        """Casts a message to the appropriate type.

        Args:
            message: The message to cast.

        Returns:
            The message cast to the appropriate type (MessageModel or Image).
        """
        return message

    def _construct_path(self, endpoint_name: str) -> str:
        """Constructs the full API path for an endpoint.

        Args:
            endpoint_name: Name of the endpoint from FREVAGPT_API_ENDPOINTS.

        Returns:
            Full path string combining root API path and endpoint path.
        """
        return f"{self._root_api_path}/{FREVAGPT_API_ENDPOINTS[endpoint_name]}"


class AsyncFrevaGPT(AsyncAPIClient):
    """Asynchronous client for interacting with the FrevaGPT API.

    This class provides an async high-level interface for communicating with
    the FrevaGPT chatbot API. Inherits from AsyncAPIClient and will have
    async versions of the methods implemented in FrevaGPT.

    Note:
        Async methods are not yet implemented - this class currently serves
        as a placeholder for future async support.
    """

    pass
