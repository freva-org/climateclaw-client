"""Unit tests for message models in freva-gpt-client."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from freva_gpt_client.models import (
    Assistant,
    BaseMessage,
    Code,
    CodeError,
    CodeOutput,
    Conversation,
    Image,
    MessageModel,
    OpenAIError,
    Prompt,
    ServerError,
    ServerHint,
    StreamConversation,
    StreamEnd,
    User,
)

# =============================================================================
# BaseMessage Tests
# =============================================================================


class TestBaseMessage:
    """Tests for BaseMessage class."""

    @pytest.mark.parametrize(
        "input_arg, expected_output",
        [
            ("Hello", "Hello"),
            (["a", "b", "c"], "['a', 'b', 'c']"),
            ({"key": "value", "num": 42}, "{'key': 'value', 'num': 42}"),
            ("", ""),
        ],
    )
    def test_repr_content(self, input_arg, expected_output):
        """Test repr_content with string content."""
        msg = BaseMessage(variant="Assistant", content=input_arg)
        assert msg.repr_content() == expected_output

    def test_repr_markdown(self):
        """Test repr_markdown returns string content."""
        msg = BaseMessage(variant="Assistant", content="Hello")
        assert msg.repr_markdown() == "Hello"

    def test_repr_markdown_list(self):
        """Test repr_markdown with list content."""
        msg = BaseMessage(variant="Assistant", content=["line1", "line2"])
        assert msg.repr_markdown() == "['line1', 'line2']"

    def test_code_cells_default(self):
        """Test default code_cells returns empty list."""
        msg = BaseMessage(variant="Assistant", content="Hello")
        assert msg.code_cells == []

    def test_repr_long_content(self):
        """Test __repr__ truncates long content."""
        msg = BaseMessage(variant="Assistant", content="01234567890123456789")
        repr_str = repr(msg)
        assert "0123456789..." in repr_str
        assert "variant=Assistant" in repr_str
        assert "BaseMessage" in repr_str

    def test_repr_short_content(self):
        """Test __repr__ shows full short content."""
        msg = BaseMessage(variant="Assistant", content="Hi")
        repr_str = repr(msg)
        assert "content=Hi" in repr_str
        assert "variant=Assistant" in repr_str

    def test_repr_with_id(self):
        """Test __repr__ includes id when present."""
        msg = BaseMessage(variant="Assistant", content="test", id="msg-123")
        repr_str = repr(msg)
        assert "id=msg-123" in repr_str

    def test_repr_without_id(self):
        """Test __repr__ handles None id."""
        msg = BaseMessage(variant="Assistant", content="test")
        repr_str = repr(msg)
        assert "id=None" in repr_str


# =============================================================================
# Simple Variant Tests (Prompt, User, ServerError, OpenAIError, CodeError, StreamEnd)
# =============================================================================


class TestSimpleVariants:
    """Tests for simple message variants."""

    @pytest.mark.parametrize(
        "variant_class, variant_str",
        [
            (Prompt, "Prompt"),
            (User, "User"),
            (ServerError, "ServerError"),
            (OpenAIError, "OpenAIError"),
            (CodeError, "CodeError"),
            (StreamEnd, "StreamEnd"),
        ],
    )
    def test_variant_instantiation(self, variant_class, variant_str):
        """Test instantiation with valid variant."""
        msg = variant_class(variant=variant_str, content="test")
        assert msg.variant == variant_str
        assert msg.content == "test"

    def test_inherited_repr_content(self):
        """Test inherited repr_content works for simple variants."""
        msg = User(variant="User", content="question")
        assert msg.repr_content() == "question"

    def test_inherited_repr_markdown(self):
        """Test inherited repr_markdown works for simple variants."""
        msg = Prompt(variant="Prompt", content="prompt text")
        assert msg.repr_markdown() == "prompt text"

    def test_stream_end_repr_markdown(self):
        """Test StreamEnd has empty repr_markdown."""
        msg = StreamEnd(variant="StreamEnd", content="Stream Ended.")
        assert msg.repr_markdown() == ""


# =============================================================================
# Assistant Message Tests
# =============================================================================


class TestAssistantMessage:
    """Tests for Assistant message variant."""

    def test_assistant_instantiation(self):
        """Test instantiation with valid variant."""
        msg = Assistant(variant="Assistant", content="test")
        assert msg.variant == "Assistant"
        assert msg.content == "test"

    def test_valid_content_single_cell(self):
        """Test code_cells with a valid code cell."""
        msg = Assistant(
            variant="Assistant",
            content="Code is as follows\n```python\nimport xarray as xr\n```\nCode is complete!",
        )
        assert len(msg.code_cells) == 1
        assert "\nimport xarray as xr\n" == msg.code_cells[0]

    def test_valid_content_multiple_cells(self):
        """Test code_cells with 2 valid code cells with non-code text before and after."""
        msg = Assistant(
            variant="Assistant",
            content="Code is as follows\n```python\nimport xarray as xr\n```\nSome more code\n```python\nimport matplotlib.pyplot as plt\n```\nCode is complete!",
        )
        assert len(msg.code_cells) == 2
        assert "\nimport xarray as xr\n" == msg.code_cells[0]
        assert "\nimport matplotlib.pyplot as plt\n" == msg.code_cells[1]


# =============================================================================
# Code Message Tests
# =============================================================================


class TestCodeMessage:
    """Tests for Code message variant."""

    def test_valid_json_content(self, sample_code_content):
        """Test code_cells with valid JSON content."""
        msg = Code(variant="Code", content=sample_code_content)
        assert len(msg.code_cells) == 1
        assert "import xarray" in msg.code_cells[0]
        assert 'print("hello!")' in msg.code_cells[0]

    def test_code_cells_empty_code(self, sample_code_content_empty):
        """Test code_cells with empty code string."""
        msg = Code(variant="Code", content=sample_code_content_empty)
        assert msg.code_cells == [""]

    def test_code_cells_invalid_json(self):
        """Test code_cells with invalid JSON returns empty list."""
        msg = Code(variant="Code", content="not valid json")
        assert msg.code_cells == []

    def test_code_cells_non_dict_json(self):
        """Test code_cells with non-dict JSON returns empty list."""
        msg = Code(variant="Code", content='["not", "a", "dict"]')
        assert msg.code_cells == []

    def test_code_cells_non_object_json(self):
        """Test code_cells with JSON string returns empty list."""
        msg = Code(variant="Code", content='"just a string"')
        assert msg.code_cells == []

    def test_code_cells_code_key_missing(self):
        """Test code_cells with JSON string that does not include the key 'code'"""
        msg = Code(variant="Code", content='{"not_code": "hello"}')
        assert msg.code_cells == []

    def test_repr_content_valid(self, sample_code_content):
        """Test repr_content with valid JSON."""
        msg = Code(variant="Code", content=sample_code_content)
        # repr_content returns joined code_cells
        assert "import xarray" in msg.repr_content()

    def test_repr_content_invalid(self):
        """Test repr_content with invalid JSON returns raw content."""
        msg = Code(variant="Code", content="raw content")
        assert msg.repr_content() == "raw content"

    def test_repr_markdown_valid(self):
        """Test repr_markdown with valid code."""
        code_json = '{"code": "x = 1"}'
        msg = Code(variant="Code", content=code_json)
        expected = "\n```python\nx = 1\n```\n"
        assert msg.repr_markdown() == expected

    def test_repr_markdown_invalid(self):
        """Test repr_markdown with invalid JSON returns empty string."""
        msg = Code(variant="Code", content="raw content")
        assert msg.repr_markdown() == ""

    def test_code_content_type(self):
        """Test that Code.content must be a string."""
        msg = Code(variant="Code", content="valid string")
        assert isinstance(msg.content, str)


# =============================================================================
# CodeOutput Message Tests
# =============================================================================


class TestCodeOutputMessage:
    """Tests for CodeOutput message variant."""

    def test_repr_markdown_single_line(self):
        """Test repr_markdown with single line."""
        msg = CodeOutput(variant="CodeOutput", content="output line")
        assert msg.repr_markdown() == "\n> output line"

    def test_repr_markdown_multiple_lines(self):
        """Test repr_markdown with multiple lines."""
        msg = CodeOutput(variant="CodeOutput", content="line1\nline2\nline3")
        expected = "\n> line1\n> line2\n> line3"
        assert msg.repr_markdown() == expected

    def test_repr_markdown_empty(self):
        """Test repr_markdown with empty content."""
        msg = CodeOutput(variant="CodeOutput", content="")
        assert msg.repr_markdown() == ""

    def test_repr_markdown_with_special_chars(self):
        """Test repr_markdown with special characters."""
        msg = CodeOutput(variant="CodeOutput", content="Error: 404 Not Found!")
        assert msg.repr_markdown() == "\n> Error: 404 Not Found!"

    def test_repr_markdown_preserves_whitespace(self):
        """Test repr_markdown preserves leading/trailing whitespace in lines."""
        msg = CodeOutput(variant="CodeOutput", content="  indented  \n  also  ")
        expected = "\n>   indented  \n>   also  "
        assert msg.repr_markdown() == expected


# =============================================================================
# ServerHint Message Tests
# =============================================================================


class TestServerHintMessage:
    """Tests for ServerHint message variant."""

    def test_dict_content(self):
        """Test ServerHint accepts dict content."""
        content = {
            "variant": "ServerHint",
            "content": {
                "memory": 12039000064,
                "total_memory": 538932101120,
                "cpu_usage": 0.0,
                "cpu_last_minute": 0.0,
                "process_cpu": 0.1,
                "process_memory": 94654464,
            },
        }
        msg = ServerHint(variant="ServerHint", content=content)
        assert msg.content == {
            "variant": "ServerHint",
            "content": {
                "memory": 12039000064,
                "total_memory": 538932101120,
                "cpu_usage": 0.0,
                "cpu_last_minute": 0.0,
                "process_cpu": 0.1,
                "process_memory": 94654464,
            },
        }
        assert isinstance(msg.content, dict)

    def test_json_string_content(self):
        """Test ServerHint parses JSON string content."""
        msg = ServerHint(variant="ServerHint", content='{"thread_id": "123"}')
        assert msg.content == {"thread_id": "123"}
        assert isinstance(msg.content, dict)

    def test_single_quoted_json(self):
        """Test ServerHint handles single-quoted JSON strings."""
        msg = ServerHint(
            variant="ServerHint",
            content="{'variant': 'ServerHint', 'content': {'memory': 12039000064, 'total_memory': 538932101120, 'cpu_usage': 0.0, 'cpu_last_minute': 0.0, 'process_cpu': 0.1, 'process_memory': 94654464}}",
        )
        assert msg.content == {
            "variant": "ServerHint",
            "content": {
                "memory": 12039000064,
                "total_memory": 538932101120,
                "cpu_usage": 0.0,
                "cpu_last_minute": 0.0,
                "process_cpu": 0.1,
                "process_memory": 94654464,
            },
        }

    def test_invalid_json_raises(self):
        """Test ServerHint raises ValueError for invalid JSON."""
        with pytest.raises(ValueError, match="cannot be parsed"):
            ServerHint(variant="ServerHint", content="not valid json")

    def test_repr_markdown_empty(self):
        """Test ServerHint repr_markdown returns empty string."""
        msg = ServerHint(variant="ServerHint", content={"thread_id": "123"})
        assert msg.repr_markdown() == ""

    def test_nested_json_content(self):
        """Test ServerHint with flat JSON content."""
        content = '{"data": "value", "num": 42}'
        msg = ServerHint(variant="ServerHint", content=content)
        assert msg.content == {"data": "value", "num": 42}


# =============================================================================
# Image Message Tests
# =============================================================================


class TestImageMessage:
    """Tests for Image message variant."""

    def test_repr_content_long(self, sample_base64_long):
        """Test repr_content truncates long base64 strings."""
        msg = Image(variant="Image", content=sample_base64_long)
        repr_content = msg.repr_content()
        assert len(repr_content) < len(sample_base64_long)
        assert "..." in repr_content

    def test_repr_content_short(self):
        """Test repr_content shows full short string."""
        msg = Image(variant="Image", content="short")
        assert msg.repr_content() == "short"

    def test_repr_content_exactly_10_chars(self):
        """Test repr_content with exactly 10 characters."""
        msg = Image(variant="Image", content="0123456789")
        # Exactly 10 chars is NOT truncated (< 10 would be, but >= 10 is truncated)
        # Actually len < 10 returns self.content, so 10 >= 10 means truncation
        assert msg.repr_content() == "0123456789..."

    def test_repr_content_11_chars(self):
        """Test repr_content truncates at 10+ characters."""
        msg = Image(variant="Image", content="01234567890")
        assert "..." in msg.repr_content()
        assert msg.repr_content() == "0123456789..."

    def test_repr_markdown(self, sample_base64):
        """Test repr_markdown returns valid markdown image tag."""
        msg = Image(variant="Image", content=sample_base64)
        markdown = msg.repr_markdown()
        assert f"![Image](data:image/png;base64,{sample_base64})" in markdown
        assert markdown.startswith("\n")
        assert markdown.endswith("\n")

    def test_save_to_file_success(self, tmp_path, sample_base64):
        """Test save_to_file saves valid base64 to file."""
        msg = Image(variant="Image", content=sample_base64)
        output_path = tmp_path / "test.png"
        msg.save_to_file(output_path)
        assert output_path.exists()
        with output_path.open("rb") as f:
            saved_data = f.read()
        assert (
            saved_data
            == b"iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="
        )

    def test_save_to_file_nonexistent_dir(self, sample_base64):
        """Test save_to_file raises ValueError for non-existent directory."""
        msg = Image(variant="Image", content=sample_base64)
        output_path = Path("/nonexistent/dir/test.png")
        with pytest.raises(
            ValueError,
            match="The directory .* does not exist. Please make sure you are saving the image to an existing directory.",
        ):
            msg.save_to_file(output_path)

    def test_repr(self, sample_base64):
        """Test __repr__ includes variant and truncated content."""
        msg = Image(variant="Image", content=sample_base64)
        repr_str = repr(msg)
        assert "variant=Image" in repr_str
        assert "..." in repr_str


# =============================================================================
# MessageModel Tests
# =============================================================================


class TestMessageModel:
    """Tests for MessageModel wrapper class."""

    @pytest.mark.parametrize(
        "variant, content, expected_class, expected_content",
        [
            ("Assistant", "hello", Assistant, "hello"),
            ("User", "question", User, "question"),
            ("Code", '{"code": "x=1"}', Code, '{"code": "x=1"}'),
            ("CodeOutput", "output", CodeOutput, "output"),
            ("Image", "base64data", Image, "base64data"),
            ("ServerError", "error", ServerError, "error"),
            (
                "ServerHint",
                '{"key": "val"}',
                ServerHint,
                {"key": "val"},
            ),
            ("Prompt", "prompt", Prompt, "prompt"),
            ("OpenAIError", "error", OpenAIError, "error"),
            ("CodeError", "error", CodeError, "error"),
            ("StreamEnd", "", StreamEnd, ""),
        ],
    )
    def test_discriminator(self, variant, content, expected_class, expected_content):
        """Test MessageModel creates correct message type based on variant."""
        msg = MessageModel(message={"variant": variant, "content": content})
        assert isinstance(msg.message, expected_class)
        assert msg.variant == variant
        assert msg.content == expected_content

    def test_content_getter(self):
        """Test content getter delegates to message."""
        msg = MessageModel(message={"variant": "Assistant", "content": "test content"})
        assert msg.content == "test content"
        assert msg.message.content == "test content"

    def test_content_setter(self):
        """Test content setter delegates to message."""
        msg = MessageModel(message={"variant": "Assistant", "content": "old"})
        msg.content = "new"
        assert msg.message.content == "new"
        assert msg.content == "new"

    def test_variant_getter(self):
        """Test variant getter delegates to message."""
        msg = MessageModel(message={"variant": "User", "content": "test"})
        assert msg.variant == "User"

    def test_variant_setter(self):
        """Test variant setter delegates to message."""
        msg = MessageModel(message={"variant": "Assistant", "content": "test"})
        msg.variant = "User"
        assert msg.message.variant == "User"
        assert msg.variant == "User"

    def test_code_cells_getter(self):
        """Test code_cells getter delegates to message"""
        msg = MessageModel(
            message={"variant": "Code", "content": '{"code": "import xarray as xr"}'}
        )
        assert all(code1 == code2 for code1, code2 in zip(msg.code_cells, msg.message.code_cells))

    def test_repr_markdown_delegation(self):
        """Test repr_markdown delegates to message."""
        msg = MessageModel(message={"variant": "Code", "content": '{"code": "x=1"}'})
        assert msg.repr_markdown() == msg.message.repr_markdown()

    def test_model_dump(self):
        """Test model_dump returns message data."""
        msg = MessageModel(message={"variant": "Assistant", "content": "test", "id": "123"})
        dumped = msg.model_dump()
        assert "message" in dumped
        assert dumped["message"]["variant"] == "Assistant"
        assert dumped["message"]["content"] == "test"


# =============================================================================
# Conversation Tests
# =============================================================================


class TestConversation:
    """Tests for Conversation class."""

    def test_messages_combines_same_variant(self):
        """Test messages property combines chunks with same variant."""
        messages = [
            MessageModel(message={"variant": "Assistant", "content": "Hello"}),
            MessageModel(message={"variant": "Assistant", "content": " world"}),
        ]
        conv = Conversation(raw_messages=messages)
        assert len(conv.messages) == 1
        assert conv.messages[0].content == "Hello world"
        assert conv.messages[0].variant == "Assistant"

    def test_messages_separates_different_variant(self):
        """Test messages property separates different variants."""
        messages = [
            MessageModel(message={"variant": "User", "content": "Q:"}),
            MessageModel(message={"variant": "Assistant", "content": "A:"}),
        ]
        conv = Conversation(raw_messages=messages)
        assert len(conv.messages) == 2
        assert conv.messages[0].variant == "User"
        assert conv.messages[0].content == "Q:"
        assert conv.messages[1].variant == "Assistant"
        assert conv.messages[1].content == "A:"

    def test_messages_serverhint_stays_separate(self):
        """Test ServerHint messages stay separate even with same variant."""
        messages = [
            MessageModel(message={"variant": "ServerHint", "content": '{"id": 1}'}),
            MessageModel(message={"variant": "ServerHint", "content": '{"id": 2}'}),
        ]
        conv = Conversation(raw_messages=messages)
        assert len(conv.messages) == 2
        assert conv.messages[0].variant == "ServerHint"
        assert conv.messages[1].variant == "ServerHint"

    def test_messages_preserves_order(self):
        """Test messages property preserves ordering."""
        messages = [
            MessageModel(message={"variant": "User", "content": "first"}),
            MessageModel(message={"variant": "Assistant", "content": "second"}),
            MessageModel(message={"variant": "User", "content": "third"}),
        ]
        conv = Conversation(raw_messages=messages)
        assert len(conv.messages) == 3
        assert conv.messages[0].variant == "User"
        assert conv.messages[0].content == "first"
        assert conv.messages[1].variant == "Assistant"
        assert conv.messages[1].content == "second"
        assert conv.messages[2].variant == "User"
        assert conv.messages[2].content == "third"

    def test_assistant_code_cell_aggregation(self):
        messages = [
            MessageModel(message={"variant": "Assistant", "content": "Hello!\n```python\n"})
        ]
        conv = Conversation(raw_messages=messages)
        # no code messages (incomplete markdown python code-block)
        assert conv.code_cells == []
        # complete markdown python code-block
        messages.append(
            MessageModel(message={"variant": "Assistant", "content": "import xarray as xr\n```"})
        )
        conv = Conversation(raw_messages=messages)
        assert len(conv.code_cells) == 1
        assert "import xarray as xr" in conv.code_cells[0]

    def test_code_cells_aggregation(self):
        """Test code_cells aggregates from all messages."""
        messages = [
            MessageModel(
                message={"variant": "Code", "content": '{"code": "import xarray as xr\\n'}
            ),
            MessageModel(message={"variant": "Code", "content": 'x=1"}'}),
        ]
        conv = Conversation(raw_messages=messages)
        # Single code message
        assert len(conv.code_cells) == 1
        assert "import xarray as xr" in conv.code_cells[0]
        assert "x=1" in conv.code_cells[0]

    def test_code_cells_incomplete_code_messages(self):
        """Test code_cells returns empty list with incomplete messages."""
        messages = [
            MessageModel(message={"variant": "Assistant", "content": '{"code": import xarray as'}),
        ]
        conv = Conversation(raw_messages=messages)
        assert conv.code_cells == []

    def test_repr_markdown_concatenates(self):
        """Test repr_markdown concatenates all message markdown."""
        messages = [
            MessageModel(message={"variant": "Assistant", "content": "Hello"}),
            MessageModel(message={"variant": "Code", "content": '{"code": "x=1"}'}),
        ]
        conv = Conversation(raw_messages=messages)
        markdown = conv.repr_markdown()
        assert "Hello" in markdown
        assert "```python" in markdown
        assert "x=1" in markdown
        assert markdown.endswith("\n")

    def test_str_format(self):
        """Test __str__ returns formatted chat string."""
        messages = [
            MessageModel(message={"variant": "User", "content": "Question"}),
        ]
        conv = Conversation(raw_messages=messages)
        conv_str = str(conv)
        assert "[0]" in conv_str
        assert "User" in conv_str
        assert "Question" in conv_str

    def test_str_format_multiple(self):
        """Test __str__ with multiple messages."""
        messages = [
            MessageModel(message={"variant": "User", "content": "Q"}),
            MessageModel(message={"variant": "Assistant", "content": "A"}),
        ]
        conv = Conversation(raw_messages=messages)
        conv_str = str(conv)
        assert "[0]" in conv_str
        assert "[1]" in conv_str
        assert "User" in conv_str
        assert "Assistant" in conv_str

    def test_getitem_single(self):
        """Test __getitem__ with single index."""
        messages = [
            MessageModel(message={"variant": "Assistant", "content": "first"}),
        ]
        conv = Conversation(raw_messages=messages)
        # messages[0] is the combined message
        assert conv[0].content == "first"

    def test_getitem_slice(self):
        """Test __getitem__ with slice."""
        messages = [
            MessageModel(message={"variant": "Assistant", "content": "a"}),
            MessageModel(message={"variant": "Assistant", "content": "b"}),
            MessageModel(message={"variant": "Assistant", "content": "c"}),
        ]
        conv = Conversation(raw_messages=messages)
        # All same variant, so combined into one message
        assert len(conv[:]) == 1

    def test_len(self):
        """Test __len__ returns correct count."""
        messages = [
            MessageModel(message={"variant": "Assistant", "content": "a"}),
            MessageModel(message={"variant": "User", "content": "b"}),
        ]
        conv = Conversation(raw_messages=messages)
        assert len(conv) == 2


# =============================================================================
# StreamConversation Tests
# =============================================================================


class TestStreamConversation:
    """Tests for StreamConversation class."""

    def test_initialization(self, mocker):
        """Test StreamConversation initialization."""

        mock_stream_response = mocker.MagicMock()
        mock_stream_response.is_closed = False
        mock_on_exit_callback = mocker.MagicMock()
        stream_conv = StreamConversation(
            stream=mock_stream_response, on_exit_callback=mock_on_exit_callback
        )

        assert stream_conv.stream_response == mock_stream_response
        assert stream_conv._on_exit_callback == mock_on_exit_callback
        assert stream_conv.conversation is None
        assert stream_conv._current_message is None
        assert stream_conv._buffered_content == ""

    def test_context_manager_enter(self, mocker):
        """Test context manager __enter__ returns self."""

        mock_response = mocker.MagicMock()
        mock_response.is_closed = False
        stream_conv = StreamConversation(mock_response)

        with stream_conv:
            assert stream_conv is not None

    @pytest.mark.asyncio
    async def test_async_context_manager_aenter(self, mocker: MockerFixture):
        """Test async context manager __aenter__ returns self."""
        mock_response = mocker.MagicMock()
        mock_response.is_closed = False
        stream_conv = StreamConversation(mock_response)

        async with stream_conv:
            assert stream_conv is not None

    def test_context_manager_exit_closes_stream(self, mocker):
        """Test context manager __exit__ closes stream."""
        mock_stream_response = mocker.MagicMock()
        mock_stream_response.is_closed = False
        mock_on_exit_callback = mocker.MagicMock()
        stream_conv = StreamConversation(
            stream=mock_stream_response, on_exit_callback=mock_on_exit_callback
        )
        with stream_conv:
            pass
        mock_stream_response.close.assert_called_once()
        mock_on_exit_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_context_manager_aexit_closes_stream(self, mocker: MockerFixture):
        """Test async context manager __aexit__ closes stream."""
        mock_stream_response = mocker.MagicMock()
        mock_stream_response.is_closed = False
        mock = mocker.AsyncMock()

        async def _exit_callback():
            await mock()

        stream_conv = StreamConversation(
            stream=mock_stream_response, on_exit_callback=_exit_callback
        )
        async with stream_conv:
            pass
        mock_stream_response.close.assert_called_once()
        mock.assert_awaited_once()

    def test_process_chunk_first_message(self, mocker):
        """Test process_chunk sets _current_message on first chunk."""

        mock_response = mocker.MagicMock()
        stream_conv = StreamConversation(mock_response)

        first_chunk = MessageModel(message={"variant": "Assistant", "content": "Hello"})
        output = stream_conv.process_chunk(first_chunk)

        assert stream_conv._current_message is not None
        assert stream_conv._current_message.variant == "Assistant"
        assert "Hello" in output

    def test_process_chunk_same_variant_accumulates(self, mocker):
        """Test process_chunk accumulates content for same variant."""

        mock_response = mocker.MagicMock()
        stream_conv = StreamConversation(mock_response)

        chunk1 = MessageModel(message={"variant": "Assistant", "content": "Hello"})
        chunk2 = MessageModel(message={"variant": "Assistant", "content": " world"})

        stream_conv.process_chunk(chunk1)
        output = stream_conv.process_chunk(chunk2)

        assert "Hello world" == stream_conv._current_message.content
        # For Assistant variant, content is yielded immediately
        assert " world" in output

    def test_process_chunk_different_variant_flushes(self, mocker):
        """Test process_chunk flushes previous message on variant change."""

        mock_response = mocker.MagicMock()
        stream_conv = StreamConversation(mock_response)

        chunk1 = MessageModel(message={"variant": "Assistant", "content": "Hello"})
        chunk2 = MessageModel(message={"variant": "User", "content": "Hi"})

        stream_conv.process_chunk(chunk1)
        output = stream_conv.process_chunk(chunk2)

        # Previous Assistant message should be flushed (output from first chunk)
        # And new User message starts fresh
        assert stream_conv._current_message.variant == "User"
        # The flush output should contain the previous content
        assert len(output) > 0

    def test_process_chunk_image_buffers(self, mocker):
        """Test Image variant buffers without output."""

        mock_response = mocker.MagicMock()
        stream_conv = StreamConversation(mock_response)

        chunk = MessageModel(message={"variant": "Image", "content": "base64data"})
        output = stream_conv.process_chunk(chunk)

        # Image should buffer, no output yet
        assert output == []
        assert stream_conv._current_message.variant == "Image"

    def test_process_chunk_code_output_skipped(self, mocker):
        """Test CodeOutput variant is skipped in incremental output."""

        mock_response = mocker.MagicMock()
        stream_conv = StreamConversation(mock_response)

        chunk = MessageModel(message={"variant": "CodeOutput", "content": "output"})
        output = stream_conv.process_chunk(chunk)

        # CodeOutput should be skipped
        assert output == []

    @pytest.mark.parametrize(
        "flushed_variant, content", [("Image", "base64encodedImage"), ("CodeOutput", "code_output")]
    )
    def test_flush_previous(self, mocker, flushed_variant, content):
        """Test that certain messages (CodeOutput, Image) are flushed and returned correctly"""
        mock_response = mocker.MagicMock()
        stream_conv = StreamConversation(mock_response)
        stream_conv._buffered_content = "base64encodedImage"
        stream_conv._current_message = MessageModel(
            message={"variant": flushed_variant, "content": content}
        )
        output = stream_conv._flush_previous()
        assert stream_conv._buffered_content == ""
        assert content in output[0]

    def test_iter_for_markdown(self, mocker):
        """Test that iter_for_markdown yields chunks ready for rendering in markdown"""
        mock_response = mocker.MagicMock()
        message_dicts = [
            dict(variant="Assistant", content="Running the code!"),
            dict(variant="Code", content='{"code": "import xarray as xr"}'),
            dict(variant="ServerHint", content='{"id": 123}'),
            dict(variant="Image", content="base64encodedImage"),
            dict(variant="Assistant", content="Code execution complete!"),
            dict(variant="StreamEnd", content="Stream ended."),
        ]
        mock_response.iter_json_objects = mocker.MagicMock(return_value=message_dicts)
        messages = [MessageModel(message=m) for m in message_dicts]
        stream_conv = StreamConversation(mock_response)
        assert stream_conv.conversation is None
        markdown_result = [md for md in stream_conv.iter_for_markdown()]
        for message in messages:
            if message.variant in ["ServerHint", "StreamEnd"]:
                assert all(str(message.content) not in md for md in markdown_result)
            elif message.variant == "Code":
                assert any(
                    f"```python\n{message.code_cells[0]}\n```" in md for md in markdown_result
                )
            elif message.variant == "Image":
                assert any(
                    f"![Image](data:image/png;base64,{message.content})" in md
                    for md in markdown_result
                )
            else:
                assert any(message.content in md for md in markdown_result)
        conversation = Conversation(raw_messages=messages)
        assert stream_conv.conversation == conversation

    def test_iter_raw(self, mocker):
        """Test that iter_raw returns dictionaries ready for use in MessageModel"""
        mock_response = mocker.MagicMock()
        message_dicts = [
            dict(variant="Assistant", content="Running the code!"),
            dict(variant="Code", content='{"code": "import xarray as xr"}'),
            dict(variant="ServerHint", content='{"id": 123}'),
            dict(variant="Image", content="base64encodedImage"),
            dict(variant="Assistant", content="Code execution complete!"),
            dict(variant="StreamEnd", content="Stream ended."),
        ]
        mock_response.iter_json_objects = mocker.MagicMock(return_value=message_dicts)
        messages = [MessageModel(message=m) for m in message_dicts]
        stream_conv = StreamConversation(mock_response)
        assert stream_conv.conversation is None
        raw_result = [raw_dict for raw_dict in stream_conv.iter_raw()]
        assert all(
            input_dict == output_dict for input_dict, output_dict in zip(message_dicts, raw_result)
        )
        conversation = Conversation(raw_messages=messages)
        assert stream_conv.conversation == conversation

    def test_translate_to_conversation(self, mocker):
        """Test that given a set of message chunks translate_to_conversation returns a Conversation object containing these messages"""
        mock_response = mocker.MagicMock()
        messages = [
            dict(variant="Assistant", content="Hello "),
            dict(variant="Assistant", content="world!"),
        ]
        mock_response.iter_json_objects = mocker.MagicMock(return_value=messages)
        stream_conv = StreamConversation(mock_response)
        assert stream_conv.conversation is None
        conv = stream_conv.translate_to_conversation()
        assert conv.messages[0].content == "Hello world!"
        mock_response.iter_json_objects.assert_called_once()
        # check that a second call to the same method just returns the already processed conversation object
        mock_response.iter_json_objects.reset_mock()
        assert stream_conv.translate_to_conversation() == conv
        assert mock_response.iter_json_objects.call_count == 0

    # Async context manager and iteration tests

    @pytest.mark.asyncio
    async def test_async_context_manager_enter(self, mocker):
        """Test async context manager __aenter__ returns self."""
        mock_response = mocker.MagicMock()
        mock_response.is_closed = False
        stream_conv = StreamConversation(mock_response)
        async with stream_conv:
            assert stream_conv is not None

    @pytest.mark.asyncio
    async def test_async_context_manager_exit_closes_stream(self, mocker):
        """Test async context manager __aexit__ closes stream."""
        mock_stream_response = mocker.MagicMock()
        mock_stream_response.is_closed = False
        mock_on_exit_callback = mocker.MagicMock()
        stream_conv = StreamConversation(
            stream=mock_stream_response, on_exit_callback=mock_on_exit_callback
        )
        async with stream_conv:
            pass
        mock_stream_response.close.assert_called_once()
        mock_on_exit_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_aiter_for_markdown(self, mocker):
        """Test that aiter_for_markdown yields chunks ready for rendering in markdown"""
        mock_response = mocker.MagicMock()
        message_dicts = [
            dict(variant="Assistant", content="Running the code!"),
            dict(variant="Code", content='{"code": "import xarray as xr"}'),
            dict(variant="ServerHint", content='{"id": 123}'),
            dict(variant="Image", content="base64encodedImage"),
            dict(variant="Assistant", content="Code execution complete!"),
            dict(variant="StreamEnd", content="Stream ended."),
        ]

        async def async_gen():
            for item in message_dicts:
                yield item

        mock_response.aiter_json_objects = mocker.MagicMock(return_value=async_gen())
        messages = [MessageModel(message=m) for m in message_dicts]
        stream_conv = StreamConversation(mock_response)
        assert stream_conv.conversation is None
        markdown_result = [md async for md in stream_conv.aiter_for_markdown()]
        for message in messages:
            if message.variant in ["ServerHint", "StreamEnd"]:
                assert all(str(message.content) not in md for md in markdown_result)
            elif message.variant == "Code":
                assert any(
                    f"```python\n{message.code_cells[0]}\n```" in md for md in markdown_result
                )
            elif message.variant == "Image":
                assert any(
                    f"![Image](data:image/png;base64,{message.content})" in md
                    for md in markdown_result
                )
            else:
                assert any(message.content in md for md in markdown_result)
        conversation = Conversation(raw_messages=messages)
        assert stream_conv.conversation == conversation

    @pytest.mark.asyncio
    async def test_aiter_raw(self, mocker):
        """Test that aiter_raw returns dictionaries ready for use in MessageModel"""
        mock_response = mocker.MagicMock()
        message_dicts = [
            dict(variant="Assistant", content="Running the code!"),
            dict(variant="Code", content='{"code": "import xarray as xr"}'),
            dict(variant="ServerHint", content='{"id": 123}'),
            dict(variant="Image", content="base64encodedImage"),
            dict(variant="Assistant", content="Code execution complete!"),
            dict(variant="StreamEnd", content="Stream ended."),
        ]

        async def async_gen():
            for item in message_dicts:
                yield item

        mock_response.aiter_json_objects = mocker.MagicMock(return_value=async_gen())
        messages = [MessageModel(message=m) for m in message_dicts]
        stream_conv = StreamConversation(mock_response)
        assert stream_conv.conversation is None
        raw_result = [raw_dict async for raw_dict in stream_conv.aiter_raw()]
        assert all(
            input_dict == output_dict for input_dict, output_dict in zip(message_dicts, raw_result)
        )
        conversation = Conversation(raw_messages=messages)
        assert stream_conv.conversation == conversation


# =============================================================================
# ProcessCodeChunk Tests (Isolated)
# =============================================================================


class TestProcessCodeChunk:
    """Isolated tests for _process_code_chunk logic."""

    def test_prefix_split_across_chunks(self):
        """Test prefix '{\"code\":' split across multiple chunks."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        stream_conv = StreamConversation(mock_response)

        # Simulate prefix arriving in chunks
        chunks = [
            MessageModel(message={"variant": "Code", "content": '{"'}),
            MessageModel(message={"variant": "Code", "content": "code"}),
            MessageModel(message={"variant": "Code", "content": '":'}),
        ]
        for chunk in chunks[:-1]:
            stream_conv.process_chunk(chunk)
        output = stream_conv.process_chunk(chunks[-1])

        # After prefix is complete, should output code block start
        assert "```python" in output[0]

    def test_backslash_buffering(self):
        """Test that chunks ending with backslash are buffered."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        stream_conv = StreamConversation(mock_response)

        # First need to send prefix
        prefix_chunk = MessageModel(message={"variant": "Code", "content": '{"code":"'})
        stream_conv.process_chunk(prefix_chunk)

        # Then backslash
        backslash_chunk = MessageModel(message={"variant": "Code", "content": "\\"})
        output1 = stream_conv.process_chunk(backslash_chunk)

        # Should buffer, no output
        assert output1 == []

    def test_escape_sequence_n(self):
        """Test \\n sequence is converted to newline."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        stream_conv = StreamConversation(mock_response)

        # Send prefix
        prefix_chunk = MessageModel(message={"variant": "Code", "content": '{"code":"'})
        stream_conv.process_chunk(prefix_chunk)

        # Send backslash
        backslash_chunk = MessageModel(message={"variant": "Code", "content": "\\"})
        stream_conv.process_chunk(backslash_chunk)

        # Send n
        n_chunk = MessageModel(message={"variant": "Code", "content": "n"})
        output = stream_conv.process_chunk(n_chunk)

        # Should output newline
        assert any("\n" == o or "\n" in o for o in output)

    def test_non_escape_backslash_preserved(self):
        """Test that backslash not part of escape sequence is preserved."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        stream_conv = StreamConversation(mock_response)

        # Send prefix
        prefix_chunk = MessageModel(message={"variant": "Code", "content": '{"code":"'})
        stream_conv.process_chunk(prefix_chunk)

        # Send backslash
        backslash_chunk = MessageModel(message={"variant": "Code", "content": "\\"})
        stream_conv.process_chunk(backslash_chunk)

        # Send x (not an escape sequence)
        x_chunk = MessageModel(message={"variant": "Code", "content": "x"})
        output = stream_conv.process_chunk(x_chunk)

        # Should output \x
        assert any("\\x" in o for o in output)

    def test_suffix_detection(self):
        """Test that suffix '\"}' completes the code block."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        stream_conv = StreamConversation(mock_response)

        # Send complete code message
        chunk = MessageModel(message={"variant": "Code", "content": '{"code":"x=1"}'})
        output = stream_conv.process_chunk(chunk)

        # Should detect suffix and output code block end
        assert any("```" in o for o in output)


