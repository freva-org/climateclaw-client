ClimateClaw Client Documentation
================================

A Python client library for interacting with the `ClimateClaw backend <https://github.com/freva-org/freva-gpt-backend-py>`_.
This library provides both synchronous and asynchronous interfaces for communicating with a ClimateClaw chatbot instance.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   usage
   api/index


Quickstart
----------

Install the package from source:

.. code-block:: bash

   git clone https://github.com/freva-org/climate-claw-client.git
   cd climate-claw-client
   pip install -e .

Or using ``uv``:

.. code-block:: bash

   uv pip install -e .


Basic Usage Example
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from climate_claw_client.client import ClimateClaw

    # Create a client instance
    client = ClimateClaw(
        base_url="https://your-climate-claw-backend.com",
        token_store_path="~/.cache/climate-claw-client/token-store.json",
    )

    # Authenticate with the backend
    client.authenticate()

    # List available models
    print(f"Available models: {client.available_models}")

    # Send a prompt
    conversation = client.prompt(
        "Please calculate the average temperature over Germany for 1990-2020!"
    )

    # Access messages
    for message in conversation.messages:
        print(f"{message.variant}: {message.content}")


Streaming Example
~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Send a prompt with streaming enabled
    stream_conv = client.prompt("Please explain the ENSO phenomenon to me!", stream=True)

    # Iterate over markdown chunks as they arrive
    with stream_conv as stream:
        for markdown_chunk in stream.iter_for_markdown():
            print(markdown_chunk)


Asynchronous Client Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import asyncio
    from climate_claw_client.client import AsyncClimateClaw


    async def main():
        # Create an async client instance
        client = AsyncClimateClaw(
            base_url="https://your-climate-claw-backend.com",
            token_store_path="~/.cache/climate-claw-client/token-store.json",
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

        # Thread management works the same way
        thread_id = await client.newthread()
        response = await client.prompt(
            "Please explain how the SOI can be calculated.",
            thread_id=thread_id,
        )


    asyncio.run(main())


Thread Management Example
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Create a new conversation thread
    thread_id = client.newthread()

    # Continue a conversation in an existing thread
    response = client.prompt("Please explain how the SOI can be calculated.", thread_id=thread_id)

    # List all your conversation threads
    total_threads, user_threads = client.getuserthreads(num_threads=10)
    print(f"A total number of {total_threads} threads was retrieved.")
    # access individual threads (which are Conversation objects)
    print(user_threads[0])

    # Search for threads by topic
    total_results, matching_threads = client.searchthreads(query="climate analysis", num_threads=5)

    # Set a topic for a thread (useful for searching later)
    client.setthreadtopic("ENSO analysis", thread_id=thread_id)

    # Delete a thread when you're done with it
    client.deletethread(thread_id=thread_id)


Features
--------

- **Synchronous client** (`ClimateClaw`) with full API support
- **Asynchronous client** (`AsyncClimateClaw`) with full API support
- **OIDC authentication** via `py-oidc-auth-client <https://pypi.org/project/py-oidc-auth-client/>`_
- **Thread management**: create, retrieve, list, search, fork, and delete conversation threads
- **Streaming and non-streaming** prompt responses
- **Thread operations**: stop active conversations, set thread topics, edit/fork threads
- **User feedback**: submit positive/negative feedback on assistant messages
- **Rich message types** with markdown rendering support
- **Message variants**: Prompt, User, Assistant, Code, CodeOutput, Image, ServerError, OpenAIError, CodeError, StreamEnd, ServerHint


Project Links
-------------

- **Source Code**: https://github.com/freva-org/climate-claw-client
- **Backend Repository**: https://github.com/freva-org/freva-gpt-backend-py
- **Issue Tracker**: https://github.com/freva-org/climate-claw-client/issues
- **License**: European Union Public Licence 1.2 (EUPL-1.2)


Indices and Tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
