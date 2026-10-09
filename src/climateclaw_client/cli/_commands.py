"""Commands understood by the interactive shell."""

from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple

import httpx
from rich import print as pprint
from rich.markup import escape
from rich.table import Table

from .._constants import CLIMATECLAW_API_ENDPOINTS
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


KNOWN_TOPICS: Dict[str, str] = {}
"""Topics of the threads seen in listings, by thread id."""
PENDING_TOPICS: Dict[str, str] = {}
"""Topics of new threads, set once the thread is stored with its first prompt."""


def new_thread(client: ClimateClaw, arg: str) -> None:
    """Start a new conversation thread, optionally with a topic."""
    try:
        thread_id = client.newthread()
    except REQUEST_ERRORS as error:
        logger.error("Could not start a new thread: %s", error)
        return
    if arg:
        PENDING_TOPICS[thread_id] = arg
        pprint(f"[b]New thread:[/b] {escape(arg)} ({thread_id})")
    else:
        pprint(f"[b]New thread:[/b] {thread_id}")


def apply_topic(client: ClimateClaw) -> None:
    """Set the pending topic of the active thread."""
    thread_id = client.thread_id
    if not thread_id or thread_id not in PENDING_TOPICS:
        return
    try:
        client.setthreadtopic(PENDING_TOPICS[thread_id], thread_id=thread_id)
    except REQUEST_ERRORS as error:
        logger.warning("Could not set the thread topic: %s", error)
        return
    del PENDING_TOPICS[thread_id]


def format_date(value: str, now: datetime | None = None) -> str:
    """Format an ISO date like a chat app, relative to ``now``.

    Recent dates show the day and time, older ones only the date. Dates
    with a timezone are shown in local time, unparseable ones unchanged.
    """
    try:
        date = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    if date.tzinfo is not None:
        date = date.astimezone().replace(tzinfo=None)
    now = now or datetime.now()
    days = (now.date() - date.date()).days
    time = date.strftime("%H:%M")
    if days == 0:
        return f"Today {time}"
    if days == 1:
        return f"Yesterday {time}"
    if 1 < days < 7:
        return f"{date:%a} {time}"
    if date.year == now.year:
        return f"{date.day} {date:%b} {time}"
    return f"{date.day} {date:%b %Y}"


def _threads_table(threads: List[Dict[str, Any]], current: str | None) -> Table:
    table = Table(box=None, header_style="bold", pad_edge=False)
    for column in ("", "Date", "Topic", "Thread id"):
        table.add_column(column)
    for thread in threads:
        thread_id = str(thread.get("thread_id", ""))
        table.add_row(
            "*" if thread_id == current else "",
            format_date(str(thread.get("date", ""))),
            escape(str(thread.get("topic", ""))),
            thread_id,
        )
    return table


def _remember_topics(threads: List[Dict[str, Any]]) -> None:
    for thread in threads:
        if thread.get("thread_id"):
            KNOWN_TOPICS[str(thread["thread_id"])] = str(thread.get("topic", ""))


def list_threads(client: ClimateClaw, arg: str) -> None:
    """List your threads, or search them by topic."""
    try:
        if arg:
            total, threads = client.searchthreads(arg)
        else:
            total, threads = client.getuserthreads()
    except (*REQUEST_ERRORS, ValueError) as error:
        logger.error("Could not get threads: %s", error)
        return
    if not threads:
        pprint(f"[yellow]No threads found{f' for {escape(arg)!r}' if arg else ''}.[/yellow]")
        return
    _remember_topics(threads)
    pprint(_threads_table(threads, client.thread_id))
    pprint(f"[dim]Showing {len(threads)} of {total} threads, * marks the active one.[/dim]")


DELETE_FORCE = "--force"
DELETE_LOOKUP = 100
"""Number of recent threads fetched to find the topics of unknown threads."""


def _topics(client: ClimateClaw, thread_ids: List[str]) -> Dict[str, str]:
    """Get the topics of threads, fetching the recent threads if needed."""
    if any(t not in KNOWN_TOPICS and t not in PENDING_TOPICS for t in thread_ids):
        try:
            _remember_topics(client.getuserthreads(DELETE_LOOKUP)[1])
        except (*REQUEST_ERRORS, ValueError) as error:
            logger.debug("Could not look up thread topics: %s", error)
    return {t: KNOWN_TOPICS.get(t) or PENDING_TOPICS.get(t) or "unknown topic" for t in thread_ids}


