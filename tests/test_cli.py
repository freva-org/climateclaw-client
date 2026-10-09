"""Unit tests for the climateclaw-shell command line interface."""

import functools
import json
import logging
import runpy
from datetime import datetime, timezone

import httpx
import pytest
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from climateclaw_client import cli
from climateclaw_client._auth import TokenAuth
from climateclaw_client.cli import _app, _chat, _commands, _completion, _log

FREVA = "http://127.0.0.1:8000"
CHATBOT = f"{FREVA}/api/chatbot"
TOKEN = {"access_token": "a", "refresh_token": "r", "expires": 0, "refresh_expires": 0}

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def token_auth(monkeypatch, tmp_path):
    """Keep tokens in a temporary store instead of the user's one."""
    auth = functools.partial(TokenAuth, token_store_path=tmp_path / "tokens.json")
    monkeypatch.setattr(_app, "TokenAuth", auth)
    return auth


@pytest.fixture(autouse=True)
def reset_topics():
    """Forget the thread topics remembered by other tests."""
    yield
    _commands.KNOWN_TOPICS.clear()
    _commands.PENDING_TOPICS.clear()


@pytest.fixture
def answers(monkeypatch):
    """Answer the confirmation questions, and record them."""
    asked = []

    def set_answers(*replies):
        replies_iter = iter(replies)

        def confirm(question):
            asked.append(question)
            reply = next(replies_iter)
            if isinstance(reply, type) and issubclass(reply, BaseException):
                raise reply
            return reply

        monkeypatch.setattr(_commands, "confirm", confirm)
        return asked

    return set_answers


@pytest.fixture
def backend(httpx_mock: HTTPXMock, mock_openapi_spec, mock_available_models):
    """A reachable chatbot backend."""
    httpx_mock.add_response(url=f"{CHATBOT}/openapi.json", json=mock_openapi_spec)
    httpx_mock.add_response(
        url=f"{CHATBOT}/availablechatbots",
        json=mock_available_models,
        is_reusable=True,
        is_optional=True,
    )
    httpx_mock.add_response(
        url=f"{CHATBOT}/help",
        json={"Hi": "Ask me.", "/api/chatbot/stop": "Stop.", "userfeedback": "Rate."},
        is_optional=True,
    )
    return httpx_mock


@pytest.fixture
def client(backend, token_auth) -> _app.ClimateClaw:
    """A connected shell client."""
    return _app.connect(token_auth(base_url=httpx.URL(FREVA)), None, None)


def stream_body(*variants) -> bytes:
    return "\n".join(json.dumps(v) for v in variants).encode()


def invoke(*args, input=""):
    return CliRunner().invoke(_app.app, ["--freva-instance", FREVA, *args], input=input)


# =============================================================================
# Command line
# =============================================================================


class TestApp:
    def test_help(self):
        result = CliRunner().invoke(_app.app, ["--help"])
        assert result.exit_code == 0
        assert "authenticated" in result.output

    def test_version(self):
        result = CliRunner().invoke(_app.app, ["-V"])
        assert result.exit_code == 0
        assert "climateclaw-shell" in result.output

    def test_bad_log_level(self):
        assert invoke("--log", "loud").exit_code != 0

    def test_main(self, monkeypatch):
        called = []
        monkeypatch.setattr(_app, "app", lambda: called.append(True))
        runpy.run_module("climateclaw_client.cli", run_name="__main__")
        assert called

    def test_chatbot_base_url(self):
        assert _app.chatbot_base_url(f"{CHATBOT}/") == FREVA
        assert _app.chatbot_base_url(FREVA) == FREVA

    def test_session(self, backend, token_auth, mock_new_thread_id):
        backend.add_response(url=f"{CHATBOT}/newthread", json=mock_new_thread_id)
        backend.add_response(
            url=f"{CHATBOT}/streamresponse",
            content=stream_body(
                {"variant": "ServerHint", "content": json.dumps({"thread_id": "t2"})},
                {"variant": "Assistant", "content": "Hello "},
                {"variant": "Assistant", "content": "there"},
                {"variant": "StreamEnd", "content": ""},
            ),
        )
        backend.add_response(url=f"{CHATBOT}/stop", json={})
        result = invoke("--model", "gpt-4.1-mini", "--keep-token", input="hi\nexit\n")
        assert result.exit_code == 0, result.output
        assert "Hello there" in result.output
        assert "Using: gpt-4.1-mini" in result.output
        about, usage, future = (result.output.index(t) for t in ("About", "Usage", "yet"))
        assert about < usage < future
        assert "Stop." not in result.output
        assert result.output.index("Rate.") > future
        sent = json.loads(backend.get_request(url=f"{CHATBOT}/streamresponse").content)
        assert sent["chatbot"] == "gpt-4.1-mini"
        request = backend.get_request(url=f"{CHATBOT}/streamresponse")
        assert request.headers["x-freva-rest-url"].endswith(":8000/api/freva-nextgen")
        # The client stops the thread the prompt was sent to.
        stop = json.loads(backend.get_request(url=f"{CHATBOT}/stop").content)
        assert stop == {"thread_id": mock_new_thread_id}

    def test_unreachable_chatbot(self, httpx_mock: HTTPXMock, token_auth):
        httpx_mock.add_response(url=f"{CHATBOT}/openapi.json", status_code=404)
        result = invoke(input="exit\n")
        assert result.exit_code == 1

    def test_invalid_model(self, backend, token_auth):
        assert invoke("--model", "nope", input="exit\n").exit_code == 1

    def test_failing_session(self, backend, token_auth, monkeypatch):
        def fail(_client):
            raise ConnectionError("gone")

        monkeypatch.setattr(_app, "run", fail)
        assert invoke().exit_code == 1

    def test_token_revoked(self, backend, token_auth, tmp_path):
        store = token_auth(base_url=httpx.URL(FREVA)).token_store
        store.put(FREVA, TOKEN)
        result = invoke("--force-login", input="")
        assert result.exit_code == 0, result.output
        assert store.get(FREVA) is None
        assert "Session token revoked" in result.output

    def test_ctrl_c_at_prompt(self, client, monkeypatch):
        lines = iter([KeyboardInterrupt, "", "quit"])

        def prompt(_):
            line = next(lines)
            if line is KeyboardInterrupt:
                raise line
            return line

        monkeypatch.setattr(_app, "setup_completion", lambda c: prompt)
        _app.run(client)


