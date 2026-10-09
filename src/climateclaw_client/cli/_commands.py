"""Commands understood by the interactive shell."""

from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple

import httpx
from rich import print as pprint
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .._constants import CLIMATECLAW_API_ENDPOINTS
from ..client import ClimateClaw
from ..models import Conversation
from ._chat import REQUEST_ERRORS, ask, show_history
from ._log import logger

EXIT_COMMANDS = ("exit", "quit")
HELP_COMMANDS = ("u", "usage", "h", "help")
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


def open_topic(client: ClimateClaw, topic: str) -> None:
    """Continue the thread with this topic, or start a new one with it."""
    try:
        _, threads = client.searchthreads(topic)
    except (*REQUEST_ERRORS, ValueError) as error:
        logger.error("Could not search threads: %s", error)
        threads = []
    wanted = topic.strip().casefold()
    match = next(
        (t for t in threads if str(t.get("topic", "")).strip().casefold() == wanted),
        None,
    )
    if match is None:
        new_thread(client, topic)
        return
    client.thread_id = str(match["thread_id"])
    _remember_topics([match])
    pprint(f"[b]Thread:[/b] {escape(str(match.get('topic', '')))} ({client.thread_id})")
    content = match.get("content")
    if isinstance(content, Conversation):
        show_history(content)


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
        pprint(usage_panel())
        return
    SLASH_COMMANDS[name][1](client, arg.strip())


def usage_rows() -> List[Tuple[str, str]]:
    """Describe how to use the shell, as pairs of input and description."""
    rows: List[Tuple[str, str]] = [("<question>", "Ask the chatbot.")]
    for name, (args, func) in SLASH_COMMANDS.items():
        call = f"{SLASH_PREFIX}{name} {args}".strip()
        rows.append((call, (func.__doc__ or "").strip()))
    return rows + [
        (" | ".join(EXIT_COMMANDS), "Leave the session."),
        (" | ".join(HELP_COMMANDS), "Show this usage."),
        (f"... {CONTINUATION}", "Continue the input on the next line."),
        ("Ctrl+C", "Stop the current answer."),
        ("Tab", "Complete commands and model names."),
    ]


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
"""Server endpoints the shell uses, they are covered by :func:`usage_rows`."""


def _endpoint(name: str) -> str:
    """Get the endpoint name of a help entry, e.g. ``/api/chatbot/stop``."""
    return name.strip().strip("/").rsplit("/", 1)[-1].lower()


def split_help(payload: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Split the server help into general information and future features.

    Entries for endpoints the shell uses are dropped, :func:`usage_rows`
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


def _panel(title: str, rows: List[Tuple[str, str]], style: str, key_style: str) -> Panel:
    """Frame a part of the usage like code, output and errors."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=key_style, no_wrap=True)
    grid.add_column()
    for key, text in rows:
        grid.add_row(Text(key), Text(text))
    return Panel(grid, title=title, title_align="left", border_style=style)


def usage_panel() -> Panel:
    """Show how to use the shell in a panel."""
    return _panel("Usage", usage_rows(), "cyan", "cyan")


def _section(title: str, entries: Dict[str, str], style: str) -> Panel:
    return _panel(title, list(entries.items()), style, "bold")


def choose_model(client: ClimateClaw) -> None:
    """Use the first available model unless one was given."""
    bots = client.available_models
    client.model = client.model or (bots[0] if bots else None)  # type: ignore[assignment]


def show_models(client: ClimateClaw) -> None:
    """Choose the model and show which ones are available."""
    choose_model(client)
    pprint(f"[b]Available models:[/b] {', '.join(client.available_models)}")
    pprint(f"[b]Using:[/b] {client.model}")


def usage(client: ClimateClaw, arg: str = "") -> None:
    """Show how to use the shell."""
    try:
        res = client.get(client._construct_path("help"))
        assert isinstance(res, httpx.Response)
        info, future = split_help(dict(res.json()))
    except (*REQUEST_ERRORS, ValueError) as error:
        logger.debug("Could not get the server help: %s", error)
        info, future = {}, {}
    if info:
        pprint(_section("About", info, "magenta"))
    pprint(usage_panel())
    if future:
        pprint(_section("Not available in the shell yet", future, "yellow"))


def handle(line: str, client: ClimateClaw) -> None:
    """Dispatch a line to the chatbot or a shell command."""
    if line.removeprefix(SLASH_PREFIX) in HELP_COMMANDS:
        usage(client)
    elif line.startswith(SLASH_PREFIX):
        run_slash_command(client, line)
    else:
        ask(client, line)
        apply_topic(client)
