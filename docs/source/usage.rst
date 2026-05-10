Usage Guide
============

This guide covers how to use the FrevaGPT Client library, including initialization, configuration, and common use cases.


Initialization
--------------

The ``FrevaGPT`` client is the main entry point for interacting with the FrevaGPT backend.

.. code-block:: python

   from freva_gpt_client.client import FrevaGPT

   client = FrevaGPT(
       base_url="https://your-freva-gpt-backend.com",
       token_store_path="~/.cache/freva-gpt-client/token-store.json",
       follow_redirects=True,
       timeout=30.0,
       max_retries=3
   )


Configuration Options
----------------------

The client accepts the following configuration parameters:

+----------------------+--------------+---------------------+----------------------------------------------------------+
| Parameter            | Type         | Default             | Description                                              |
+======================+==============+=====================+==========================================================+
| ``base_url``         | str/URL      | **Required**        | Base URL of the FrevaGPT backend                         |
+----------------------+--------------+---------------------+----------------------------------------------------------+
| ``token_store_path`` | str          | ``""``              | Path to store OIDC tokens                                |
+----------------------+--------------+---------------------+----------------------------------------------------------+
| ``follow_redirects`` | bool         | ``True``            | Whether to follow HTTP redirects                         |
+----------------------+--------------+---------------------+----------------------------------------------------------+
| ``timeout``          | float        | ``30.0``            | Request timeout in seconds                               |
+----------------------+--------------+---------------------+----------------------------------------------------------+
| ``max_retries``      | int          | ``3``               | Maximum retry attempts for failed requests               |
+----------------------+--------------+---------------------+----------------------------------------------------------+
| ``http_client``      | httpx.Client | ``None``            | Pre-configured HTTP client (optional)                    |
+----------------------+--------------+---------------------+----------------------------------------------------------+
| ``thread_id``        | str          | ``None``            | Default thread ID for conversations                      |
+----------------------+--------------+---------------------+----------------------------------------------------------+
| ``model``            | str          | ``None``            | Default model for prompts                                |
+----------------------+--------------+---------------------+----------------------------------------------------------+


Authentication
--------------

The client uses OIDC authentication. Call ``authenticate()`` to trigger the authentication flow:

.. code-block:: python

   client.authenticate()

This will open a browser window for authentication and store the tokens in the configured ``token_store_path``.


Working with Models
-------------------

.. code-block:: python

   # List available chatbot models
   models = client.available_models
   print(f"Available models: {models}")

   # Set a default model for the client
   client.model = "gpt-4.1"

   # Or specify model per request
   conversation = client.prompt("Hello!", model="gpt-4.1")


Sending Prompts
---------------

**Non-streamed Response:**

.. code-block:: python

   conversation = client.prompt("Please calculate the average temperature over Germany!")

   # Access the conversation messages
   for message in conversation.messages:
       print(f"{message.variant}: {message.content}")

   # Get markdown representation
   markdown = conversation.repr_markdown()
   print(markdown)


**Streamed Response:**

.. code-block:: python

   stream_conv = client.prompt(
       "Please explain the ENSO phenomenon to me!",
       stream=True
   )

   with stream_conv as stream:
       for markdown_chunk in stream.iter_for_markdown():
           print(markdown_chunk)

   # After streaming completes, access the full conversation
   full_conversation = stream_conv.translate_to_conversation()
   print(full_conversation.repr_markdown())


Thread Management
-----------------

**Create a New Thread:**

.. code-block:: python

   thread_id = client.newthread()
   print(f"New thread ID: {thread_id}")


**Get a Thread:**

.. code-block:: python

   # Retrieve an existing thread by ID
   thread_id = "your-thread-id"
   conversation = client.getthread(thread_id=thread_id)

   # Or use the current active thread
   conversation = client.getthread()

   # Print all messages
   print(conversation)


**Prompt in a Specific Thread:**

.. code-block:: python

   response = client.prompt(
       "Please explain how the SOI can be calculated.",
       thread_id=thread_id  # optional: uses thread of active conversation otherwise
   )


Working with Message Types
--------------------------

The client provides rich message types that can be rendered in different formats:

.. code-block:: python

   conversation = client.prompt("Show me a code example of using xarray!")

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

       # Save to file
       image_message.save_to_file("output.png")


Raw Message Access
------------------

.. code-block:: python

   conversation = client.prompt("Hello FrevaGPT!")

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


Asynchronous Client (Coming Soon)
---------------------------------

The library includes an ``AsyncFrevaGPT`` class for async operations:

.. code-block:: python

   from freva_gpt_client.client import AsyncFrevaGPT

   async def main():
       client = AsyncFrevaGPT(base_url="https://your-freva-gpt-backend.com")
       await client.authenticate()
       # Async methods will be available in future versions

   # Note: Async methods are not yet fully implemented
