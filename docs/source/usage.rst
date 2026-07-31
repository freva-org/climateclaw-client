Usage Guide
============

This guide covers how to use the ClimateClaw Client library, including initialization, configuration, and common use cases.


Initialization
--------------

The library provides two client classes: ``ClimateClaw`` for synchronous operations and ``AsyncClimateClaw`` for asynchronous operations.

**Synchronous Client:**

.. code-block:: python

    from climate_claw_client.client import ClimateClaw

    cc = ClimateClaw(
        base_url="https://your-climate-claw-backend.com",
        token_store_path="~/.cache/climate-claw-client/token-store.json",
        follow_redirects=True,
        timeout=30.0,
        max_retries=3,
    )

**Asynchronous Client:**

.. code-block:: python

    from climate_claw_client.client import AsyncClimateClaw

    cc = AsyncClimateClaw(
        base_url="https://your-climate-claw-backend.com",
        token_store_path="~/.cache/climate-claw-client/token-store.json",
        follow_redirects=True,
        timeout=30.0,
        max_retries=3,
    )



Configuration Options
----------------------

The client accepts the following configuration parameters:

+----------------------+-------------------------------+---------------------+----------------------------------------------------------+
| Parameter            | Type                          | Default             | Description                                              |
+======================+===============================+=====================+==========================================================+
| ``base_url``         | str/URL                       | **Required**        | Base URL of the ClimateClaw backend                         |
+----------------------+-------------------------------+---------------------+----------------------------------------------------------+
| ``token_store_path`` | str                           | ``""``              | Path to store OIDC tokens                                |
+----------------------+-------------------------------+---------------------+----------------------------------------------------------+
| ``follow_redirects`` | bool                          | ``True``            | Whether to follow HTTP redirects                         |
+----------------------+-------------------------------+---------------------+----------------------------------------------------------+
| ``timeout``          | float                         | ``30.0``            | Request timeout in seconds                               |
+----------------------+-------------------------------+---------------------+----------------------------------------------------------+
| ``max_retries``      | int                           | ``3``               | Maximum retry attempts for failed requests               |
+----------------------+-------------------------------+---------------------+----------------------------------------------------------+
| ``http_client``      | httpx.Client                  | ``None``            | Pre-configured HTTP client (use httpx.Client for         |
|                      | httpx.AsyncClient             |                     | ClimateClaw, htppx.AsyncClient for AsyncClimateClaw)           |
+----------------------+-------------------------------+---------------------+----------------------------------------------------------+
| ``thread_id``        | str                           | ``None``            | Default thread ID for conversations                      |
+----------------------+-------------------------------+---------------------+----------------------------------------------------------+
| ``model``            | str                           | ``None``            | Default model for prompts                                |
+----------------------+-------------------------------+---------------------+----------------------------------------------------------+


Authentication
--------------

Both clients use OIDC authentication. Call ``authenticate()`` (or ``await authenticate()`` for async) to trigger the authentication flow:

.. important::
   When specifying a custom HTTP client during the initialization of ClimateClaw/AsyncClimateClaw, it is assumed that the specified client handles the `authentication <https://www.python-httpx.org/advanced/authentication/>`__ (if required).

**Synchronous:**

.. code-block:: python

    cc = ClimateClaw(base_url="https://your-climate-claw-backend.com")
    cc.authenticate()

**Asynchronous:**

.. code-block:: python

    async def main():
        cc = AsyncClimateClaw(base_url="https://your-climate-claw-backend.com")
        await cc.authenticate()


    asyncio.run(main())

This will open a browser window for authentication and store the tokens in the configured ``token_store_path``.


Working with Models
-------------------

.. code-block:: python

    # List available chatbot models (cached property)
    models = cc.available_models
    print(f"Available models: {models}")

    # Set a default model for the client
    cc.model = "gpt-4.1"

    # Or specify model per request
    conversation = cc.prompt("Hello!", model="gpt-4.1")

    # Note: If no model is set on the client or in the prompt call,
    # a TypeError will be raised


Sending Prompts
---------------

**Non-streamed Response (Synchronous):**

.. code-block:: python

    conversation = cc.prompt("Please calculate the average temperature over Germany!")

    # Render the entire answer as a human-readable string
    print(conversation)

    # Access the conversation messages
    for message in conversation.messages:
        print(f"{message.variant}: {message.content}")

    # Get markdown representation
    markdown = conversation.repr_markdown()
    print(markdown)

**Non-streamed Response (Asynchronous):**

.. code-block:: python

    async def main():
        client = AsyncClimateClaw(base_url="https://your-climate-claw-backend.com")
        await cc.authenticate()

        conversation = await cc.prompt("Please calculate the average temperature over Germany!")

        # Render the entire answer as a human-readable string
        print(conversation)

        # Access the conversation messages
        for message in conversation.messages:
            print(f"{message.variant}: {message.content}")


    asyncio.run(main())