def confirm(question: str) -> bool:
    """Ask a yes/no question, no is the default."""
    return input(question).strip().lower() in ("y", "yes")


def delete_threads(client: ClimateClaw, arg: str) -> None:
    """Delete threads, by default the active one."""
    words = arg.split()
    force = DELETE_FORCE in words
    thread_ids = list(dict.fromkeys(w for w in words if w != DELETE_FORCE))
    if not thread_ids:
        if not client.thread_id:
            pprint("[yellow]No active thread, pass the ids of the threads to delete.[/yellow]")
            return
        thread_ids = [client.thread_id]
    topics = _topics(client, thread_ids)
    for thread_id in thread_ids:
        label = f"{escape(topics[thread_id])!r} ({thread_id})"
        if not force:
            try:
                if not confirm(f"Delete thread {topics[thread_id]!r} ({thread_id})? [y/N] "):
                    pprint(f"[dim]Kept {label}.[/dim]")
                    continue
            except (EOFError, KeyboardInterrupt):
                print()
                pprint("[yellow]Cancelled.[/yellow]")
                return
        try:
            client.deletethread(thread_id)
        except REQUEST_ERRORS as error:
            logger.error("Could not delete thread %s: %s", thread_id, error)
            continue
        KNOWN_TOPICS.pop(thread_id, None)
        PENDING_TOPICS.pop(thread_id, None)
        pprint(f"[green]Deleted {label}.[/green]")


SlashCommand = Callable[[ClimateClaw, str], None]

SLASH_COMMANDS: Dict[str, Tuple[str, SlashCommand]] = {
    "model": ("[name]", switch_model),
    "new": ("[topic]", new_thread),
    "threads": ("[query]", list_threads),
    "delete": (f"[{DELETE_FORCE}] [thread-id ...]", delete_threads),
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
    return "\n".join(["[b]Usage[/b]", ""] + lines + [""])


SHELL_ENDPOINTS = {
    "streamresponse",
    "stop",
    "newthread",
    "availablechatbots",
    "getuserthreads",
    "searchthreads",
    "setthreadtopic",
    "deletethread",
    "help",
    "ping",
}
"""Server endpoints the shell uses, they are covered by :func:`usage`."""


def _endpoint(name: str) -> str:
    """Get the endpoint name of a help entry, e.g. ``/api/chatbot/stop``."""
    return name.strip().strip("/").rsplit("/", 1)[-1].lower()


def split_help(payload: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Split the server help into general information and future features.

    Entries for endpoints the shell uses are dropped, :func:`usage`
    describes them. Entries for other endpoints are features the shell
    does not offer yet. Everything else is general information.
    """
    known = set(CLIMATECLAW_API_ENDPOINTS.values())
    info: Dict[str, str] = {}
    future: Dict[str, str] = {}
    for name, text in payload.items():
        endpoint = _endpoint(name)
        if endpoint in SHELL_ENDPOINTS:
            continue
        (future if endpoint in known else info)[name] = str(text)
    return info, future


def _section(title: str, entries: Dict[str, str]) -> str:
    lines = [f"  [b]{escape(name)}[/b]: {escape(text)}" for name, text in entries.items()]
    return "\n".join([f"[b]{title}[/b]", ""] + lines + [""])


def show_intro(client: ClimateClaw) -> None:
    """Show how to use the shell and what the server offers beyond that."""
    res = client.get(client._construct_path("help"))
    assert isinstance(res, httpx.Response)
    info, future = split_help(dict(res.json()))
    if info:
        pprint(_section("About", info))
    pprint(usage())
    if future:
        pprint(_section("Not available in the shell yet", future))
    bots = client.available_models
    client.model = client.model or (bots[0] if bots else None)  # type: ignore[assignment]
    pprint(f"[b]Available models:[/b] {', '.join(bots)}")
    pprint(f"[b]Using:[/b] {client.model}")


def handle(line: str, client: ClimateClaw) -> None:
    """Dispatch a line to the chatbot or a shell command."""
    if line.startswith(SLASH_PREFIX):
        run_slash_command(client, line)
    else:
        ask(client, line)
        apply_topic(client)
