from py_oidc_auth_client import authenticate, TokenStore, Token
from py_oidc_auth_client.exceptions import AuthError
from pydantic import BaseModel, Field, model_validator
from typing import AsyncIterator, Iterator

class Client(BaseModel):
    pass
