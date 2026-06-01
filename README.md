# FrevaGPT Client

[![License](https://github.com/eClip-/EUPL-badge/blob/master/eupl_1.2.svg)](LICENSE)
[![docs](https://readthedocs.org/projects/freva-gpt-client/badge/?version=latest)](https://freva-gpt-client.readthedocs.io/latest/?badge=latest)
[![codecov](https://codecov.io/github/freva-org/freva-gpt-client/graph/badge.svg?token=kDsGq9llcK)](https://codecov.io/github/freva-org/freva-gpt-client)

A Python client library for interacting with the [FrevaGPT backend](https://github.com/freva-org/freva-gpt-backend-py). This library provides both synchronous and asynchronous interfaces for communicating with a FrevaGPT chatbot instance.

**Features:**
- Synchronous client (`FrevaGPT`) with full API support
- Asynchronous client (`AsyncFrevaGPT`) with full API support
- OIDC authentication via [py-oidc-auth-client](https://pypi.org/project/py-oidc-auth-client/)
- Thread management (create, retrieve, list, search, fork, and delete conversation threads)
- Streaming and non-streaming prompt responses
- Thread operations (stop active conversations, set thread topics, edit/fork threads)
- User feedback (submit positive/negative feedback on assistant messages)
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
    token_store_path="~/.cache/freva-gpt-client/token-store.json",  # Optional: path to store auth tokens
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
conversation = client.prompt(
    "Please calculate the average temperature over Germany for the years 1990-2020!"
)
# Render the entire answer as a human-readable string
print(conversation)

# Access the individual messages
for message in conversation.messages:
    print(f"{message.variant}: {message.content}")

# Get markdown representation
markdown = conversation.repr_markdown()
print(markdown)
```

#### Streamed Response

```python
# Send a prompt with streaming enabled
stream_conv = client.prompt(
    "Please explain the ENSO phenomenon to me and give examples of how to quantify it!", stream=True
)

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
    thread_id=thread_id,  # optional: uses thread of active conversation otherwise
)
```

#### List User Threads

```python
# List all your conversation threads
total_threads, user_threads = client.getuserthreads(num_threads=10)
print(f"A total number of {total_threads} threads was retrieved.")
# access individual threads (which are Conversation objects)
print(user_threads[0])
```

#### Search Threads

```python
# Search for threads by topic
total_results, matching_threads = client.searchthreads(query="climate analysis", num_threads=5)
```

#### Set Thread Topic

```python
# Set a topic for a thread (useful for searching later)
client.setthreadtopic("ENSO analysis", thread_id=thread_id)
```

#### Delete a Thread

```python
# Delete a thread on the backend when you're done with it
client.deletethread(thread_id=thread_id)
```

### Working with Message Types

The client provides rich message types that can be rendered in different formats:

```python
from freva_gpt_client.client import FrevaGPT

# Create a client instance
client = FrevaGPT(base_url="https://your-freva-gpt-backend.com")

# Authenticate with the backend
client.authenticate()

# List available models
print(f"Available models: {client.available_models}")
client.model = client.available_models[0]

# Start a conversation
response = client.prompt(
    "Show me a code example of using the xarray library for analysing climate data!"
)

# Access individual messages
initial_response = response[0]

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
if response.messages[1].variant == "Image":
    image_message = conversation.messages[1]

    # Get markdown representation (base64 embedded)
    md = image_message.repr_markdown()

    # Save to file
    image_message.save_to_file("output.png")
```

### Raw Message Access

```python
# Access raw message chunks (before aggregation)
response = client.prompt("Hello FrevaGPT! What is your function?")

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

## Asynchronous Client

The library includes an `AsyncFrevaGPT` class for async operations, providing the same functionality as the synchronous client but with async/await syntax:

```python
import asyncio
from freva_gpt_client import AsyncFrevaGPT


async def main():
    # Create an async client instance
    client = AsyncFrevaGPT(
        base_url="https://your-freva-gpt-backend.com",
        token_store_path="~/.cache/freva-gpt-client/token-store.json",
    )

    # Authenticate with the backend
    await client.authenticate()

    # List available models
    print(f"Available models: {client.available_models}")
    client.model = client.available_models[0]

    # Send a prompt
    response = await client.prompt(
        "Please calculate the average temperature over Germany for 1990-2020!"
    )
    print(response)

    # Send a streaming prompt
    stream_resp = await client.prompt("Please explain the ENSO phenomenon to me!", stream=True)
    async with stream_resp as stream:
        async for markdown_chunk in stream.aiter_for_markdown():
            print(markdown_chunk)

    # Thread management
    thread_id = await client.newthread()
    response = await client.prompt(
        "Please explain how the SOI can be calculated.",
        thread_id=thread_id,
    )


# Run the async main function
asyncio.run(main())
```

**Note:** The async client uses `httpx.AsyncClient` under the hood and provides all the same methods as the synchronous `FrevaGPT` client, but as coroutines that must be awaited.

## Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | str/URL | Required | Base URL of the FrevaGPT backend |
| `token_store_path` | str | "" | Path to store OIDC tokens |
| `follow_redirects` | bool | True | Whether to follow HTTP redirects |
| `timeout` | float | 30.0 | Request timeout in seconds |
| `max_retries` | int | 3 | Maximum retry attempts for failed requests |
| `http_client` | httpx.Client / httpx.AsyncClient | None | Pre-configured HTTP client (Optional) |
| `thread_id` | str | None | Default thread ID for conversations |
| `model` | str | None | Default model for prompts |

**Note:** For `AsyncFrevaGPT`, the `http_client` parameter should be an `httpx.AsyncClient` instance, while for `FrevaGPT` it should be an `httpx.Client` instance.


## Project Links

- **Source Code**: https://github.com/freva-org/freva-gpt-client
- **Backend Repository**: https://github.com/freva-org/freva-gpt-backend-py
- **Documentation**: https://freva-gpt-client.readthedocs.io/en/latest/
- **Issue Tracker**: https://github.com/freva-org/freva-gpt-client/issues

## License

This project is licensed under the European Union Public Licence 1.2 (EUPL-1.2).
