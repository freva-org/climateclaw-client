"""Send prompts to the chatbot and render the streamed answers."""

import base64
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import httpx
from py_oidc_auth_client import AuthError  # type: ignore
from rich import print as pprint
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.text import Text

from .._auth import TokenAuth
from ..client import ClimateClaw
from ..models import Conversation, StreamConversation
from ._log import logger

WAITING = "[dim]Waiting for the answer, press Ctrl+C to cancel...[/dim]"
STDERR_LINES = 3
REQUEST_ERRORS = (ConnectionError, httpx.HTTPError, AuthError)
"""Errors of a failed request that should not end the shell."""


LATEX_SYMBOLS = {
    "rightarrow": "→",
    "to": "→",
    "leftarrow": "←",
    "gets": "←",
    "Rightarrow": "⇒",
    "Leftarrow": "⇐",
    "leftrightarrow": "↔",
    "Leftrightarrow": "⇔",
    "uparrow": "↑",
    "downarrow": "↓",
    "times": "×",
    "cdot": "·",
    "div": "÷",
    "pm": "±",
    "mp": "∓",
    "approx": "≈",
    "sim": "∼",
    "neq": "≠",
    "ne": "≠",
    "leq": "≤",
    "le": "≤",
    "geq": "≥",
    "ge": "≥",
    "ll": "≪",
    "gg": "≫",
    "propto": "∝",
    "infty": "∞",
    "partial": "∂",
    "nabla": "∇",
    "sum": "∑",
    "prod": "∏",
    "int": "∫",
    "sqrt": "√",
    "circ": "°",
    "degree": "°",
    "in": "∈",
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "Delta": "Δ",
    "epsilon": "ε",
    "theta": "θ",
    "lambda": "λ",
    "mu": "μ",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "Sigma": "Σ",
    "tau": "τ",
    "phi": "φ",
    "omega": "ω",
    "Omega": "Ω",
}
_LATEX_INLINE = re.compile(r"\$([^$\n]*\\[A-Za-z][^$\n]*)\$")
_LATEX_COMMAND = re.compile(r"\\([A-Za-z]+)")


def _latex_to_text(markdown: str) -> str:
    """Replace simple inline LaTeX like ``$\\rightarrow$`` by Unicode.

    Formulas with commands that have no Unicode equivalent are left as is.
    """

    def replace(match: "re.Match[str]") -> str:
        formula = _LATEX_COMMAND.sub(
            lambda cmd: LATEX_SYMBOLS.get(cmd.group(1), cmd.group(0)),
            match.group(1),
        )
        if "\\" in formula:
            return match.group(0)
        return formula.replace("{", "").replace("}", "").strip()

    return _LATEX_INLINE.sub(replace, markdown)


def _code_text(raw: str) -> str:
    """Get the source from a streamed ``{"code": ...}`` payload."""
    try:
        payload = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(payload, dict):
        return str(payload.get("code", raw))
    return raw


def _shorten(text: str, lines: int = STDERR_LINES) -> str:
    rows = text.rstrip().splitlines()
    if len(rows) <= lines:
        return "\n".join(rows)
    return "\n".join(rows[:lines] + [f"... ({len(rows) - lines} more lines)"])


def code_output(content: Any) -> Panel:
    """Render the result of a code execution."""
    if not isinstance(content, dict):
        return Panel(Text(str(content)), title="Output", border_style="green")
    parts: List[Any] = []
    for key in ("stdout", "result_repr"):
        if str(content.get(key) or "").strip():
            parts.append(Text(str(content[key]).rstrip()))
    for name in content.get("created_files") or []:
        parts.append(Text(f"Created file: {name}", style="cyan"))
    if str(content.get("stderr") or "").strip():
        parts.append(Text(_shorten(str(content["stderr"])), style="dim"))
    error = str(content.get("error") or "").strip()
    if error:
        parts.append(Text.from_ansi(error, style="red"))
    return Panel(
        Group(*parts) if parts else Text("(no output)", style="dim"),
        title="Error" if error else "Output",
        title_align="left",
        border_style="red" if error else "green",
    )