**Streamed Response (Synchronous):**

.. code-block:: python

    stream_conv = cc.prompt("Please explain the ENSO phenomenon to me!", stream=True)

    with stream_conv as stream:
        for markdown_chunk in stream.iter_for_markdown():
            print(markdown_chunk)

    # After streaming completes, access the full conversation
    full_conversation = stream_conv.translate_to_conversation()
    print(full_conversation.repr_markdown())

**Streamed Response (Asynchronous):**

.. code-block:: python

    async def main():
        client = AsyncClimateClaw(base_url="https://your-climate-claw-backend.com")
        await cc.authenticate()

        stream_conv = await cc.prompt("Please explain the ENSO phenomenon to me!", stream=True)

        async with stream_conv as stream:
            async for markdown_chunk in stream.iter_for_markdown():
                print(markdown_chunk)

        # After streaming completes, access the full conversation
        full_conversation = stream_conv.translate_to_conversation()
        print(full_conversation.repr_markdown())


    asyncio.run(main())


Thread Management
-----------------

The following methods are available for managing conversation threads on both ``ClimateClaw`` and ``AsyncClimateClaw``:

+----------------------+----------------------------------------+--------------------------+
| Method               | Description                            | Returns                  |
+======================+========================================+==========================+
| ``newthread()``      | Create a new conversation thread       | ``str``                  |
+----------------------+----------------------------------------+--------------------------+
| ``getthread()``      | Retrieve a thread by ID                | ``Conversation``         |
+----------------------+----------------------------------------+--------------------------+
| ``getuserthreads()`` | Get recent user threads                | ``Tuple``                |
+----------------------+----------------------------------------+--------------------------+
| ``deletethread()``   | Delete a thread by ID                  | ``None``                 |
+----------------------+----------------------------------------+--------------------------+
| ``setthreadtopic()`` | Set topic for a thread                 | ``str``                  |
+----------------------+----------------------------------------+--------------------------+
| ``searchthreads()``  | Search threads by topic                | ``Tuple``                |
+----------------------+----------------------------------------+--------------------------+
| ``editthread()``     | Fork a thread at index                 | ``Tuple``                |
+----------------------+----------------------------------------+--------------------------+
| ``stop()``           | Stop a streaming conversation          | ``bool``                 |
+----------------------+----------------------------------------+--------------------------+
| ``userfeedback()``   | Submit feedback                        | ``str``                  |
+----------------------+----------------------------------------+--------------------------+

Note: ``getuserthreads()`` and ``searchthreads()`` return a tuple of (total_count, thread_list).
``editthread()`` returns a tuple of (new_thread_id, conversation_history).

For ``AsyncClimateClaw``, all these methods must be awaited.

**Create a New Thread:**

.. code-block:: python

    thread_id = cc.newthread()
    print(f"New thread ID: {thread_id}")


**Get a Thread:**

.. code-block:: python

    # Retrieve an existing thread by ID
    thread_id = "your-thread-id"
    conversation = cc.getthread(thread_id=thread_id)

    # Or use the current active thread
    conversation = cc.getthread()

    # Print the entire conversation as a human-readable string
    print(conversation)


**Prompt in a Specific Thread:**

.. code-block:: python

    response = cc.prompt(
        "Please explain how the SOI can be calculated.",
        thread_id=thread_id,  # optional: uses thread of active conversation otherwise
    )


**List User Threads:**

Retrieve your recent conversation threads with metadata:

.. code-block:: python

    # Get the 10 most recent threads
    total_threads, user_threads = cc.getuserthreads(num_threads=10)

    print(f"Total threads available: {total_threads}")
    print(f"Retrieved {len(user_threads)} threads")

    # Each thread includes metadata and content
    for thread_info in user_threads:
        print(f"Thread ID: {thread_info['thread_id']}")
        print(f"Topic: {thread_info.get('topic', 'Untitled')}")
        print(f"Date: {thread_info['date']}")
        # Access the conversation content
        conversation = thread_info["content"]
        print(f"Number of messages: {len(conversation.messages)}")


**Set Thread Topic:**

Set a descriptive topic for a thread to make it easier to search and organize:

.. code-block:: python

    # Set topic for a specific thread
    new_topic = cc.setthreadtopic(new_topic="Analysis of ENSO patterns", thread_id=thread_id)
    print(f"Thread topic set to: {new_topic}")

    # Or set topic for the current active thread
    cc.setthreadtopic("Climate data analysis")


**Search Threads:**

Search your threads by topic text:

.. code-block:: python

    # Search for threads containing "ENSO" in their topic
    total_results, matching_threads = cc.searchthreads(query="ENSO", num_threads=10)

    print(f"Found {total_results} threads matching 'ENSO'")
    for thread_info in matching_threads:
        print(f"  - {thread_info['thread_id']}: {thread_info.get('topic', 'Untitled')}")


