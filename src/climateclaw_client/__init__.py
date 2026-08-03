from ._version import get_versions
from .client import AsyncClimateClaw, ClimateClaw
from .models import (
    Assistant,
    Code,
    CodeOutput,
    Conversation,
    Image,
    Prompt,
    StreamConversation,
    User,
)

__version__ = get_versions()["version"]
__all__ = [
    "AsyncClimateClaw",
    "ClimateClaw",
    "Assistant",
    "Code",
    "CodeOutput",
    "Conversation",
    "Image",
    "Prompt",
    "StreamConversation",
    "User",
    "__version__",
]

del get_versions
