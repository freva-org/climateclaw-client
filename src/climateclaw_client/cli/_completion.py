"""Inline suggestions for the interactive shell."""

import sys
from typing import Any, Callable, Iterator, List, Tuple

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.completion import Completer as PTCompleter
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings

from ..client import ClimateClaw
from ._commands import (
    EXIT_COMMANDS,
    PENDING_LINES,
    SLASH_COMMANDS,
    SLASH_PREFIX,
)


class Completer:
    """Completion candidates for the shell."""

    def __init__(self, client: ClimateClaw) -> None:
        self.client = client

    def candidates(self, line: str, text: str) -> List[str]:
        """Get the completion candidates for ``text``.

        ``line`` is the input in front of ``text``.
        """
        if line.startswith(f"{SLASH_PREFIX}model "):
            return [m for m in self.client.available_models if m.startswith(text)]
        if line:
            return []
        words = [SLASH_PREFIX + n for n in SLASH_COMMANDS] + list(EXIT_COMMANDS)
        return [w for w in words if w.startswith(text)]

    def matches(self, before_cursor: str) -> Tuple[str, List[str]]:
        """Get the word in front of the cursor and its candidates."""
        line, sep, text = before_cursor.rpartition(" ")
        line = " ".join(PENDING_LINES + [line + sep])
        return text, self.candidates(line.lstrip(), text)

    def suggest(self, before_cursor: str) -> str | None:
        """Get the inline suggestion for the text in front of the cursor.

        Only the missing rest of the best match is returned.
        """
        text, candidates = self.matches(before_cursor)
        for candidate in candidates:
            if len(candidate) > len(text):
                return candidate[len(text) :]
        return None


class MenuCompleter(PTCompleter):
    """Offer all candidates in a completion menu."""

    def __init__(self, completer: Completer) -> None:
        self.completer = completer

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        text, candidates = self.completer.matches(document.text_before_cursor)
        for candidate in candidates:
            yield Completion(candidate, start_position=-len(text))


class InlineSuggest(AutoSuggest):
    """Show the best completion as ghost text behind the cursor."""

    def __init__(self, completer: Completer) -> None:
        self.completer = completer

    def get_suggestion(self, buffer: Buffer, document: Document) -> Suggestion | None:
        if document.text_after_cursor.strip():
            return None
        rest = self.completer.suggest(document.text_before_cursor)
        return Suggestion(rest) if rest else None


def _key_bindings(completer: Completer) -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("tab")
    def _(event: Any) -> None:
        """Accept a single match, otherwise show or cycle the options."""
        buffer = event.current_buffer
        if buffer.complete_state:
            buffer.complete_next()
            return
        _, candidates = completer.matches(buffer.document.text_before_cursor)
        if len(candidates) == 1 and buffer.suggestion:
            buffer.insert_text(buffer.suggestion.text)
        elif candidates:
            buffer.start_completion(select_first=False)

    return bindings


def setup(client: ClimateClaw) -> Callable[[str], str]:
    """Create the prompt function with inline suggestions.

    Falls back to :func:`input` if stdin is not a terminal.
    """
    if not sys.stdin.isatty():
        return lambda prompt: input(prompt)
    completer = Completer(client)
    session: PromptSession[str] = PromptSession(
        auto_suggest=InlineSuggest(completer),
        completer=MenuCompleter(completer),
        complete_while_typing=False,
        key_bindings=_key_bindings(completer),
        history=InMemoryHistory(),
    )
    return lambda prompt: session.prompt(prompt)