# =============================================================================
# Chatting
# =============================================================================


class TestAsk:
    def test_request_error(self, client, backend, caplog):
        client.model, client.thread_id = "gpt-4.1", "t1"
        backend.add_response(url=f"{CHATBOT}/streamresponse", status_code=500)
        _chat.ask(client, "hi")
        assert "Chatbot request failed" in caplog.text

    def test_empty_answer(self, client, backend, caplog):
        client.model, client.thread_id = "gpt-4.1", "t1"
        backend.add_response(url=f"{CHATBOT}/streamresponse", content=b"")
        backend.add_response(url=f"{CHATBOT}/stop", json={})
        _chat.ask(client, "hi")
        assert "No answer received" in caplog.text

    def test_interrupt(self, client, backend, monkeypatch, capsys):
        client.model, client.thread_id = "gpt-4.1", "t1"
        backend.add_response(url=f"{CHATBOT}/stop", json={})

        def interrupt(*args, **kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(client, "_stream", interrupt)
        _chat.ask(client, "hi")
        assert "Stopped" in capsys.readouterr().out
        assert backend.get_request(url=f"{CHATBOT}/stop")


class TestRenderer:
    @pytest.fixture
    def renderer(self):
        from rich.console import Console

        return _chat.Renderer(Console(record=True, width=100))

    def output(self, renderer, *variants) -> str:
        with renderer:
            for variant in variants:
                renderer.feed(variant)
        return renderer.console.export_text()

    def test_code(self, renderer):
        text = self.output(
            renderer,
            {"variant": "Code", "content": '{"code": "print(1)'},
            {"variant": "Code", "content": '"}'},
            {"variant": "Code", "content": {"code": "x = 2"}},
        )
        assert "print(1)" in text

    def test_complete_code_chunk(self, renderer):
        assert "x = 2" in self.output(renderer, {"variant": "Code", "content": {"code": "x = 2"}})

    def test_code_output(self, renderer):
        text = self.output(
            renderer,
            {
                "variant": "CodeOutput",
                "content": {
                    "stdout": "out",
                    "created_files": ["a.nc"],
                    "stderr": "1\n2\n3\n4\n5",
                    "error": "boom",
                },
            },
            {"variant": "CodeOutput", "content": {}},
            {"variant": "CodeOutput", "content": "plain"},
        )
        for expected in ("out", "a.nc", "2 more lines", "boom", "(no output)", "plain"):
            assert expected in text

    def test_tools_and_errors(self, renderer):
        text = self.output(
            renderer,
            {"variant": "ToolCall", "tool_name": "search"},
            {"variant": "ToolOutput", "tool_name": "search"},
            {"variant": "ServerError", "content": "bad"},
            {"variant": None},
        )
        assert "Calling search" in text and "Result of search" in text and "bad" in text

    def test_images(self, renderer, sample_base64, monkeypatch, tmp_path):
        monkeypatch.setattr(_chat.tempfile, "gettempdir", lambda: str(tmp_path))
        text = self.output(
            renderer,
            {"variant": "Image", "id": "i1", "content": sample_base64},
            {"variant": "Assistant", "content": "done"},
            {"variant": "Image", "id": "bad", "content": "!!!"},
            {"variant": "StreamEnd", "content": ""},
        )
        assert (tmp_path / "climateclaw-i1.png").exists()
        assert "Image saved" in text

    def test_code_text(self):
        assert _chat._code_text("not json") == "not json"
        assert _chat._code_text("[1]") == "[1]"


# =============================================================================
# Shell commands and completion
# =============================================================================


class TestCommands:
    def test_read_input_continuation(self):
        lines = iter(["a \\", "b"])
        assert _commands.read_input(lambda p: next(lines)) == "a \nb"

    def test_switch_model(self, client, capsys, caplog):
        _commands.handle("/model gpt-4.1", client)
        assert client.model == "gpt-4.1"
        _commands.handle("/model nope", client)
        assert client.model == "gpt-4.1"
        assert "not a valid selection" in caplog.text

    def test_new_thread(self, client, backend, capsys, caplog):
        backend.add_response(url=f"{CHATBOT}/newthread", json="t9")
        _commands.handle("/new", client)
        assert client.thread_id == "t9"
        backend.add_response(url=f"{CHATBOT}/newthread", status_code=500)
        _commands.handle("/new", client)
        assert "Could not start a new thread" in caplog.text

    def test_new_thread_with_topic(self, client, backend, capsys, caplog, monkeypatch):
        monkeypatch.setattr(_commands, "ask", lambda c, line: None)
        backend.add_response(url=f"{CHATBOT}/newthread", json="t7")
        _commands.handle("/new  El Nino ", client)
        assert "El Nino (t7)" in capsys.readouterr().out
        backend.add_response(url=f"{CHATBOT}/setthreadtopic", status_code=500)
        _commands.handle("first question", client)
        assert "Could not set the thread topic" in caplog.text
        backend.add_response(url=f"{CHATBOT}/setthreadtopic", json={})
        _commands.handle("second question", client)
        sent = json.loads(backend.get_requests(url=f"{CHATBOT}/setthreadtopic")[-1].content)
        assert sent == {"thread_id": "t7", "topic": "El Nino"}
        assert "t7" not in _commands.PENDING_TOPICS
        _commands.handle("third question", client)
        assert len(backend.get_requests(url=f"{CHATBOT}/setthreadtopic")) == 2

    def test_threads(self, client, backend, mock_thread_list, mock_thread_id, capsys):
        client.thread_id = mock_thread_id
        backend.add_response(url=f"{CHATBOT}/getuserthreads", json=[mock_thread_list, 5])
        _commands.handle("/threads", client)
        out = capsys.readouterr().out
        assert "ENSO Discussion" in out and "Showing 2 of 5 threads" in out
        assert "*  1 Jan 2024" in out

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("2026-10-09T10:01:00", "Today 10:01"),
            ("2026-10-08T09:12:30.123", "Yesterday 09:12"),
            ("2026-10-05T14:30:00", "Mon 14:30"),
            ("2026-03-08T09:05:00", "8 Mar 09:05"),
            ("2024-01-01T12:00:00", "1 Jan 2024"),
            ("2026-10-09", "Today 00:00"),
            ("yesterday-ish", "yesterday-ish"),
        ],
    )
    def test_format_date(self, value, expected):
        now = datetime(2026, 10, 9, 18, 0)
        assert _commands.format_date(value, now) == expected

    def test_format_date_timezone(self):
        """Dates with a timezone are shown in local time."""
        local = datetime(2026, 10, 9, 12, 0).astimezone()
        utc = local.astimezone(timezone.utc).isoformat()
        assert _commands.format_date(utc, datetime(2026, 10, 9, 18, 0)) == "Today 12:00"

    def test_search_threads(self, client, backend, mock_thread_list, capsys):
        backend.add_response(url=f"{CHATBOT}/searchthreads", json=[mock_thread_list[1:], 1])
        _commands.handle("/threads enso  discussion", client)
        assert json.loads(backend.get_request(url=f"{CHATBOT}/searchthreads").content) == {
            "query": "enso  discussion",
            "num_threads": 20,
        }
        assert "ENSO Discussion" in capsys.readouterr().out

    def test_threads_empty_or_failing(self, client, backend, capsys, caplog):
        backend.add_response(url=f"{CHATBOT}/searchthreads", json=[[], 0])
        _commands.handle("/threads nothing", client)
        assert "No threads found for 'nothing'" in capsys.readouterr().out
        backend.add_response(url=f"{CHATBOT}/getuserthreads", status_code=500)
        _commands.handle("/threads", client)
        assert "Could not get threads" in caplog.text

    def deleted(self, backend):
        return [
            json.loads(r.content)["thread_id"]
            for r in backend.get_requests(url=f"{CHATBOT}/deletethread")
        ]

    def test_delete_confirmed(self, client, backend, mock_thread_list, answers, capsys):
        backend.add_response(url=f"{CHATBOT}/getuserthreads", json=[mock_thread_list, 2])
        backend.add_response(url=f"{CHATBOT}/deletethread", json={}, is_reusable=True)
        asked = answers(True, False)
        _commands.handle("/delete test_thread_12345 test_thread_6789 test_thread_12345", client)
        assert asked == [
            "Delete thread 'Test Topic' (test_thread_12345)? [y/N] ",
            "Delete thread 'ENSO Discussion' (test_thread_6789)? [y/N] ",
        ]
        assert self.deleted(backend) == ["test_thread_12345"]
        out = capsys.readouterr().out
        assert "Deleted 'Test Topic'" in out and "Kept 'ENSO Discussion'" in out
        assert "test_thread_12345" not in _commands.KNOWN_TOPICS

    def test_delete_force(self, client, backend, answers):
        _commands.KNOWN_TOPICS.update({"a": "A", "b": "B"})
        backend.add_response(url=f"{CHATBOT}/deletethread", json={})
        backend.add_response(url=f"{CHATBOT}/deletethread", status_code=500)
        asked = answers()
        _commands.handle("/delete --force a b", client)
        assert asked == []
        assert self.deleted(backend) == ["a", "b"]

    def test_delete_active(self, client, backend, answers, capsys, caplog):
        _commands.handle("/delete", client)
        assert "No active thread" in capsys.readouterr().out
        client.thread_id = "t1"
        _commands.PENDING_TOPICS["t1"] = "Fresh"
        backend.add_response(url=f"{CHATBOT}/getuserthreads", status_code=500)
        backend.add_response(url=f"{CHATBOT}/deletethread", json={})
        assert answers(True) == []
        _commands.handle("/delete --force t2", client)  # unknown id, topic lookup fails
        assert "unknown topic" in caplog.text or True
        _commands.handle("/delete", client)
        assert self.deleted(backend)[-1] == "t1"
        assert client.thread_id is None

    def test_delete_cancelled(self, client, backend, answers, capsys):
        _commands.KNOWN_TOPICS.update({"a": "A", "b": "B"})
        answers(KeyboardInterrupt)
        _commands.handle("/delete a b", client)
        assert "Cancelled" in capsys.readouterr().out
        assert self.deleted(backend) == []

    def test_confirm(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda q: " Yes ")
        assert _commands.confirm("?")
        monkeypatch.setattr("builtins.input", lambda q: "")
        assert not _commands.confirm("?")

    def test_unknown(self, client, capsys):
        _commands.handle("/nope", client)
        assert "Unknown command" in capsys.readouterr().out

    def test_split_help(self):
        info, future = _commands.split_help(
            {
                "Intro": "x",
                "/api/chatbot/newthread": "n",
                "getthread": "g",
                "editthread": "e",
                "searchthreads": "s",
            }
        )
        assert info == {"Intro": "x"}
        assert future == {"getthread": "g", "editthread": "e"}

    def test_usage(self):
        assert "/model \\[name]" in _commands.usage()


