import base64
import re

from functools import cached_property
from pydantic import BaseModel, Field, computed_field
from pathlib import Path
from typing import Any, Literal, Optional, Union, Sequence, Mapping



class BaseMessage(BaseModel):
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
    content: Union[str, Sequence[str], Mapping[str, Any]]
    id: Optional[str] = None 

    def repr_content(self) -> str:
        return str(self.content)

class Prompt(BaseMessage):
    variant: Literal["Prompt"]
class User(BaseMessage):
    variant: Literal["User"]
class Assistant(BaseMessage):
    variant: Literal["Assistant"]
class Code(BaseMessage):
    variant: Literal["Code"]
class CodeOutput(BaseMessage):
    variant: Literal["CodeOutput"]
class ServerError(BaseMessage):
    variant: Literal["ServerError"]
class OpenAIError(BaseMessage):
    variant: Literal["OpenAIError"]
class CodeError(BaseMessage):
    variant: Literal["CodeError"]
class StreamEnd(BaseMessage):
    variant: Literal["StreamEnd"]
class ServerHint(BaseMessage):
    variant: Literal["ServerHint"]
class Image(BaseMessage):
    variant: Literal["Image"]

    def repr_content(self) -> str:
        """
        Representation used when producing message as a string to the user. 
        """
        # Only show the first 10 characters of the base64 encoded image string 
        content = f"{self.content[:10]}..."
        return content
    def markdown_repr(self) -> str:
        markdown_str = f"![Image](data:image/png;base64,){self.content}"
        return markdown_str
    def save_to_file(self, output_path: Path | str):
        output_path = Path(output_path)
        if not (parent_dir:=output_path.parent).exists():
            raise ValueError(f"The directory {parent_dir} does not exist. Please make sure you are saving the image to an existing directory.")
        base64_bytes = self.content.encode("utf-8")
        image_data=base64.decodebytes(base64_bytes)
        with output_path.open(mode="wb") as fw:
            fw.write(image_data)

class MessageModel(BaseModel):
    message: Union[Prompt, User, Assistant, Code, CodeOutput, Image, ServerError, OpenAIError, CodeError, StreamEnd, ServerHint] = Field(discriminator="variant")

class Conversation(BaseModel):
    raw_messages: Sequence[MessageModel] = Field(repr=False)

    def _format_messages_for_chat(self) -> str:
        format_str = ""
        for i, mm in enumerate(self.messages):
            format_str += f"[{i}] {mm.message.variant}: {mm.message.repr_content()}\n"
        return format_str
  
    @computed_field
    @cached_property
    def messages(self) -> list[MessageModel]:
        """
        Appends message chunks to create complete messages along the variants of the messages.
        """
        current_content = ""
        current_variant = ""
        result = []
        for m in self.raw_messages:
            if current_variant != m.message.variant:
                if current_variant and current_content: 
                    result.append(
                        MessageModel(
                            message={"variant" : current_variant, "content" : current_content}
                        )
                    )
                    current_content = ""
                current_variant = m.message.variant
            current_content += str(m.message.content)
        result.append(
            MessageModel(
                message={"variant" : current_variant, "content" : current_content}
            )
        )
        return result
    
    @computed_field(repr=False)
    @cached_property
    def code_cells(self) -> list[str]:
        """
        Extracts python code cells from the conversation instance.
        """
        result = []
        for mm in self.messages:
                if mm.message.variant in ["Assistant", "Code"]:
                    string = str(mm.message.content)
                    matches = re.findall(r"(?:```python)((?:\n(?!.*```python).*)+)(?:```)", string, flags=re.MULTILINE) 
                    for m in matches:
                        result.append(m)
        return result
        

    def __str__(self) -> str:
        return self._format_messages_for_chat()