import base64
import json
import re
import sys
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from functools import cached_property
from pathlib import Path
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypedDict,
    Union,
)

import PIL.Image
from pydantic import BaseModel, Field, computed_field, field_validator

from ._streaming import StreamResponse

if sys.version_info.minor < 11:  # pragma: no cover
    from typing_extensions import Self
else:
    from typing import Self


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
        """Returns a markdown representation of the message.

        Returns:
            Markdown string representation of the message.
        """
        return str(self.content)

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @cached_property
    def code_cells(self) -> List[str]:
        """Representation of code cells included in a given message.

        By default returns an empty list.

        Returns:
            List of code cell strings.
        """
        return []

    def __repr__(self):
        """Returns a string representation of the message.

        Returns:
            String representation with variant, truncated content, and id.
        """
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

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def code_cells(self) -> List[str]:
        """Extracts python code cells from the assistant message.

        Finds all Python code blocks (between ```python and ``` markers)
        in Assistant messages.

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


class Code(BaseMessage):
    """A code message containing Python code."""

    variant: Literal["Code"]
    content: str

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def code_cells(self) -> List[str]:
        """Extracts code cells from the JSON content.

        Returns:
            List containing the code string from the JSON content,
            or empty list if parsing fails.
        """
        try:
            decoded_str = json.loads(self.content)
            if isinstance(decoded_str, dict):
                return [decoded_str.get("code", "")] if "code" in decoded_str else []
            return []
        except json.JSONDecodeError:
            return []

    def repr_content(self):
        """Returns a string representation of the code content.

        Returns:
            Joined code cells or raw content if no code cells available.
        """
        if self.code_cells:
            return "\n".join(self.code_cells)
        return self.content

    def repr_markdown(self):
        """Returns a markdown representation of the code message.

        Returns:
            Markdown string with code in a Python code block.
        """
        if self.code_cells:
            markdown_str = "\n```python\n" + "\n".join(self.code_cells) + "\n```\n"
            return markdown_str
        return ""


class CodeOutput(BaseMessage):
    """A code output message."""

    class CodeOutputContent(TypedDict):
        stdout: str
        stderr: str
        result_repr: str
        display_data: List[Dict[str, Any]]
        error: str
        created_files: List[Dict[str, Any]]

    variant: Literal["CodeOutput"]
    content: Union[str, CodeOutputContent]

    def repr_markdown(self):
        """Returns a markdown representation of the code output.

        Formats output (result representation, stdout, error) as a python code cell,
        links any output files and renders output images.

        Returns:
            Markdown string with output in blockquotes.
        """
        markdown_str = ""
        if isinstance(self.content, str):
            text_content = self.content
            created_files = ""
        else:
            text_content = (
                self.content["result_repr"] or self.content["stdout"] or self.content["error"]
            )
            created_files = self.content["created_files"]
        if text_content:
            markdown_str += "---\n```python"
            for line in text_content.split("\n"):
                markdown_str += f"\n{line}"
            markdown_str += "\n```\n---"
        if created_files:
            created_files.sort(key=lambda x: x["mime_type"], reverse=True)
            for file_dict in created_files:
                preview_url = file_dict["preview_url"]
                mime_type = file_dict["mime_type"]
                path = file_dict["path"]
                markdown_str += (
                    f"\n![{path}]({preview_url})\n"
                    if "image" in mime_type
                    else f"\nOutput file: [{path}]({preview_url})\n"
                )
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

    def repr_markdown(self):
        return ""


class ServerHint(BaseMessage):
    """A server hint message containing structured hint data."""

    variant: Literal["ServerHint"]
    content: Dict[str, str | int | float | Dict[str, Any]]

    @field_validator("content", mode="before")
    @classmethod
    def load_json_str(cls, value: Any) -> dict[str, Any]:
        """Validates and parses content as a JSON object.

        Args:
            value: The value to validate and parse.

        Returns:
            Parsed dictionary from the JSON string.

        Raises:
            ValueError: If the value cannot be parsed as JSON.
        """
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            value = value.replace("'", '"')
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(f"Value {value} cannot be parsed as a json object.")

    def repr_markdown(self):
        return ""


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
            Markdown image tag with embedded base64 data, wrapped in newlines.
        """
        markdown_str = f"\n![Image](data:image/png;base64,{self.content})\n"
        return markdown_str

    def to_pil_image(self) -> PIL.Image.Image:
        """Translate base64-encoded image data to a Pillow Image.

        Returns:
            PIL.Image.Image: The Image object, lazily loaded.
        """
        import io

        base64_bytes = self.content.encode("utf-8")
        image_data = base64.decodebytes(base64_bytes)
        image = PIL.Image.open(io.BytesIO(image_data))
        return image

    def save_to_file(self, output_path: Path | str):
        """Saves the image to a file.

        Args:
            output_path: Path where the (PNG) image should be saved.

        Raises:
            ValueError: If the parent directory does not exist.
        """
        output_path = Path(output_path)
        if not (parent_dir := output_path.parent).exists():
            raise ValueError(
                f"The directory {parent_dir} does not exist. Please make sure you are saving the image to an existing directory."
            )
        image = self.to_pil_image()
        image.save(output_path)

    def __repr__(self):
        """Returns a string representation of the image message.

        Returns:
            String representation with variant and truncated content.
        """
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
    def content(self) -> Union[str, Sequence[str], Mapping[str, Any]]:
        """Gets the content of the underlying message.

        Returns:
            The content string from the message.
        """
        return self.message.content

    @content.setter
    def content(self, content: str) -> None:
        """Sets the content of the underlying message.

        Args:
            content: The content string to set.
        """
        self.message.content = content

    @property
    def variant(self) -> str:
        """Gets the variant of the underlying message.

        Returns:
            The variant string from the message.
        """
        return self.message.variant

    @variant.setter
    def variant(self, variant) -> None:
        """Sets the variant of the underlying message.

        Args:
            variant: The variant string to set.
        """
        self.message.variant = variant

    @property
    def code_cells(self) -> List[str]:
        """Gets the code_cells of the underlying message (valid for Assistant or Code type messages)

        Returns
            A list of individual code cells contained in a given message.
        """
        return self.message.code_cells

    def repr_markdown(self) -> str:
        """Returns a markdown representation of the message.

        Delegates to the underlying message's repr_markdown method.

        Returns:
            Markdown string representation.
        """
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

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def messages(self) -> List[MessageModel]:
        """Appends message chunks to create complete messages.

        Combines message chunks that have the same variant into complete messages.
        ServerHint messages are treated as separate messages even if variant matches.

        Returns:
            List of complete MessageModel instances.
        """
        current_content = ""
        current_variant = ""
        result = []
        for m in self.raw_messages:
            if current_variant != m.message.variant or current_variant == "ServerHint":
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

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @cached_property
    def images(self) -> List[Image]:
        """Extract Image objects from conversation.

        Returns:
            List of extracted Image objects.
        """
        result = []
        for message in self.messages:
            if isinstance(message.message, Image):
                result.append(message.message)
        return result

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @cached_property
    def code_cells(self) -> List[str]:
        """Extracts python code cells from the conversation.

        Returns:
            List of extracted Python code strings.
        """
        result = []
        for mm in self.messages:
            result += mm.code_cells
        return result

    def repr_markdown(self) -> str:
        """Returns a markdown representation of the conversation.

        Concatenates markdown representations of all messages.

        Returns:
            Markdown string of the entire conversation.
        """
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

    def __getitem__(self, index):
        """Indexes into the messages list.

        Args:
            indexes: Index or slice to retrieve messages.

        Returns:
            MessageModel or list of MessageModel instances.
        """
        return self.messages.__getitem__(index)

    def __len__(self) -> int:
        """Returns the number of messages in the conversation.

        Returns:
            Number of messages.
        """
        return len(self.messages)


