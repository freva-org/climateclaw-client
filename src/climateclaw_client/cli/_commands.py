"""Commands understood by the interactive shell."""

from typing import Callable, Dict, List, Tuple

from rich import print as pprint
from rich.markup import escape

from ..client import ClimateClaw
from ._chat import REQUEST_ERRORS, ask
from ._log import logger

EXIT_COMMANDS = ("exit", "quit", "logout")
SLASH_PREFIX = "/"
CONTINUATION = "\\"
PROMPT = "climateclaw> "
CONTINUATION_PROMPT = "...> "
PENDING_LINES: List[str] = []
"""Lines of the current input that were continued with a backslash."""


def read_input(prompt: Callable[[str], str] | None = None) -> str:
    """Read a prompt, a trailing backslash continues on the next line."""
    prompt = prompt or input
    PENDING_LINES.clear()
    try:
        text = prompt(PROMPT)
        while text.rstrip().endswith(CONTINUATION):
            PENDING_LINES.append(text.rstrip()[: -len(CONTINUATION)])
            text = prompt(CONTINUATION_PROMPT)
        return "\n".join(PENDING_LINES + [text]).strip()
    finally:
        PENDING_LINES.clear()


def switch_model(client: ClimateClaw, arg: str) -> None:
    """Switch to another model, or show the current one."""
    try:
        client.model = arg or client.model
    except ValueError as error:
        logger.error("%s", error)
        return
    pprint(f"[b]Using:[/b] {client.model}")


def new_thread(client: ClimateClaw, arg: str) -> None:
    """Start a new conversation thread."""
    try:
        thread_id = client.newthread()
    except REQUEST_ERRORS as error:
        logger.error("Could not start a new thread: %s", error)
        return
    pprint(f"[b]New thread:[/b] {thread_id}")


SlashCommand = Callable[[ClimateClaw, str], None]

SLASH_COMMANDS: Dict[str, Tuple[str, SlashCommand]] = {
    "model": ("[name]", switch_model),
    "new": ("", new_thread),
}
"""Shell commands: name -> (argument usage, function)."""


def run_slash_command(client: ClimateClaw, line: str) -> None:
    """Run a ``/<name> [arg]`` shell command."""
    name, _, arg = line[len(SLASH_PREFIX) :].partition(" ")
    if name not in SLASH_COMMANDS:
        pprint(f"[yellow]Unknown command: {SLASH_PREFIX}{name}[/yellow]")
        return
    SLASH_COMMANDS[name][1](client, arg.strip())


def usage() -> str:
    """Describe how to use the shell as an aligned list."""
    rows: List[Tuple[str, str]] = [("<question>", "Ask the chatbot.")]
    for name, (args, func) in SLASH_COMMANDS.items():
        call = f"{SLASH_PREFIX}{name} {args}".strip()
        rows.append((call, (func.__doc__ or "").strip()))
    rows += [
        (" | ".join(EXIT_COMMANDS), "Leave the session."),
        (f"... {CONTINUATION}", "Continue the input on the next line."),
        ("Ctrl+C", "Stop the current answer."),
        ("Tab", "Complete commands and model names."),
    ]
    width = max(len(call) for call, _ in rows)
    lines = [f"  [cyan]{escape(call.ljust(width))}[/cyan]  {escape(text)}" for call, text in rows]
    return "\n".join(["[b]climateclaw chat session[/b]", ""] + lines + [""])


def handle(line: str, client: ClimateClaw) -> None:
    """Dispatch a line to the chatbot or a shell command."""
    if line.startswith(SLASH_PREFIX):
        run_slash_command(client, line)
    else:
        ask(client, line)
