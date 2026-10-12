Interactive Shell
=================

``climateclaw-shell`` is an interactive chat session in the terminal. It is installed with the
optional ``cli`` extra:

.. code-block:: console

    pip install "climateclaw-client[cli]"
    climateclaw-shell --freva-instance https://www.freva.dkrz.de
    climateclaw (gpt-4.1-mini)> what is the warmest cmip6 model?
    climateclaw (gpt-4.1-mini)> exit

The prompt shows the model in use. To ask a single question without the interactive session,
pass it with ``-p``; the answer is printed and the shell exits:

.. code-block:: console

    climateclaw-shell -p "what is the warmest cmip6 model?"
    climateclaw-shell --topic "ENSO" -p "/threads"


Authentication
--------------

The shell uses the same OIDC token handling as the client: a stored token is reused, refreshed
when it expired, and you are asked to log in only if the refresh token expired as well.

On exit the token is revoked, unless ``--keep-token`` is given. ``--force-login`` ignores a
stored token and always asks for a new login.


Connecting
----------

By default the chatbot is expected at ``<freva-instance>/api/chatbot``. Use ``--chatbot-url``
(or the ``CLIMATECLAW_URL`` environment variable) for a chatbot on another host. ``--model``
chooses a model; without it, the first available one is used.


Commands
--------

==============================  =================================================
Input                           Effect
==============================  =================================================
``<question>``                  Ask the chatbot, the answer is streamed back.
``/model [name]``               Switch to another model, or show the current one.
``/new [topic]``                Start a new thread, optionally with a topic.
``/threads``                    List your most recent threads.
``/threads <query>``            Search your threads by topic.
``/delete [--force] [id ...]``  Delete threads, by default the active one.
``exit``, ``quit``              Leave the shell.
``help``, ``usage``, ``h``,     Show the usage, also with a leading ``/``.
``u``
Ctrl+C while streaming          Stop the current answer.
``\`` at the end of a line      Continue the input on the next line.
Tab                             Complete commands and model names.
==============================  =================================================

``/new <topic>`` takes a topic, not a thread id: the shell creates a new thread and names it
``<topic>`` once the first question is sent, since only then is the thread stored. The topic can
contain spaces, e.g. ``/new El Nino in CMIP6``, and is what ``/threads <query>`` searches.

``/threads`` shows up to 20 threads with their date, topic and id; the active thread is marked
with ``*``. Everything after ``/threads`` is sent as one search query, so ``/threads el nino``
searches for "el nino".

``/delete`` asks for confirmation for each thread unless ``--force`` is given.

The usage is shown on ``help`` and on an unknown command, together with information from the
server and the server features the shell does not offer yet, such as giving feedback. These are
available through the Python client, see :doc:`usage`.


Topics
------

``--topic <topic>`` (``-t``) opens a thread by its topic when the shell starts. If one of your
threads has exactly this topic (ignoring case), it is continued and its history is shown;
otherwise a new thread with this topic is started.


Options
-------

=====================  ================================================================
Option                 Description
=====================  ================================================================
``--freva-instance``   Url of the freva instance to log in to (``FREVA_INSTANCE``).
``--chatbot-url``      Url of the chatbot (``CLIMATECLAW_URL``), defaults to
                       ``<freva-instance>/api/chatbot``.
``--model``            Chatbot model, defaults to the first available.
``--timeout``          Login timeout in seconds, ``0`` for indefinite.
``--keep-token``       Keep the token on exit.
``--force-login``      Ignore a stored token and always log in again.
``-p``, ``--prompt``   Send a single prompt or command, print the answer and exit
                       (also ``-c``, ``--command``).
``-t``, ``--topic``    Continue the thread with this topic, or start a new one.
``--log <level>``      Log level: ``trace``, ``debug``, ``info``, ``warning``, ``error``
                       or a number.
``--debug``            Log debug messages, including tracebacks of errors.
``--trace``            Most verbose, including http traffic.
``-v``, ``-vv``        Increase verbosity: ``-v`` debug, ``-vv`` trace.
``-V``, ``--version``  Show the version and exit.
=====================  ================================================================