# =============================================================================
# Pydantic Validation Tests
# =============================================================================


class TestPydanticValidation:
    """Tests for Pydantic model validation."""

    def test_base_message_variant_type(self):
        """Test that variant must be one of the Literal values."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BaseMessage(variant="InvalidVariant", content="test")

    def test_code_content_must_be_string(self):
        """Test that Code.content must be a string."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Code(variant="Code", content=123)

        with pytest.raises(ValidationError):
            Code(variant="Code", content=["list", "content"])

    def test_serverhint_content_accepts_dict(self):
        """Test that ServerHint.content accepts dict."""
        msg = ServerHint(variant="ServerHint", content={"key": "value"})
        assert msg.content == {"key": "value"}

    def test_serverhint_content_accepts_parseable_string(self):
        """Test that ServerHint.content accepts parseable string."""
        msg = ServerHint(variant="ServerHint", content='{"key": "value"}')
        assert msg.content == {"key": "value"}

    def test_image_content_must_be_string(self):
        """Test that Image.content must be a string."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Image(variant="Image", content=123)

        with pytest.raises(ValidationError):
            Image(variant="Image", content={"not": "string"})

    def test_message_model_discriminator_validation(self):
        """Test MessageModel validates variant through discriminator."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MessageModel(message={"variant": "InvalidType", "content": "test"})