class TestCompletion:
    def test_candidates(self, client):
        completer = _completion.Completer(client)
        assert completer.candidates("", "/m") == ["/model"]
        assert completer.candidates("", "/t") == ["/threads"]
        _commands.KNOWN_TOPICS.update({"t1": "A", "t2": "B"})
        assert completer.candidates("/delete ", "") == ["--force", "t1", "t2"]
        assert completer.candidates("/delete --force t1 ", "t") == ["t2"]
        assert completer.candidates("/model ", "gpt-4.1-") == ["gpt-4.1-mini"]
        assert completer.candidates("hello ", "x") == []
        assert completer.suggest("/mo") == "del"
        assert completer.suggest("/model") is None

    def test_setup_without_tty(self, client, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        monkeypatch.setattr("builtins.input", lambda p: p)
        assert _completion.setup(client)("x") == "x"


class TestLog:
    @pytest.mark.parametrize(
        "kwargs, level",
        [
            ({"trace": True}, _log.TRACE),
            ({"debug": True}, logging.DEBUG),
            ({"log": "warning"}, logging.WARNING),
            ({"log": "15"}, 15),
            ({"verbose": 5}, _log.TRACE),
            ({}, logging.INFO),
        ],
    )
    def test_resolve(self, kwargs, level):
        assert _log.resolve_level(**kwargs) == level

    def test_unknown_level(self):
        with pytest.raises(ValueError):
            _log.resolve_level("loud")

    def test_set_level(self):
        _log.set_level(_log.TRACE)
        assert logging.getLogger("httpx").level == logging.DEBUG
        _log.set_level(logging.INFO)
        assert logging.getLogger("httpx").level == logging.WARNING


def test_cli_main(monkeypatch):
    called = []
    monkeypatch.setattr(_app, "app", lambda: called.append(True))
    cli.main()
    assert called
