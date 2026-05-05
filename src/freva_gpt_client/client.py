import getpass
import json
from functools import cached_property
from importlib import metadata
from typing import Iterator, Union

import httpx
from httpx import URL

from ._base_client import AsyncAPIClient, SyncAPIClient
from ._models import Conversation, Image, MessageModel
from ._utils import (DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT,
                     FREVAGPT_API_ENDPOINTS)

try:
    __version__ = metadata.version("jupyter_freva_gpt")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"


class FrevaGPT(SyncAPIClient):
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
        super().__init__(
            version=__version__,
            base_url=base_url,
            token_store_path=token_store_path,
            follow_redirects=follow_redirects,
            max_retries=max_retries,
            timeout=timeout,
            http_client=http_client,
        )
        self._thread_id = thread_id
        if model and model not in self.available_models:
            raise ValueError(
                f"Model {model} is not a valid selection. Please select from available models: {self.available_models} instead."
            )
        self.model = model

    @cached_property
    def available_models(self) -> list[str]:
        response = self.get(path=self._construct_path("chatbots"))
        available_models = response.json()
        return available_models

    def authenticate(self) -> None:
        self._auth._authenticate()

    def newthread(self) -> str:
        response = self.get(path=self._construct_path("newthread"))
        thread_id = response.json()
        return thread_id

    def prompt(
        self,
        input: str,
        model: str | None = None,
        thread_id: str | None = None,
        stream=False,
    ) -> Conversation | Iterator[MessageModel]:

        if not model and self.model:
            model = self.model
        elif model and not model in self.available_models:
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
            return map(lambda x: MessageModel(message=x), response.iter_json_objects())

    def getthread(self, thread_id: str | None = None):
        if not thread_id and self._thread_id:
            thread_id = self._thread_id
        else:
            raise TypeError(
                f"Argument thread_id has to specified, if no conversation was started previously."
            )
        response = self.get(
            path=self._construct_path("getthread"),
            params={"thread_id": thread_id},
        )
        messages = [MessageModel(message=m) for m in response.json()]
        return Conversation(raw_messages=messages)

    def _cast_message(self, message: MessageModel) -> Union[MessageModel, Image]:
        return message

    def _construct_path(self, endpoint_name: str) -> str:
        return f"{self._root_api_path}/{FREVAGPT_API_ENDPOINTS[endpoint_name]}"


class AsyncFrevaGPT(AsyncAPIClient):
    pass