class Renderer:
    """Render the streamed answer of the chatbot.

    Text and code arrive in small chunks; they are collected and shown
    live, and printed for good once the next part of the answer starts.
    While the server is busy a spinner is shown.
    """

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self.live = Live(
            Spinner("dots", WAITING, style="dim"),
            console=self.console,
            transient=True,
            refresh_per_second=8,
            vertical_overflow="visible",
        )
        self.kind: str | None = None
        self.buffer = ""
        self.images: Dict[str, List[str]] = {}
        self.received = False

    def __enter__(self) -> "Renderer":
        self.live.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

    def stop(self) -> None:
        """Print what is left and stop the live display."""
        self.flush()
        self.live.stop()

    def _status(self, text: str) -> None:
        self.live.update(Spinner("dots", f"[dim]{text}[/dim]"))

    def flush(self) -> None:
        """Print the collected part of the answer for good."""
        kind, buffer = self.kind, self.buffer
        self.kind, self.buffer = None, ""
        if kind == "Assistant" and buffer.strip():
            self.live.update(Text(""))
            self.console.print(Markdown(_latex_to_text(buffer)))
        elif kind == "Code" and buffer.strip():
            self.console.print(
                Panel(
                    Syntax(_code_text(buffer).strip(), "python", word_wrap=True),
                    title="Code",
                    title_align="left",
                    border_style="blue",
                )
            )
        self._status("Working...")

    def _save_images(self) -> None:
        for image_id, chunks in self.images.items():
            path = Path(tempfile.gettempdir()) / f"climateclaw-{image_id}.png"
            try:
                data = base64.b64decode("".join(chunks), validate=True)
                path.write_bytes(data)
            except (ValueError, OSError) as error:
                logger.error("Could not save image: %s", error)
                continue
            self.console.print(f"[cyan]Image saved to {path}[/cyan]")
        self.images.clear()

    def feed(self, variant: Dict[str, Any]) -> None:
        """Render one streamed variant."""
        kind = variant.get("variant")
        content = variant.get("content", "")
        if kind in ("ServerHint", "Prompt", None):
            return
        self.received = True
        if kind != self.kind:
            self.flush()
        if kind != "Image" and self.images:
            self._save_images()
        if kind == "Assistant":
            self.kind = kind
            self.buffer += str(content)
            self.live.update(Markdown(_latex_to_text(self.buffer)))
        elif kind == "Code":
            self.kind = kind
            # A complete code chunk arrives already decoded by the stream parser.
            self.buffer += json.dumps(content) if isinstance(content, dict) else str(content)
            self._status(f"Writing code ({len(self.buffer)} characters)...")
        elif kind == "CodeOutput":
            self.console.print(code_output(content))
        elif kind == "Image":
            self.kind = kind
            self.images.setdefault(str(variant.get("id", "image")), []).append(str(content))
            self._status("Receiving image...")
        elif kind in ("ToolCall", "ToolOutput"):
            tool = variant.get("tool_name", "tool")
            verb = "Calling" if kind == "ToolCall" else "Result of"
            self.console.print(f"[dim]{verb} {tool}[/dim]")
        elif kind in ("CodeError", "ServerError", "OpenAIError"):
            self.console.print(Panel(Text(str(content)), title=kind, border_style="red"))
        elif kind == "StreamEnd":
            self._save_images()
        elif kind == "User":
            self.console.print(Text(f"> {content}", style="bold"))


def _track_thread(client: ClimateClaw, variant: Dict[str, Any]) -> None:
    """Follow a thread id the server hands out while streaming."""
    content = variant.get("content")
    if variant.get("variant") == "ServerHint" and isinstance(content, dict):
        client.thread_id = content.get("thread_id", client.thread_id)


def ask(client: ClimateClaw, text: str) -> None:
    """Send a prompt to the chatbot and render the answer.

    The answer is streamed and may take a while; Ctrl+C stops it and
    returns to the prompt.
    """
    renderer = Renderer()
    try:
        with renderer:
            stream = client.prompt(text, stream=True)
            assert isinstance(stream, StreamConversation)
            # Leaving the stream context asks the server to stop the thread.
            with stream:
                # Raw dicts: the shell also renders variants without a model.
                for variant in stream.stream_response.iter_json_objects():
                    _track_thread(client, variant)
                    renderer.feed(variant)
        if not renderer.received:
            logger.error("No answer received from %s", client.base_url)
    except KeyboardInterrupt:
        renderer.stop()
        pprint("[yellow]Stopped.[/yellow]")
    except REQUEST_ERRORS as error:
        logger.error("Chatbot request failed: %s", error)


def show_history(conversation: Conversation) -> None:
    """Render the messages of a stored thread."""
    with Renderer() as renderer:
        for message in conversation.raw_messages:
            renderer.feed(message.message.model_dump())


def revoke(auth: TokenAuth) -> None:
    """Revoke the session token by removing it from the token store.

    The token is stored under the auth url by the client and under the
    freva rest url by the login flow, both entries are removed.
    """
    hosts = (str(auth.base_url), f"{auth.base_url}/api/freva-nextgen")
    removed = [auth.token_store.remove(host) for host in hosts]
    auth.auth_token = None
    if any(removed):
        pprint("[green]Session token revoked.[/green]")