**Delete a Thread:**

Remove a thread that you no longer need:

.. code-block:: python

    # Delete a specific thread
    cc.deletethread(thread_id="thread-id-to-delete")

    # Or delete the current active thread
    cc.deletethread()

    # Note: After deletion, the active thread ID is cleared


**Edit/Fork a Thread:**

Create a new thread by forking an existing conversation at a specific message:

.. code-block:: python

    # Fork at message index 2 (zero-based)
    # This creates a new thread with messages 0, 1, 2 from the source thread
    # Message 2 and all subsequent messages are discarded in the new branch
    try:
        new_thread_id, history = cc.editthread(user_index=2, source_thread_id=thread_id)
        print(f"Created new thread: {new_thread_id}")
        print(f"History in new thread: {history}")
    except IndexError as e:
        print(f"Error: {e}")
    except ValueError as e:
        print(f"Thread not found: {e}")


**Stop a Streaming Conversation:**

Cancel an active streaming conversation and any in-flight tool executions:

.. code-block:: python

    # Start a streaming prompt
    stream_conv = cc.prompt("Perform a complex analysis...", stream=True)

    # In a different process or after a timeout, stop it
    cc.stop(thread_id=thread_id)

    # Or use with the current active thread
    cc.stop()


**Submit User Feedback:**

Provide feedback on assistant messages to improve future responses:

.. code-block:: python

    # After receiving a response in a conversation
    conversation = cc.prompt("Please give me an example of a climate data analysis!")

    # Submit positive feedback for the first assistant message (index 1)
    # Note: Index 0 is typically the user prompt, index 1 is the first assistant response
    try:
        message = cc.userfeedback(
            feedback_index=1,
            feedback="up",  # or "down" for negative, "remove" to remove feedback
            thread_id=thread_id,
        )
        print(f"Feedback submitted: {message}")
    except IndexError as e:
        print(f"Invalid message index: {e}")
    except ValueError as e:
        print(f"Invalid feedback value: {e}")


Working with Message Types
--------------------------

The client provides rich message types that can be rendered in different formats:

.. code-block:: python

    conversation = cc.prompt(
        "Show me an example of a climate data analysis using the xarray tutorial datasets!"
    )

    # Access individual messages
    initial_response = conversation[0]

    # String representation
    print(str(initial_response))

    # Markdown representation
    print(initial_response.repr_markdown())

    # Access content directly
    print(initial_response.content)

    # Extract code cells from Assistant messages
    for code_cell in initial_response.message.code_cells:
        print(f"Code cell: {code_cell}")


Handling Images
---------------

Image messages have special methods:

.. code-block:: python

    if conversation.messages[1].variant == "Image":
        image_message = conversation.messages[1]

        # Get markdown representation (base64 embedded)
        md = image_message.repr_markdown()

        # Return message as a PIL Image
        pil_im = image_message.to_pil_image()

        # Save to file
        image_message.save_to_file("output.png")


Raw Message Access
------------------

.. code-block:: python

    conversation = cc.prompt("Hello ClimateClaw!")

    for raw_msg in conversation.raw_messages:
        print(raw_msg.message.variant)
        print(raw_msg.message.content)


Message Variants Reference
---------------------------

The library supports the following message variants:

+----------------+--------------------------------------+------------------------------------------+
| Variant        | Description                          | Special Methods                          |
+================+======================================+==========================================+
| ``Prompt``     | Initial user prompt                  | ``repr_content()``, ``repr_markdown()``  |
+----------------+--------------------------------------+------------------------------------------+
| ``User``       | User message                         | ``repr_content()``, ``repr_markdown()``  |
+----------------+--------------------------------------+------------------------------------------+
| ``Assistant``  | Assistant response                   | ``code_cells``, ``repr_content()``,      |
|                |                                      | ``repr_markdown()``                      |
+----------------+--------------------------------------+------------------------------------------+
| ``Code``       | Python code                          | ``code_cells``, ``repr_markdown()``      |
+----------------+--------------------------------------+------------------------------------------+
| ``CodeOutput`` | Code execution output                | ``repr_markdown()``                      |
+----------------+--------------------------------------+------------------------------------------+
| ``Image``      | Base64-encoded image                 | ``repr_markdown()``, ``save_to_file()``  |
+----------------+--------------------------------------+------------------------------------------+
| ``ServerError``| Server error message                 | ``repr_content()``, ``repr_markdown()``  |
+----------------+--------------------------------------+------------------------------------------+
| ``OpenAIError``| OpenAI error message                 | ``repr_content()``, ``repr_markdown()``  |
+----------------+--------------------------------------+------------------------------------------+
| ``CodeError``  | Code execution error                 | ``repr_content()``, ``repr_markdown()``  |
+----------------+--------------------------------------+------------------------------------------+
| ``StreamEnd``  | Stream completion marker             | ``repr_markdown()``                      |
+----------------+--------------------------------------+------------------------------------------+
| ``ServerHint`` | Backend hint data (e.g., heartbeats) | ``repr_markdown()``                      |
+----------------+--------------------------------------+------------------------------------------+


