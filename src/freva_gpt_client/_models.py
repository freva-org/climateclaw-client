import base64
import json
import re
from contextlib import ContextDecorator
from functools import cached_property
from pathlib import Path
from typing import Any, Self, Literal, Mapping, Optional, Sequence, TypedDict, Union

from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator, validator

from ._streaming import StreamResponse


class BaseMessage(BaseModel):
    """Base model for all message types in a conversation.

    Attributes:
        variant: The type of message (e.g., User, Assistant, Code, etc.).
        content: The content of the message.
        id: Optional unique identifier for the message.
    """

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
        """Returns a string representation of the message content.

        Returns:
            String representation of the content.
        """
        return str(self.content)

    def repr_markdown(self) -> str:
        return str(self.content)

    @computed_field(repr=False) # type: ignore[prop-decorator]
    @cached_property
    def code_cells(self) -> list[str]:
        """Representation of code cells included in a given message. By default returns an empty list."""
        return []
    
    def __repr__(self):
        content_str = self.repr_content()
        if len(content_str) < 10:
            content = content_str
        else:
            content = f"{content_str[:10]}..."
        return f"{self.__class__.__name__}(variant={self.variant}, content={content}, id={self.id})"


class Prompt(BaseMessage):
    """A prompt message."""

    variant: Literal["Prompt"]


class User(BaseMessage):
    """A user message."""

    variant: Literal["User"]


class Assistant(BaseMessage):
    """An assistant message."""

    variant: Literal["Assistant"]

    @computed_field # type: ignore[prop-decorator]
    @cached_property
    def code_cells(self) -> list[str]:
        """Extracts python code cells from the assistant message.

        Finds all Python code blocks (between ```python and ``` markers)
        in Assistant and Code messages.

        Returns:
            List of extracted Python code strings.
        """
        string = str(self.content)
        matches = re.findall(
            r"(?:```python)((?:\n(?!.*```python).*)+)(?:```)",
            string,
            flags=re.MULTILINE,
        )
        result = []
        for m in matches:
            result.append(m)
        return result


CodeContent = TypedDict("CodeContent", {"code": str})


class Code(BaseMessage):
    """A code message."""

    variant: Literal["Code"]

    @computed_field(repr=False) # type: ignore[prop-decorator]
    @property
    def code_cells(self) -> list[str]:
        try: 
            decoded_str = json.loads(self.content)
            if isinstance(decoded_str, dict):
                return [json.loads(self.content)["code"]]
            return []
        except json.JSONDecodeError:
            return []
        
    def repr_content(self):
        if self.code_cells:
            return "\n".join(self.code_cells)
        return self.content

    def repr_markdown(self):
        if self.code_cells:
            markdown_str = f"\n```python\n{"\n".join(self.code_cells)}\n```\n"
            return markdown_str
        return ""


class CodeOutput(BaseMessage):
    """A code output message."""

    variant: Literal["CodeOutput"]
    content: str

    def repr_markdown(self):
        markdown_str = ""
        for line in self.content.split("\n"):
            markdown_str += f"\n> {line}\n>"
        return markdown_str



class ServerError(BaseMessage):
    """A server error message."""

    variant: Literal["ServerError"]


class OpenAIError(BaseMessage):
    """An OpenAI error message."""

    variant: Literal["OpenAIError"]


class CodeError(BaseMessage):
    """A code error message."""

    variant: Literal["CodeError"]


class StreamEnd(BaseMessage):
    """A stream end message."""

    variant: Literal["StreamEnd"]


