from pydantic import BaseModel
from typing import Literal, Optional, Union, Sequence, Mapping


class Message(BaseModel):
    variant: Literal[
        "Prompt",
        "User",
        "Assistant",
        "Code",
        "CodeOutput",
        "Image",
        "ServerError",
        "OpenAIError",
        "CodeError",
        "StreamEnd",
        "ServerHint",
    ]
    content: Union[str, Sequence[str], Mapping[str, str]]
    id: Optional[str] = None 

class Image(BaseModel):
    base64_image: str
    variant: Literal["Image"]

class Conversation(BaseModel):
    messages: Sequence[Message]

    def _format_messages_for_chat(self) -> str:
        format_str = ""
        current_variant = ""
        for message in self.messages:
            if current_variant != message.variant:
                current_variant = message.variant
                format_str += f"\n{current_variant}: "
            format_str += f"{message.content}"
        return format_str
    
    @property
    def text_output(self) -> str:
        return self._format_messages_for_chat()