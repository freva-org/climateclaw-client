"""Utility constants and configurations for the FrevaGPT client.

This module contains default configuration values and API endpoint mappings
used throughout the client.
"""

DEFAULT_MAX_RETRIES = 10
DEFAULT_TIMEOUT = 20.0
DEFAULT_AUTH_TIMEOUT = 30.0

OPENAPI_SPEC_PATH = "openapi.json"

FREVAGPT_API_ENDPOINTS = {
    "ping": "ping",
    "help": "help",
    "chatbots": "availablechatbots",
    "getthread": "getthread",
    "getuserthreads": "getuserthreads",
    "deletethread": "deletethread",
    "newthread": "newthread",
    "setthreadtopic": "setthreadtopic",
    "searchthreads": "searchthreads",
    "streamresponse": "streamresponse",
    "stop": "stop",
    "editthread": "editthread",
    "userfeedback": "userfeedback",
}