Asynchronous Client
-------------------

The ``AsyncClimateClaw`` class provides the same functionality as ``ClimateClaw`` but with async/await syntax.
This is useful when integrating with async frameworks like FastAPI, Quart, or any async Python application.

**Basic Async Usage:**

.. code-block:: python

    import asyncio
    from climate_claw_client.client import AsyncClimateClaw


    async def main():
        # Initialize the async client
        cc = AsyncClimateClaw(
            base_url="https://your-climate-claw-backend.com",
            token_store_path="~/.cache/climate-claw-client/token-store.json",
        )

        # Authenticate
        await cc.authenticate()

        # List available models
        models = cc.available_models
        print(f"Available models: {models}")

        # Set a default model
        cc.model = "gpt-4.1"

        # Create a new thread
        thread_id = await cc.newthread()
        print(f"Created thread: {thread_id}")

        # Send a prompt
        conversation = await cc.prompt(
            "Please explain the ENSO phenomenon!",
            thread_id=thread_id,
        )
        print(conversation.repr_markdown())


    # Run the async function
    asyncio.run(main())

**Async Thread Management:**

.. code-block:: python

    async def manage_threads():
        cc = AsyncClimateClaw(base_url="https://your-climate-claw-backend.com")
        await cc.authenticate()

        # Create and work with threads
        thread_id = await cc.newthread()

        # Get thread
        conversation = await cc.getthread(thread_id=thread_id)

        # List user threads
        total, threads = await cc.getuserthreads(num_threads=10)
        print(f"Total threads: {total}")

        # Set thread topic
        await cc.setthreadtopic("ENSO analysis", thread_id=thread_id)

        # Search threads
        total_results, matching = await cc.searchthreads(query="ENSO", num_threads=5)

        # Delete thread
        await cc.deletethread(thread_id=thread_id)


    asyncio.run(manage_threads())

**Async Streaming with Context Manager:**

.. code-block:: python

    async def stream_example():
        cc = AsyncClimateClaw(base_url="https://your-climate-claw-backend.com")
        await cc.authenticate()

        # Use async context manager for streaming
        stream_conv = await cc.prompt("Please explain climate patterns in detail!", stream=True)

        async with stream_conv as stream:
            async for markdown_chunk in stream.aiter_for_markdown():
                # Process each chunk as it arrives
                print(markdown_chunk, end="")

        # Get the full conversation after streaming
        full_conv = stream_conv.translate_to_conversation()


    asyncio.run(stream_example())

**Async Feedback and Thread Operations:**

.. code-block:: python

    async def advanced_operations():
        cc = AsyncClimateClaw(base_url="https://your-climate-claw-backend.com")
        await cc.authenticate()

        # Start a conversation
        conversation = await cc.prompt(
            "Show me an example of climate data analysis!", model="gpt-4.1"
        )

        # Submit feedback on assistant message
        try:
            message = await cc.userfeedback(
                feedback_index=1,
                feedback="up",
                thread_id=cc.thread_id,
            )
            print(f"Feedback submitted: {message}")
        except (IndexError, ValueError) as e:
            print(f"Feedback error: {e}")

        # Stop a streaming conversation
        await cc.stop(thread_id=cc.thread_id)

        # Fork a thread at a specific message
        try:
            new_thread_id, history = await cc.editthread(
                user_index=2,
                source_thread_id=cc.thread_id,
            )
            print(f"Forked thread: {new_thread_id}")
        except (IndexError, ValueError) as e:
            print(f"Edit error: {e}")


    asyncio.run(advanced_operations())

**Using Async Context Manager for Client Lifecycle:**

.. code-block:: python

    import asyncio
    from climate_claw_client.client import AsyncClimateClaw


    async def main():
        # Create client with custom async HTTP client
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            cc = AsyncClimateClaw(
                base_url="https://your-climate-claw-backend.com",
                http_client=http_client,
            )

            # Use the client...
            conversation = await cc.prompt("Hello ClimateClaw!", model="gpt-4.1")
            print(conversation)

            # Client uses the provided http_client
            # which will be properly closed when exiting the context


    asyncio.run(main())

**Note:** The ``AsyncClimateClaw`` class uses ``httpx.AsyncClient`` under the hood and provides all the same methods
as the synchronous ``ClimateClaw`` client. All methods that perform I/O operations are coroutines and must be awaited.
