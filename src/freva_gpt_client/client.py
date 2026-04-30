import httpx
from httpx import URL

import json

import getpass
from functools import cached_property
from importlib import metadata
from typing import Iterator, Union

from ._base_client import SyncAPIClient, AsyncAPIClient
from .types import Message, Conversation, Image
from .utils import FREVAGPT_API_ENDPOINTS, DEFAULT_TIMEOUT, DEFAULT_MAX_RETRIES

try:
    __version__ = metadata.version("jupyter_freva_gpt")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"

class FrevaGPT(SyncAPIClient):
    _root_api_path: str = "/api/chatbot"
    _user: str = getpass.getuser()
    _thread_id: str
    model: str
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
            http_client=http_client
        )
        self._thread_id = thread_id
        self.model = model

    @cached_property
    def available_models(self) -> list[str]:
        response=self.get(path=self._construct_path("chatbots"))
        return response.json()
    
    def authenticate(self) -> None:
        self._auth._authenticate()

    def newthread(self) -> str:
        response = self.get(path=self._construct_path("newthread"))
        thread_id = response.json()
        return thread_id
    
    def prompt(self, input: str, model: str = None, thread_id = None) -> Conversation:
        if not (self._thread_id or thread_id):
            self._thread_id = self.newthread()
            thread_id = self._thread_id
        response = self.get(
            path=self._construct_path("streamresponse"),
            params={
                "input": input,
                "thread_id": thread_id,
                "chatbot": model,
            }
        )
        messages = [Message(**json.loads(el)) for el in response.text.split("\n") if el]
        return Conversation(messages=messages)
    
    def stream_prompt(self, input: str, model: str = None, thread_id = None) -> Iterator[Message]:
        if not (self._thread_id or thread_id):
            self._thread_id = self.newthread()
            thread_id = self._thread_id
        for response in self.get(
            path=self._construct_path("streamresponse"),
            params={
                "input": input,
                "thread_id": thread_id,
                "chatbot": model,
            },
            stream=True
        ):
            yield Message(**response)   
         
    def getthread(self, thread_id: str):
        response = self.get(
            path=self._construct_path("getthread"),
            params = {"thread_id": thread_id}    ,
        )
        return Conversation(messages=response.json())
    
    def _cast_message(self, message: Message) -> Union[Message, Image]:
        pass

    def _construct_path(self, endpoint_name:str) -> str:
        return f"{self._root_api_path}/{FREVAGPT_API_ENDPOINTS[endpoint_name]}"
        
class AsyncFrevaGPT(AsyncAPIClient):
    pass