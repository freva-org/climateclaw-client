import base64
import re
from functools import cached_property
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Sequence, Union

from pydantic import BaseModel, Field, computed_field


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


class Prompt(BaseMessage):
    """A prompt message."""

    variant: Literal["Prompt"]


class User(BaseMessage):
    """A user message."""

    variant: Literal["User"]


class Assistant(BaseMessage):
    """An assistant message."""

    variant: Literal["Assistant"]


class Code(BaseMessage):
    """A code message."""

    variant: Literal["Code"]


class CodeOutput(BaseMessage):
    """A code output message."""

    variant: Literal["CodeOutput"]


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
        content = f"{self.content[:10]}..."
        return content

    def markdown_repr(self) -> str:
        """Returns a markdown representation of the image.

        Returns:
            Markdown image tag with embedded base64 data.
        """
        markdown_str = f"![Image](data:image/png;base64,{self.content})"
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
            format_str += f"[{i}] {mm.message.variant}: {mm.message.repr_content()}\n"
        return format_str

    @cached_property
    @computed_field
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
            if current_variant != m.message.variant:
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

    @cached_property
    @computed_field(repr=False)
    def code_cells(self) -> list[str]:
        """Extracts python code cells from the conversation.

        Finds all Python code blocks (between ```python and ``` markers)
        in Assistant and Code messages.

        Returns:
            List of extracted Python code strings.
        """
        result = []
        for mm in self.messages:
            if mm.message.variant in ["Assistant", "Code"]:
                string = str(mm.message.content)
                matches = re.findall(
                    r"(?:```python)((?:\n(?!.*```python).*)+)(?:```)",
                    string,
                    flags=re.MULTILINE,
                )
                for m in matches:
                    result.append(m)
        return result

    def __str__(self) -> str:
        """Returns a string representation of the conversation.

        Returns:
            Formatted chat string of all messages.
        """
        return self._format_messages_for_chat()