class StreamConversation(AbstractContextManager, AbstractAsyncContextManager):
    """Accumulates streaming message chunks and yields markdown-ready content.

    This class handles the type-specific logic for rendering streamed messages
    as markdown. It buffers content for message types that require complete data
    (like Images) and processes content for types that need transformation
    (like Code messages with JSON prefixes).

    Can be used as a context manager (with) or async context manager (async with)
    to automatically close the underlying stream response, or as a regular object
    for manual control.

    Supports both synchronous and asynchronous iteration:
    - Use iter_for_markdown(), iter_raw() for synchronous streaming
    - Use aiter_for_markdown(), aiter_raw() for asynchronous streaming

    Attributes:
        stream_response: The underlying StreamResponse object.
        conversation: Cached Conversation instance after stream completes.
        _current_message: The current MessageModel being accumulated.
        _buffered_content: Any message content that needs to be buffered for delayed processing.
        _code_started: Flag indicating if a code message has been started in the stream.
        _on_exit_callback: Callable that is called on exit of the context.
    """

    def __init__(self, stream: StreamResponse, on_exit_callback: Callable | None = None):
        """Initializes the class with a StreamResponse.

        Args:
            stream: The StreamResponse to process.
            on_exit_callback: Optional callable that is invoked upon exiting the context.
        """
        self.stream_response: StreamResponse = stream
        self.conversation: Conversation | None = None
        self._current_message: MessageModel | None = None
        self._buffered_content: str = ""
        self._code_started: bool = False
        self._on_exit_callback: Callable | None = on_exit_callback

    def __enter__(self) -> Self:
        """Enters the context manager.

        Returns:
            Self for use in with statements.
        """
        return self

    def __exit__(self, *exc_details) -> None:
        """Exits the context manager, closing the stream response.

        Args:
            exc_details: Arguments describing exception, if raised.
        """
        self.stream_response.close()
        if self._on_exit_callback:
            self._on_exit_callback()

    async def __aenter__(self) -> Self:
        """Enters the async context manager.

        Returns:
            Self for use in async with statements.
        """
        return self

    async def __aexit__(self, *exc_details) -> None:
        """Exits the async context manager, closing the stream response.

        Args:
            exc_details: Arguments describing exception, if raised.
        """
        await self.stream_response.aclose()
        if self._on_exit_callback:
            callback_result = self._on_exit_callback()
            await callback_result

    def translate_to_conversation(self) -> Conversation:
        """Converts the streamed messages to a Conversation instance.

        If already converted, returns the cached Conversation.
        Otherwise, processes all remaining messages from the stream.

        Returns:
            Conversation instance containing all streamed messages.
        """
        if self.conversation:
            return self.conversation
        raw_messages = [MessageModel(message=msg_dict) for msg_dict in self.stream_response.iter_json_objects()]  # type: ignore[arg-type]
        self.conversation = Conversation(raw_messages=raw_messages)
        return self.conversation

    def process_chunk(self, message_chunk: MessageModel) -> Tuple[List[str], List[str]]:
        """Process a streamed message chunk and return th markdown-ready strings, as well as variants contained in the message chunk.
        Args:
            message_chunk: A MessageModel from the stream.

        Returns:
            A tuple consisting of:
               - List of markdown strings ready to be rendered. Empty list if nothing is ready yet.
               - List of variants corresponding to the different markdown strings.
        """
        variant = message_chunk.variant
        content = str(message_chunk.content)

        output: List[str] = []
        variants: List[str] = []

        # If first message chunk, set current message to message_chunk
        if not self._current_message:
            self._current_message = MessageModel(**message_chunk.model_dump())
        # If variant changed, flush previous buffer
        elif variant != self._current_message.variant:
            previous_variant, new_output = self._flush_previous()
            output.extend(new_output)
            variants.extend(previous_variant)
            self._current_message = MessageModel(**message_chunk.model_dump())
        else:
            if isinstance(self._current_message.content, str):
                # Accumulate content if it is current message is of type string
                self._current_message.content += content
            else:
                # Otherwise, content is set to content of new chunk
                self._current_message.content = message_chunk.content  # type: ignore[assignment]

        # Type-specific handling for current variant
        if variant == "Image":
            # Buffer until complete (detected by variant change)
            # Don't yield anything yet
            pass
        elif variant == "CodeOutput":
            # Code Output is returned in one chunk, so it can be skipped in the incremental returns
            pass
        elif variant == "Code":
            output.extend(self._process_code_chunk_for_md(content))
            variants.append(variant)
        else:
            # Text messages: yield the new chunk immediately
            md_string = message_chunk.repr_markdown()
            if md_string:
                output.append(md_string)
                variants.append(variant)
        return variants, output

    def _flush_previous(self) -> Tuple[List[str], List[str]]:
        """Flush buffered content when variant changes.

        Returns:
            A tuple consisting of:
                - List of markdown strings for the completed previous message.
                - List of variants corresponding the the completed markdown strings.
        """
        output: List[str] = []
        variants: List[str] = []
        self._buffered_content = ""
        if (
            self._current_message
            and self._current_message.variant in ["Image", "CodeOutput"]
            and self._current_message.content
        ):
            output.append(self._current_message.repr_markdown() + "\n")
            variants.append(self._current_message.variant)
        return variants, output

    @staticmethod
    def _parse_escaped_chars(string: str) -> str:
        """Parse string to replace various characters typically escaped in a json-like string."""
        esc_char_dict = {
            "\\n": "\n",
            "\\t": "\t",
            "\\r": "\r",
            "\\\\": "\\",
            '\\"': '"',
            "\\'": "'",
        }
        for esc_char, non_esc in esc_char_dict.items():
            string = string.replace(esc_char, non_esc)
        return string

    def _process_code_chunk_for_md(self, code_chunk: str) -> List[str]:
        """Process Code message content, stripping prefix when detected.

        Handles case where prefix might be split across chunks by searching
        for the complete prefix string.

        Args:
            code_chunk: The new code content chunk.

        Returns:
            List of markdown strings (code content with prefix stripped).
        """
        output: List[str] = []

        content = str(self._current_message.content) if self._current_message else ""
        code_content = ""
        self._buffered_content += code_chunk
        prefix = '{"code":"'
        suffix = '"}'
        prefix_idx = content.find(prefix)
        # Check if we have the complete prefix
        if prefix_idx >= 0:
            # if prefix is found, but code not started yet, set flag to true and add markdown python code-wrapper prefix
            if not self._code_started:
                self._code_started = True
                code_content = "\n\n```python\n"
            # if buffered content ends with suffix, indicates end of code
            if self._buffered_content.endswith(suffix):
                code_content += (
                    self._buffered_content.removeprefix(prefix).removesuffix(suffix) + "\n```\n\n"
                )
                self._code_started = False  # reset code-started flag
            # parse buffered content if it does not end with a (potentially) incomplete escape sequence
            elif self._buffered_content[-1] != "\\":
                code_content += (
                    self._parse_escaped_chars(self._buffered_content)
                    .removeprefix(prefix)
                    .removesuffix(suffix)
                )
                # reset buffered content
                self._buffered_content = ""
            if code_content:
                output.append(code_content)
        return output

    def iter_for_markdown(self) -> Generator[Tuple[str, str], None, None]:
        """Iterates over the stream, yielding markdown-ready strings.

        Processes each message chunk and yields markdown content as it
        becomes available.

        Yields:
            Tuple containing:
                - Variant of processed markdown chunk.
                - Markdown strings ready for rendering.
        """
        raw_messages = []
        for msg_dict in self.stream_response.iter_json_objects():
            msg_model = MessageModel(message=msg_dict)
            raw_messages.append(msg_model)
            variants, processed_chunks = self.process_chunk(msg_model)
            for variant, markdown_chunk in zip(variants, processed_chunks):
                yield variant, markdown_chunk
        # save completed response as a conversation instance
        self.conversation = Conversation(raw_messages=raw_messages)

    def iter_raw(self):
        """Iterates over raw message dictionaries from the stream.

        Yields:
            Raw message dictionaries as they arrive from the stream.
        """
        raw_messages = []
        for msg_dict in self.stream_response.iter_json_objects():
            yield msg_dict
            raw_messages.append(MessageModel(message=msg_dict))
        # save completed response as a conversation instance
        self.conversation = Conversation(raw_messages=raw_messages)

    async def aiter_for_markdown(self) -> AsyncGenerator[Tuple[str, str], None]:
        """Asynchronously iterates over the stream, yielding markdown-ready strings.

        Processes each message chunk and yields markdown content as it
        becomes available.

        Yields:
            Tuple containing:
                - Variant of processed markdown chunk.
                - Markdown strings ready for rendering.
        """
        raw_messages = []
        async for msg_dict in self.stream_response.aiter_json_objects():
            msg_model = MessageModel(message=msg_dict)
            raw_messages.append(msg_model)
            variants, processed_chunks = self.process_chunk(msg_model)
            for variant, markdown_chunk in zip(variants, processed_chunks):
                yield variant, markdown_chunk
        # save completed response as a conversation instance
        self.conversation = Conversation(raw_messages=raw_messages)

    async def aiter_raw(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Asynchronously iterates over raw message dictionaries from the stream.

        Yields:
            Raw message dictionaries as they arrive from the stream.
        """
        raw_messages = []
        async for msg_dict in self.stream_response.aiter_json_objects():
            yield msg_dict
            raw_messages.append(MessageModel(message=msg_dict))
        # save completed response as a conversation instance
        self.conversation = Conversation(raw_messages=raw_messages)
