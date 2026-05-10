FrevaGPT Client Documentation
================================

A Python client library for interacting with the `FrevaGPT backend <https://github.com/freva-org/freva-gpt-backend-py>`_.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   usage
   api/index


Quickstart
----------

Install the package from source:

.. code-block:: bash

   git clone https://github.com/freva-org/freva-gpt-client.git
   cd freva-gpt-client
   pip install -e .

Or using ``uv``:

.. code-block:: bash

   uv pip install -e .


Basic Usage Example
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from freva_gpt_client.client import FrevaGPT

   # Create a client instance
   client = FrevaGPT(
       base_url="https://your-freva-gpt-backend.com",
       token_store_path="~/.cache/freva-gpt-client/token-store.json"
   )

   # Authenticate with the backend
   client.authenticate()

   # List available models
   print(f"Available models: {client.available_models}")

   # Send a prompt
   conversation = client.prompt("Please calculate the average temperature over Germany for 1990-2020!")

   # Access messages
   for message in conversation.messages:
       print(f"{message.variant}: {message.content}")


Streaming Example
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Send a prompt with streaming enabled
   stream_conv = client.prompt(
       "Please explain the ENSO phenomenon to me!",
       stream=True
   )

   # Iterate over markdown chunks as they arrive
   with stream_conv as stream:
       for markdown_chunk in stream.iter_for_markdown():
           print(markdown_chunk)


Thread Management Example
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Create a new conversation thread
   thread_id = client.newthread()

   # Continue a conversation in an existing thread
   response = client.prompt(
       "Please explain how the SOI can be calculated.",
       thread_id=thread_id
   )


Features
--------

- **Synchronous client** with full API support
- **OIDC authentication** via `py-oidc-auth-client <https://pypi.org/project/py-oidc-auth-client/>`_
- **Thread management**: create, retrieve, interact with conversation threads
- **Streaming and non-streaming** prompt responses
- **Rich message types** with markdown rendering support
- **Message variants**: Prompt, User, Assistant, Code, CodeOutput, Image, ServerError, OpenAIError, CodeError, StreamEnd, ServerHint


Project Links
-------------

- **Source Code**: https://github.com/freva-org/freva-gpt-client
- **Backend Repository**: https://github.com/freva-org/freva-gpt-backend-py
- **Issue Tracker**: https://github.com/freva-org/freva-gpt-client/issues
- **License**: European Union Public Licence 1.2 (EUPL-1.2)


Indices and Tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
