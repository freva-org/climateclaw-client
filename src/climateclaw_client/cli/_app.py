"""The ``climateclaw-shell`` command line interface."""

import logging
from typing import Any, Optional

import typer
from rich import print as pprint

from .._auth import TokenAuth
from .._version import get_versions
from ..client import ClimateClaw
from ._chat import REQUEST_ERRORS, revoke, show_intro
from ._commands import EXIT_COMMANDS, handle, read_input, usage
from ._completion import setup as setup_completion
from ._log import logger, resolve_level, set_level

CHATBOT_PATH = ClimateClaw._root_api_path


def check_level(value: Optional[str]) -> Optional[str]:
    """Validate the ``--log`` option."""
    try:
        resolve_level(value)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    return value


def version_callback(value: bool) -> None:
    """Show the version and exit."""
    if value:
        pprint(f"climateclaw-shell {get_versions()['version']}")
        raise typer.Exit()


def chatbot_base_url(url: str) -> str:
    """Strip the chatbot api path, the client adds it to every request."""
    url = url.rstrip("/")
    return url[: -len(CHATBOT_PATH)] if url.endswith(CHATBOT_PATH) else url


class ShellClient(ClimateClaw):
    """A client that authenticates with a given :class:`TokenAuth`.

    The client already sends requests while it is created, the token
    handling has to be set up before that.
    """

    def __init__(self, *, auth: TokenAuth, **kwargs: Any) -> None:
        self._auth = auth  # type: ignore[misc]
        super().__init__(auth_url=auth.base_url, **kwargs)


def connect(auth: TokenAuth, chatbot_url: Optional[str], model: Optional[str]) -> ClimateClaw:
    """Connect to the chatbot, authenticating against the freva instance."""
    return ShellClient(
        auth=auth,
        base_url=chatbot_base_url(chatbot_url or str(auth.base_url)),
        model=model,
        custom_headers={"x-freva-rest-url": f"{auth.base_url}/api/freva-nextgen"},
    )


def run(client: ClimateClaw) -> None:
    """Read prompts and commands until the user leaves."""
    pprint(usage())
    show_intro(client)
    prompt = setup_completion(client)
    while True:
        try:
            line = read_input(prompt)
        except EOFError:
            break
        except KeyboardInterrupt:
            print()
            continue
        if line in EXIT_COMMANDS:
            break
        if line:
            handle(line, client)


def chat(
    freva_instance: str = typer.Option(
        ...,
        "--freva-instance",
        envvar="FREVA_INSTANCE",
        help="Url of the freva instance to log in to, e.g. https://www.freva.dkrz.de",
    ),
    chatbot_url: Optional[str] = typer.Option(
        None,
        "--chatbot-url",
        envvar="CLIMATECLAW_URL",
        help=(
            "Url of the climateclaw chatbot, e.g. "
            "http://chatbot.example.org:8505/api/chatbot. "
            "Defaults to <freva-instance>/api/chatbot."
        ),
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Chatbot model to use, defaults to the first available.",
    ),
    timeout: int = typer.Option(
        30,
        "--timeout",
        help="Set the timeout for login in seconds, 0 for indefinite",
    ),
    keep_token: bool = typer.Option(
        False,
        "--keep-token",
        help=(
            "Do not revoke the token on exit. The next launch reuses it, "
            "refreshes it or asks for a new login if both expired."
        ),
    ),
    force_login: bool = typer.Option(
        False,
        "--force-login",
        help="Ignore a stored token and always ask for a new login.",
    ),
    log: Optional[str] = typer.Option(
        None,
        "--log",
        help="Set the log level: trace, debug, info, warning, error or a number.",
        callback=check_level,
    ),
    debug: bool = typer.Option(False, "--debug", help="Log debug messages."),
    trace: bool = typer.Option(
        False, "--trace", help="Most verbose logging, including http traffic."
    ),
    verbose: int = typer.Option(
        0, "-v", help="Increase verbosity: -v debug, -vv trace.", count=True
    ),
    version: Optional[bool] = typer.Option(
        False,
        "-V",
        "--version",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Start an interactive, authenticated climateclaw chat session."""
    set_level(resolve_level(log, verbose, debug, trace))
    # Logging in, refreshing and storing the token is left to the client,
    # it does so whenever a request is rejected with 401.
    auth = TokenAuth(
        base_url=ClimateClaw._validate_base_url(freva_instance),
        timeout=timeout or None,  # type: ignore[arg-type]
    )
    if force_login:
        revoke(auth)
    try:
        try:
            client = connect(auth, chatbot_url, model)
        except (*REQUEST_ERRORS, KeyError, ValueError) as error:
            logger.critical(
                "No usable chatbot found: %s", error, exc_info=logger.isEnabledFor(logging.DEBUG)
            )
            raise typer.Exit(1) from error
        run(client)
    except REQUEST_ERRORS as error:
        logger.critical("%s", error, exc_info=logger.isEnabledFor(logging.DEBUG))
        raise typer.Exit(1) from error
    finally:
        if not keep_token:
            revoke(auth)


app = typer.Typer(name="climateclaw-shell", add_completion=False)
app.command(help=chat.__doc__)(chat)
