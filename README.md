# FrevaGPT Client

[![License](https://github.com/eClip-/EUPL-badge/blob/master/eupl_1.2.svg)](LICENSE)
[![docs](https://readthedocs.org/projects/freva-gpt-client/badge/?version=latest)](https://freva-gpt-client.readthedocs.io/en/latest/?badge=latest)

A Python client library for interacting with the [FrevaGPT backend](https://github.com/freva-org/freva-gpt-backend-py). This library provides both synchronous and asynchronous (not yet fully implemented) interfaces for communicating with a FrevaGPT chatbot instance.

**Features:**
- Synchronous client with full API support
- Asynchronous client (placeholder, async methods coming soon)
- OIDC authentication via [py-oidc-auth-client](https://pypi.org/project/py-oidc-auth-client/)
- Thread management (create, retrieve, interact with conversation threads)
- Streaming and non-streaming prompt responses
- Rich message types with markdown rendering support

## Requirements

- Python 3.10+

## Dependencies

- `httpx` - HTTP client for making requests
- `pydantic` - Data validation and message modeling
- `py_oidc_auth_client` - OIDC authentication handling

## Installation

Currently, this package is in development and must be installed from source:

```bash
git clone https://github.com/freva-org/freva-gpt-client.git
cd freva-gpt-client
pip install -e .
```

Or using `uv`:

```bash
uv pip install -e .
```

## Usage

### Initialization

```python
from freva_gpt_client.client import FrevaGPT

# Create a client instance
frevagpt = FrevaGPT(
    base_url="https://your-freva-gpt-backend.com",
    token_store_path="~/.cache/freva-gpt-client/token-store.json"  # Optional: path to store auth tokens
)

# Authenticate with the backend (triggers OIDC flow)
client.authenticate()
```

### Available Models

```python
# List available chatbot models
models = client.available_models
print(f"Available models: {models}")

# Set a default model for the client
frevagpt.model = "gpt-4.1"
```

### Prompting the Backend

#### Non-streamed Response

```python
# Send a prompt and get the complete conversation
conversation = client.prompt("Please calculate the average temperature over Germany for the years 1990-2020!")

# Access the conversation messages
for message in conversation.messages:
    print(f"{message.variant}: {message.content}")

# Get markdown representation
markdown = conversation.repr_markdown()
print(markdown)
```

#### Streamed Response

```python
# Send a prompt with streaming enabled
stream_conv = client.prompt("Please explain the ENSO phenomenon to me and give examples of how to quantify it!", stream=True)

# Iterate over markdown-ready chunks as they arrive
with stream_conv as stream:
    for markdown_chunk in stream.iter_for_markdown():
        print(markdown_chunk)

# After streaming completes, access the full conversation
full_conversation = stream_conv.translate_to_conversation()
print(full_conversation.repr_markdown())
```

### Thread Management

#### Create a New Thread

```python
# Create a new conversation thread
thread_id = client.newthread()
print(f"New thread ID: {thread_id}")
```

#### Get a Thread

```python
# Retrieve an existing thread by ID
thread_id = "your-thread-id"
conversation = client.getthread(thread_id=thread_id)

# Or use the current active thread
conversation = client.getthread() 

# Print all messages
print(conversation)
```

#### Prompt in a Specific Thread

```python
# Continue a conversation in an existing thread
response = client.prompt(
    "Please explain how the SOI can be calculated and run an example analysis.",
    thread_id=thread_id # optional: uses thread of active conversation otherwise
)
```

### Working with Message Types

The client provides rich message types that can be rendered in different formats:

```python
from freva_gpt_client.client import FrevaGPT

client = FrevaGPT(base_url="https://your-freva-gpt-backend.com")
client.authenticate()

# Get a conversation
conversation = client.prompt("Show me a code example of using the xarray library for analysing climate data!")

# Access individual messages
initial_response = conversation[0]

# String representation (for Python sessions)
print(str(initial_response))

# Markdown representation (for rendering)
print(initial_response.repr_markdown())

# Access content directly
print(initial_response.content)

# Extract code cells from Assistant messages
for code_cell in initial_response.message.code_cells:
    print(f"Code cell: {code_cell}")
```

### Handling Images

Image messages have special methods:

```python
# If the response contains an image
if conversation.messages[1].variant == "Image":
    image_message = conversation.messages[1]
    
    # Get markdown representation (base64 embedded)
    md = image_message.repr_markdown()
    
    # Save to file
    image_message.save_to_file("output.png")
```

### Raw Message Access

```python
# Access raw message chunks (before aggregation)
conversation = client.prompt("Hello FrevaGPT! What is your function?")

for raw_msg in conversation.raw_messages:
    print(raw_msg.message.variant)
    print(raw_msg.message.content)
```


## Message Types

The library supports the following message variants:

| Variant | Description | Special Methods |
|---------|-------------|-----------------|
| `Prompt` | Initial user prompt | `repr_content()`, `repr_markdown()` |
| `User` | User message | `repr_content()`, `repr_markdown()` |
| `Assistant` | Assistant response | `code_cells` property, `repr_content()`, `repr_markdown()` |
| `Code` | Python code | `code_cells` property, `repr_markdown()` renders as code block |
| `CodeOutput` | Code execution output | `repr_markdown()` renders as blockquote |
| `Image` | Base64-encoded image | `repr_markdown()`, `save_to_file()` |
| `ServerError` | Server error message | `repr_content()`, `repr_markdown()` |
| `OpenAIError` | OpenAI error message | `repr_content()`, `repr_markdown()` |
| `CodeError` | Code execution error | `repr_content()`, `repr_markdown()` |
| `StreamEnd` | Stream completion marker | `repr_markdown()` |
| `ServerHint` | Backend hint data (such as server heartbeats) | `repr_markdown()` |

## Asynchronous Client (Coming Soon)

The library includes an `AsyncFrevaGPT` class for async operations:

```python
from freva_gpt_client.client import AsyncFrevaGPT

async def main():
    client = AsyncFrevaGPT(base_url="https://your-freva-gpt-backend.com")
    await client.authenticate()
    
    # Async methods will be available in future versions
    # response = await client.prompt("Hi FrevaGPT! Can you help me with a climate analysis task today?")

# Note: Async methods are not yet fully implemented
```

## Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | str/URL | Required | Base URL of the FrevaGPT backend |
| `token_store_path` | str | "" | Path to store OIDC tokens |
| `follow_redirects` | bool | True | Whether to follow HTTP redirects |
| `timeout` | float | 30.0 | Request timeout in seconds |
| `max_retries` | int | 3 | Maximum retry attempts for failed requests |
| `http_client` | httpx.Client | None | Pre-configured HTTP client (Optional) |
| `thread_id` | str | None | Default thread ID for conversations |
| `model` | str | None | Default model for prompts |


## Project Links

- **Source Code**: https://github.com/freva-org/freva-gpt-client
- **Backend Repository**: https://github.com/freva-org/freva-gpt-backend-py
- **Documentation**: https://freva-gpt-client.readthedocs.io/en/latest/
- **Issue Tracker**: https://github.com/freva-org/freva-gpt-client/issues

## License

This project is licensed under the European Union Public Licence 1.2 (EUPL-1.2).