class ServerHint(BaseMessage):
    """A server hint message."""

    variant: Literal["ServerHint"]
    content: dict[str, str | int | float]

    @field_validator('content', mode='before')
    @classmethod
    def load_json_str(cls, value: Any) -> dict[str , Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            value = value.replace("'", "\"")
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(f"Value {value} cannot be parsed as a json object.")


class Image(BaseMessage):
    """An image message stored as base64-encoded string.

    Attributes:
        variant: Always "Image".
        content: Base64-encoded image data.
    """

    variant: Literal["Image"]
    content: str

    def repr_content(self) -> str:
        """Returns a truncated representation of the image content.

        Only shows the first 10 characters of the base64 encoded string.

        Returns:
            Truncated string representation of the content.
        """
        if len(self.content) < 10:
            return self.content
        content = f"{self.content[:10]}..."
        return content

    def repr_markdown(self) -> str:
        """Returns a markdown representation of the image.

        Returns:
            Markdown image tag with embedded base64 data.
        """
        markdown_str = f"\n![Image](data:image/png;base64,{self.content})\n"
        return markdown_str

    def save_to_file(self, output_path: Path | str):
        """Saves the image to a file.

        Args:
            output_path: Path where the image should be saved.

        Raises:
            ValueError: If the parent directory does not exist.
        """
        output_path = Path(output_path)
        if not (parent_dir := output_path.parent).exists():
            raise ValueError(
                f"The directory {parent_dir} does not exist. Please make sure you are saving the image to an existing directory."
            )
        base64_bytes = self.content.encode("utf-8")
        image_data = base64.decodebytes(base64_bytes)
        with output_path.open(mode="wb") as fw:
            fw.write(image_data)

    def __repr__(self):
        return f"{self.__class__.__name__}(variant={self.variant}, content={self.repr_content()})"


class MessageModel(BaseModel):
    """Model wrapping a single message with variant discrimination.

    Uses Pydantic's discriminator to distinguish between different message types
    based on the variant field.

    Attributes:
        message: A union of all possible message types.
    """

    message: Union[
        Prompt,
        User,
        Assistant,
        Code,
        CodeOutput,
        Image,
        ServerError,
        OpenAIError,
        CodeError,
        StreamEnd,
        ServerHint,
    ] = Field(discriminator="variant")

    @property
    def content(self) -> str:
        return self.message.content
    @content.setter
    def content(self, content: str) -> None:
        self.message.content = content
    
    @property
    def variant(self) -> str:
        return self.message.variant
    @variant.setter
    def variant(self, variant: str) -> None:
        self.message.variant = variant

    def repr_markdown(self) -> str:
        return self.message.repr_markdown()
    

class Conversation(BaseModel):
    """Model representing a conversation with multiple messages.

    This class handles raw message chunks and provides computed properties
    for accessing formatted messages, code cells, etc.

    Attributes:
        raw_messages: Sequence of MessageModel instances.
    """

    raw_messages: Sequence[MessageModel] = Field(repr=False)

    def _format_messages_for_chat(self) -> str:
        """Formats messages for chat display.

        Returns:
            Formatted string representation of all messages.
        """
        format_str = ""
        for i, mm in enumerate(self.messages):
            format_str += f"[{i}] {mm.message.variant}:\n{mm.message.repr_content()}\n\n"
        return format_str

    @computed_field # type: ignore[prop-decorator]
    @cached_property
    def messages(self) -> list[MessageModel]:
        """Appends message chunks to create complete messages.

        Combines message chunks that have the same variant into complete messages.

        Returns:
            List of complete MessageModel instances.
        """
        current_content = ""
        current_variant = ""
        result = []
        for m in self.raw_messages:
            if current_variant != m.message.variant or current_variant=="ServerHint":
                if current_variant and current_content:
                    result.append(
                        MessageModel(
                            message={"variant": current_variant, "content": current_content}  # type: ignore[arg-type]
                        )
                    )
                    current_content = ""
                current_variant = m.message.variant
            current_content += str(m.message.content)
        result.append(
            MessageModel(
                message={"variant": current_variant, "content": current_content}  # type: ignore[arg-type]
            )
        )
        return result

    @computed_field(repr=False) # type: ignore[prop-decorator]
    @cached_property
    def code_cells(self) -> list[str]:
        """Extracts python code cells from the conversation.

        Returns:
            List of extracted Python code strings.
        """
        result = []
        for mm in self.messages:
            result += mm.message.code_cells
        return result
    
    def repr_markdown(self) -> str:
        markdown_string = ""
        for mm in self.messages:
            markdown_string += mm.message.repr_markdown() + "\n"
        return markdown_string

    def __str__(self) -> str:
        """Returns a string representation of the conversation.

        Returns:
            Formatted chat string of all messages.
        """
        return self._format_messages_for_chat()
    
    def __getitem__(self, indexes: int | tuple[int, int, int]):
        return self.messages[indexes]
    
    def __len__(self) -> int:
        return len(self.messages)
    

class StreamConversation(ContextDecorator):
    """Accumulates streaming message chunks and yields markdown-ready content.

    This class handles the type-specific logic for rendering streamed messages
    as markdown. It buffers content for message types that require complete data
    (like Images) and processes content for types that need transformation
    (like Code messages with JSON prefixes).

    Attributes:
        _current_variant: The variant of the message currently being accumulated.
        _current_buffer: The accumulated content for the current message.
    """

    def __init__(self, stream: StreamResponse):
        """Initializes the class with empty state."""
        self.stream_response : StreamResponse = stream
        self.conversation: Conversation | None = None
        self._current_message: MessageModel | None = None

    def __enter__(self) -> Self:
        return self
    
    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.stream_response.close()
        return False

    def translate_to_conversation(self) -> Conversation:
        if self.conversation:
            return self.conversation
        raw_messages =  [MessageModel(message=msg_dict) for msg_dict in self.stream_response.iter_json_objects()]
        self.conversation = Conversation(raw_messages=raw_messages)
        return self.conversation

    def process_chunk(self, message_chunk: MessageModel) -> list[str]:
        """Process a streamed message chunk and return markdown-ready strings.

        Args:
            message_model: A MessageModel from the stream.

        Returns:
            List of markdown strings ready to be rendered.
            Empty list if nothing is ready yet.
        """
        variant = message_chunk.variant
        content = str(message_chunk.content)

        output: list[str] = []

        # If first message chunk, set current message to message_chunk
        if not self._current_message:
            self._current_message = MessageModel(**message_chunk.model_dump())
        # If variant changed, flush previous buffer
        elif variant != self._current_message.variant:
            output.extend(self._flush_previous())
            self._current_message = MessageModel(**message_chunk.model_dump())
        else:
            # Accumulate content
            self._current_message.content += content

        # Type-specific handling for current variant
        if variant == "Image":
            # Buffer until complete (detected by variant change)
            # Don't yield anything yet
            pass
        elif variant == "CodeOutput":
            # Code Output is returned in one chunk, so it can be skipped in the incremental returns
            pass
        elif variant == "Code":
            output.extend(self._process_code_chunk(content))
        else:
            # Text messages: yield the new chunk immediately
            output.append(content)
        return output

    def _flush_previous(self) -> list[str]:
        """Flush buffered content when variant changes.

        Returns:
            List of markdown strings for the completed previous message.
        """
        output: list[str] = []
        if  self._current_message.variant in ["Image", "CodeOutput"] and self._current_message.content:
            output.append(self._current_message.repr_markdown() + "\n")
        return output

    def _process_code_chunk(self, code_chunk: str) -> list[str]:
        """Process Code message content, stripping prefix when detected.

        Handles case where prefix might be split across chunks by searching
        for the complete prefix string.

        Returns:
            List of markdown strings (code content with prefix stripped).
        """
        output: list[str] = []

        content = self._current_message.content
        code_content = ""
        prefix = '{"code":"'
        prefix_idx = content.find(prefix)
        # Check if we have the complete prefix
        if prefix_idx >= 0:
            # Extract everything after the prefix
            valid_content = content[prefix_idx + len(prefix) :]
            if not valid_content:
                code_content = "\n\n```python\n"
            elif code_chunk == "\\n":
                code_content = "\n"
            elif "\\n" in valid_content[-len(code_chunk)-1:]:
                code_content = valid_content[-len(code_chunk)-1:].replace("\\n", "\n")
            elif code_chunk[-1] == "\\":
                code_content = code_chunk[:-1]
            elif code_chunk == '"}':
                code_content = "\n```\n\n"
            else:
                code_content = code_chunk
            if code_content:
                output.append(code_content)
        return output
    
    def iter_for_markdown(self):
        raw_messages = []
        for msg_dict in self.stream_response.iter_json_objects():
            msg_model = MessageModel(message=msg_dict)
            raw_messages.append(msg_model)
            if msg_model.variant not in ["ServerHint", "StreamEnd"]:
                for markdown_chunk in self.process_chunk(msg_model):
                    yield markdown_chunk
        # save completed response as a conversation instance
        self.conversation = Conversation(raw_messages=raw_messages)

    def iter_raw(self):
        for msg_dict in self.stream_response.iter_json_objects():
            yield msg_dict



