import getpass
import json
import logging
from functools import cached_property
from importlib import metadata
from typing import Any, Dict, List, Literal, Tuple, Union, cast

import httpx
from httpx import URL

from ._base_client import AsyncAPIClient, SyncAPIClient
from ._constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    FREVAGPT_API_ENDPOINTS,
    OPENAPI_SPEC_PATH,
)
from ._streaming import StreamResponse
from .models import Conversation, Image, MessageModel, StreamConversation

try:
    __version__ = metadata.version("freva-gpt-client")
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
    def available_models(self) -> List[str]:
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
        stream: bool = False,
    ) -> Conversation | StreamConversation:
        """Sends a prompt to the chatbot and gets the response.

        Args:
            input: The user input/prompt to send.
            model: Optional model to use for this request. Falls back to instance attribute if not specified.
            thread_id: Optional thread ID for the conversation. Creates a new thread if not specified and no active thread exists.
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
                f"Value '{model}' is not a valid selection for param 'model'. Please select from available models: {self.available_models} instead."
            )
        elif not model and not self.model:
            raise TypeError(
                f"Argument 'model' has to specified, unless instance attribute '{self.__class__.__name__}.model' is set."
            )

        if not (self._thread_id or thread_id):
            thread_id = self.newthread()
            self._thread_id = thread_id
        elif thread_id:
            self._thread_id = thread_id
        else:
            thread_id = self._thread_id
        try:
            response: httpx.Response | StreamResponse = self.get(
                path=self._construct_path("streamresponse"),
                params={
                    "input": input,
                    "thread_id": thread_id,
                    "chatbot": model,
                },
                stream=stream,
            )
        except KeyboardInterrupt:
            logger.debug("Registered keyboard-interrupt. Stopping thread.")
            self.stop(thread_id=thread_id)
            raise
        if not stream:
            response = cast(httpx.Response, response)
            messages = [
                MessageModel(message=json.loads(el)) for el in response.text.split("\n") if el
            ]
            return Conversation(raw_messages=messages)
        else:
            response = cast(StreamResponse, response)
            return StreamConversation(
                stream=response, on_exit_callback=lambda: self.stop(thread_id)
            )

    def getthread(self, thread_id: str | None = None) -> Conversation:
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
        elif not (thread_id or self._thread_id):
            raise TypeError(
                "Argument 'thread_id' has to specified, if no conversation was started previously."
            )
        response = self.get(
            path=self._construct_path("getthread"),
            params={"thread_id": thread_id},
        )
        messages = [MessageModel(message=m) for m in response.json()]
        return Conversation(raw_messages=messages)

    def getuserthreads(
        self, num_threads: int = 20
    ) -> Tuple[int, List[Dict[str, str | Conversation]]]:
        """Retrieve the most recent conversation threads of the authenticated user, limited by the requested number.

        Args:
            num_threads (int): The maximum number of recent threads to return. Defaults to 20.

        Returns:
            A tuple with two elements: 1. the total number of threads available for the user and 2. a list containing dictionaries
            that include information on each thread retrieved, such as "thread_id", "date", and "topic", as well as "content",
            which includes the thread's messages as a Conversation object.

        Raises:
            ValueError: Raised if integer num_threads is 0 or smaller.
        """
        if num_threads <= 0:
            raise ValueError("Value 'num_threads' has to be at least 1.")
        response: httpx.Response = self.get(
            path=self._construct_path("getuserthreads"),
            params={
                "num_threads": num_threads,
                "page": 0,  # currently hardcoded to be 0 (other values seem to always return an empty list)
            },
        )
        user_threads: List[Dict[str, Any]] = response.json()[0]
        n_threads: int = response.json()[1]

        def map_key_value(k: str, v: Any):
            return (
                Conversation(raw_messages=[MessageModel(message=m) for m in v])
                if k.lower() == "content"
                else str(v)
            )

        thread_data = [
            {key: map_key_value(key, value) for key, value in ut.items()} for ut in user_threads
        ]
        return n_threads, thread_data

    def deletethread(self, thread_id: str | None = None) -> None:
        """
        Delete a given thread by the authenticated user.

        Args:
            thread_id (str | None, optional): The ID of the thread to be deleted on the backend. If not specified, uses the current active thread ID.

        Raises:
            TypeError: Raised, if no thread_id is specified and no previous conversation was started.
        """
        if not thread_id and self._thread_id:
            thread_id = self._thread_id
        elif not (thread_id or self._thread_id):
            raise TypeError(
                "Argument 'thread_id' has to specified, if no conversation was started previously."
            )
        self.get(path=self._construct_path("deletethread"), params={"thread_id": thread_id})

    def setthreadtopic(self, new_topic: str, thread_id: str | None = None) -> str:
        """Sets the topic of a given thread.
        Thread topics can be used to search threads (see `searchthreads`).

        Args:
            new_topic (str): String describing the new thread topic.
            thread_id (str | None, optional): The ID of the thread which topic should be changed. If not specified, uses the current active thread ID.

        Raises:
            TypeError: Raised, if no thread_id is specified and no previous conversation was started.

        Returns:
            str: The new thread topic.
        """
        if not thread_id and self._thread_id:
            thread_id = self._thread_id
        elif not (thread_id or self._thread_id):
            raise TypeError(
                "Argument 'thread_id' has to specified, if no conversation was started previously."
            )
        self.get(
            path=self._construct_path("setthreadtopic"),
            params={"thread_id": thread_id, "topic": new_topic},
        )
        return new_topic

    def searchthreads(
        self, query: str, num_threads: int = 20
    ) -> Tuple[int, List[Dict[str, str | Conversation]]]:
        """Search the authenticated user's conversation threads using a query string. Supports only topic-based search.

        Args:
            query (str): The search query string.
            num_threads (int, optional): The maximum number of results to return. Defaults to 20.

        Returns:
            A tuple with two elements: 1. the total number of threads available for the user and 2. a list containing dictionaries
            that include information on each thread retrieved, such as "thread_id", "date", and "topic", as well as "content",
            which includes the thread's messages as a Conversation object.

        Raises:
            ValueError: Raised if integer num_threads is 0 or smaller.
        """
        if num_threads <= 0:
            raise ValueError("Value 'num_threads' has to be at least 1.")
        response: httpx.Response = self.get(
            path=self._construct_path("searchthreads"),
            params={
                "query": query,
                "num_threads": num_threads,
            },
        )
        user_threads, n_threads = response.json()

        def map_key_value(k: str, v: Any):
            return (
                Conversation(raw_messages=[MessageModel(message=m) for m in v])
                if k.lower() == "content"
                else str(v)
            )

        thread_data = [
            {key: map_key_value(key, value) for key, value in ut.items()} for ut in user_threads
        ]
        return n_threads, thread_data

    def stop(self, thread_id: str | None = None) -> bool:
        """Stop an active streaming conversation, cancels any in-flight tool executions on the backend.

        Args:
            thread_id (str | None, optional): The ID of the thread which should be stopped. If not specified, uses the current active thread ID.

        Raises:
            TypeError: Raised if thread_id is not specified and no active thread exists.
            ConnectionError: Raised if the request results in an internal server error.

        Returns:
            True if thread was stopped successfully (without an error).
        """
        if not thread_id and self._thread_id:
            thread_id = self._thread_id
        elif not (thread_id or self._thread_id):
            raise TypeError(
                "Argument 'thread_id' has to specified, if no conversation was started previously."
            )
        try:
            self.get(path=self._construct_path("stop"), params={"thread_id": thread_id})
            return True
        except ConnectionError as e:
            if e.errno == 404:
                logger.warning(f"No active thread could be found under thread_id {thread_id}.")
                return True
            elif e.errno == 505:
                raise ConnectionError(
                    "Could not stop thread due to an internal server error."
                ) from e
            raise

    def editthread(
        self, user_index: int, source_thread_id: str | None = None
    ) -> Tuple[str, Conversation]:
        """Fork an existing conversation thread at a given message index.
        This causes the endpoint to create a new thread by copying the message history of an existing thread up to the edited message.
        The specified message and all subsequent messages are discarded in the new branch, allowing the client to replace or modify the conversation from that point onward.

        Args:
            user_index (int): The (zero-based) index from which to fork the conversation.
            source_thread_id (str | None, optional): The ID of the thread which should be forked. If not specified, uses the current active thread ID.

        Raises:
            TypeError: Raised if thread_id is not specified and no active thread exists.
            ValueError: Raised if given thread cannot be found by the backend.
            IndexError: Raised if the user index is out of bounds, as indicated by the backend.
            ConnectionError: Raised in case server responds with an internal error message.
            KeyError: Raised if the response does not include the keys 'new_thread_id' or 'history'.

        Returns:
            Tuple[str, Conversation]: A tuple containing both the new thread id and a Conversation object that encapsulates the message history from which the new thread starts from.
        """
        if not source_thread_id and self._thread_id:
            source_thread_id = self._thread_id
        elif not (source_thread_id or self._thread_id):
            raise TypeError(
                "Argument 'source_thread_id' has to specified, if no conversation was started previously."
            )
        try:
            response: httpx.Response = self.get(
                path=self._construct_path("editthread"),
                params={
                    "source_thread_id": source_thread_id,
                    "user_index": user_index,
                },
            )
        except ConnectionError as e:
            if e.errno == 404:
                raise ValueError(f"No thread found for id '{source_thread_id}'!")
            elif e.errno == 422:
                raise IndexError(f"User message index {user_index} out of bounds!")
            else:
                raise ConnectionError(
                    "Editing thread failed due to an internal server error."
                ) from e
        response_dict: Dict[str, Any] = response.json()
        if not response_dict.keys() >= (expected_keys := {"new_thread_id", "history"}):
            raise KeyError(
                f"The response to editing thread '{source_thread_id}' did not include keys {expected_keys}."
            )
        new_thread_id = response_dict["new_thread_id"]
        history = Conversation(
            raw_messages=[MessageModel(message=m) for m in response_dict["history"]]
        )
        return new_thread_id, history

    def userfeedback(
        self,
        feedback_index: int,
        feedback: Literal["up", "down", "remove"],
        thread_id: str | None = None,
    ) -> str:
        """Submit or modify to a specific message within a thread.

        Args:
            feedback_index (int): The (zero-based) index of the (Code, Assistant) message within a thread where feedback should be added or removed.
            feedback (str): Feedback to be submitted. Must be one of 'up' (positive), 'down' (negative) or 'remove' (remove any existing feedback from message).
            thread_id (str | None, optional): The ID of the thread containing the message feedback should be submitted for. If not specified, uses the current active thread ID.

        Raises:
            TypeError: Raised if thread_id is not specified and no active thread exists.
            ValueError: Raised if feedback string is not one of 'up', 'down', 'remove', or if thread cannot be found by backend.
            IndexError: Raised if feedback cannot be found at given index (in case of removal) or if index is out of bounds.
            ConnectionError: Raised if feedback submission results in a internal server error on the backend.

        Returns:
            Detail message returned by the backend, or warning if the response was empty.

        """
        if not thread_id and self._thread_id:
            thread_id = self._thread_id
        elif not (thread_id or self._thread_id):
            raise TypeError(
                "Argument 'thread_id' has to specified, if no conversation was started previously."
            )
        if feedback not in (allowed_feedback := ["up", "down", "remove"]):
            raise ValueError(f"Feedback string must be one of {allowed_feedback}.")
        try:
            response: httpx.Response = self.get(
                path=self._construct_path("userfeedback"),
                params={
                    "thread_id": thread_id,
                    "feedback_index": feedback_index,
                    "feedback": feedback,
                },
            )
            response_dict: Dict[str, str] = response.json()
            message: str = response_dict.get(
                "detail",
                "Empty message was returned. User feedback was possibly not correctly processed by the backend.",
            )
            return message
        except ConnectionError as e:
            if e.errno == 404:
                if e.strerror and "thread not found" in e.strerror.lower():
                    raise ValueError(f"No thread found for id '{thread_id}'.")
                elif e.strerror and "feedback not found" in e.strerror.lower():
                    raise IndexError(
                        f"Feedback not found at index {feedback_index} for thread '{thread_id}'."
                    )
            elif e.errno == 422:
                raise IndexError(f"Index {feedback_index} is out of bounds.")
            elif e.errno in (500, 503):
                raise ConnectionError("Error on the backend saving/modifying feedback.")
            raise

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
