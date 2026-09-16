"""Tests for ``telegram_agent/src/core/utils.py``."""

from json import dumps
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import StateSnapshot
from pydantic import BaseModel, ValidationError

from telegram_agent.src.core import utils
from telegram_agent.src.core.utils import (
    Flag,
    ReContext,
    Usage,
    _media_payload_chars,
    append_structured_output,
    checkpointer,
    format_called_tool,
    parse_structured_output,
    pre_agent_hook,
    run_schema,
    summarize_and_rephrase,
    token_counter,
)


class TestUsage:
    def test_accumulates_flat_and_nested_keys(self):
        usage = Usage()
        usage.add_usage({"input_tokens": 1, "output_tokens": 2})
        usage.add_usage({"input_tokens": 3, "details": {"reasoning": 4}})
        usage.add_usage({"details": {"reasoning": 1}})
        assert usage.total == {
            "input_tokens": 4,
            "output_tokens": 2,
            "details": {"reasoning": 5},
        }

    def test_str_lists_totals(self):
        usage = Usage()
        usage.add_usage({"a": 2})
        assert str(usage) == "a: 2"


class TestFlag:
    def test_flag_values(self):
        assert Flag.ERROR.value == "error:"
        assert Flag._ERROR.value == " error"


def test_format_called_tool():
    assert format_called_tool("web_search-v2") == "Web Search V2"


class TestCheckpointer:
    def test_dev_uses_memory(self):
        assert isinstance(checkpointer(dev=True), InMemorySaver)

    def test_no_persist_uses_memory(self):
        assert isinstance(checkpointer(persist=False), InMemorySaver)

    async def test_persist_uses_sqlite_saver(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        saver = checkpointer(dev=False, persist=True)
        assert saver.__class__.__name__ == "AsyncSqliteSaver"


class TestMediaPayloadChars:
    def test_long_strings_blanked(self):
        slim, chars = _media_payload_chars("A" * utils._MEDIA_PAYLOAD_MIN_CHARS)
        assert slim == ""
        assert chars == utils._MEDIA_PAYLOAD_MIN_CHARS

    def test_short_strings_kept(self):
        assert _media_payload_chars("short") == ("short", 0)

    def test_nested_structures(self):
        block = {"a": ["text", {"b": "B" * 5000}], "c": 1}
        slim, chars = _media_payload_chars(block)
        assert chars == 5000
        assert slim == {"a": ["text", {"b": ""}], "c": 1}


class TestTokenCounter:
    def test_empty(self):
        assert token_counter([]) == 0
        assert token_counter(None) == 0

    def test_text_messages_counted(self):
        assert token_counter([HumanMessage("hello world")]) > 0

    def test_remove_message_stubs_skipped(self):
        assert token_counter([RemoveMessage(REMOVE_ALL_MESSAGES)]) == 0

    def test_media_payload_counted_once(self):
        msg = HumanMessage(
            content=[
                {"type": "text", "text": "img"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64," + "A" * 40000},
                },
            ]
        )
        count = token_counter([msg])
        assert 7500 < count < 15000

    def test_original_message_not_mutated(self):
        msg = HumanMessage(
            content=[
                {"type": "text", "text": "x"},
                {"type": "audio", "mime_type": "audio/ogg", "base64": "A" * 5000},
            ]
        )
        token_counter([msg])
        assert "AAAA" in str(msg.content)


class TestPreAgentHook:
    def test_non_dict_state_returns_empty_trim(self):
        out = pre_agent_hook(SimpleNamespace())
        assert out == {"messages": []}

    def test_plain_trim_no_remove_marker(self):
        msgs = [HumanMessage("a"), AIMessage("b")]
        out = pre_agent_hook({"messages": msgs}, max_tokens=10_000)
        assert [m.id for m in out["messages"]] == [m.id for m in msgs]

    def test_remove_all_emits_marker_and_keeps_current_turn(self):
        msgs = [HumanMessage("old" * 500), HumanMessage("new")]
        out = pre_agent_hook({"messages": msgs}, remove_all=True, max_tokens=10)
        assert out["messages"][0].id == REMOVE_ALL_MESSAGES
        assert "new" in str(out["messages"][-1].content)

    def test_voice_payload_reaches_model_intact(self):
        voice = HumanMessage(
            content=[
                {"type": "text", "text": "voice"},
                {"type": "audio", "mime_type": "audio/ogg", "base64": "A" * 600000},
            ]
        )
        out = pre_agent_hook(
            {"messages": [HumanMessage("a"), AIMessage("b"), voice]},
            remove_all=True,
            max_tokens=1000,
        )
        assert "AAAA" in str(out["messages"][-1].content)

    def test_empty_messages_with_remove_all(self):
        # No history to exempt: the hook returns the (empty) trim result.
        out = pre_agent_hook({"messages": []}, remove_all=True)
        assert out["messages"] == []


def test_append_structured_output_includes_schema():
    class M(BaseModel):
        value: int

    out = append_structured_output(M)
    assert "# JSON Output Schema" in out
    assert '"value"' in out


class TestParseStructuredOutput:
    class M(BaseModel):
        value: int

    def test_direct_json_wins_over_fenced(self):
        assert parse_structured_output('{"value": 1}', self.M).value == 1

    def test_fenced_json_block(self):
        raw = 'text\n```json\n{"value": 2}\n```\nmore'
        assert parse_structured_output(raw, self.M).value == 2

    def test_fenced_block_without_json_label(self):
        raw = "```\n{'value': 3}\n```".replace("'", '"')
        assert parse_structured_output(raw, self.M).value == 3

    def test_braces_extracted_from_prose(self):
        assert (
            parse_structured_output(
                "say {'value': 4} ok".replace("'", '"'), self.M
            ).value
            == 4
        )

    def test_accepts_ai_message(self):
        assert (
            parse_structured_output(AIMessage(content='{"value": 5}'), self.M).value
            == 5
        )

    def test_invalid_payload_raises_validation_error(self):
        with pytest.raises(ValidationError):
            parse_structured_output("not json at all", self.M)


class _FakeStructuredLLM:
    def __init__(self, result: Any = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.seen: list[Any] = []

    def with_structured_output(self, schema: Any) -> _FakeStructuredLLM:
        self.schema = schema
        return self

    async def ainvoke(self, messages: Any) -> Any:
        self.seen = list(messages)
        if self.error:
            raise self.error
        return self.result


class _FakeTextLLM:
    def __init__(self, payload: str):
        self.payload = payload
        self.seen: list[Any] = []

    async def ainvoke(self, messages: Any) -> AIMessage:
        self.seen = list(messages)
        return AIMessage(content=self.payload)


def _patch_picker(
    monkeypatch, sequence: list[str | None], llms: dict[str, Any], capable: set[str]
):
    """Patch run_schema's LLM/can_struct/mark_* seams."""
    picks = list(sequence)

    def pick(*_caps: str, **_kwargs: Any) -> str | None:
        return picks.pop(0) if picks else None

    monkeypatch.setattr(utils.LLM, "pick", staticmethod(pick))
    monkeypatch.setattr(utils.LLM, "get", staticmethod(lambda p=None: llms[p]))
    monkeypatch.setattr(utils, "can_struct", lambda p=None: p in capable)
    alive, dead = [], []
    monkeypatch.setattr(utils, "mark_alive", alive.append)
    monkeypatch.setattr(utils, "mark_dead", dead.append)
    return alive, dead


class TestRunSchema:
    class M(BaseModel):
        value: int

    async def test_native_structured_output(self, monkeypatch):
        llm = _FakeStructuredLLM(result=self.M(value=1))
        alive, dead = _patch_picker(monkeypatch, ["p1"], {"p1": llm}, {"p1"})
        out = await run_schema([HumanMessage("q")], self.M, provider="p1")
        assert out.value == 1
        assert alive == ["p1"]
        assert dead == []

    async def test_no_provider_available(self, monkeypatch):
        _patch_picker(monkeypatch, [None], {}, set())
        with pytest.raises(RuntimeError, match="No LLM provider available"):
            await run_schema([HumanMessage("q")], self.M)

    async def test_failure_falls_over_to_next_provider(self, monkeypatch):
        bad = _FakeStructuredLLM(error=ValueError("boom"))
        good = _FakeStructuredLLM(result=self.M(value=2))
        alive, dead = _patch_picker(
            monkeypatch, ["p1", "p2"], {"p1": bad, "p2": good}, {"p1", "p2"}
        )
        out = await run_schema([HumanMessage("q")], self.M)
        assert out.value == 2
        assert dead == ["p1"]
        assert alive == ["p2"]

    async def test_repeated_pick_breaks_the_loop(self, monkeypatch):
        bad = _FakeStructuredLLM(error=ValueError("boom"))
        _patch_picker(monkeypatch, ["p1"], {"p1": bad}, {"p1"})
        with pytest.raises(RuntimeError):
            await run_schema([HumanMessage("q")], self.M)

    async def test_text_prompt_path_appends_schema_to_str_content(self, monkeypatch):
        llm = _FakeTextLLM(dumps({"value": 7}))
        _patch_picker(monkeypatch, ["p1"], {"p1": llm}, set())
        out = await run_schema([HumanMessage("q")], self.M, provider="p1")
        assert out.value == 7
        assert "# JSON Output Schema" in llm.seen[-1].content

    async def test_text_prompt_path_list_content_uses_system_message(self, monkeypatch):
        llm = _FakeTextLLM(dumps({"value": 8}))
        _patch_picker(monkeypatch, ["p1"], {"p1": llm}, set())
        first = HumanMessage(
            content=[
                {"type": "text", "text": "parts"},
                {"type": "audio", "base64": "A"},
            ]
        )
        out = await run_schema([first], self.M, provider="p1")
        assert out.value == 8
        assert llm.seen[0].type == "system"


class TestSummarizeAndRephrase:
    async def test_empty_history_still_completes(self, monkeypatch):
        state = StateSnapshot(
            values={"messages": []},
            next=(),
            config={},
            metadata=None,
            created_at=None,
            parent_config=None,
            tasks=(),
            interrupts=(),
        )

        async def fake_run_schema(messages, schema, provider=None):
            return ReContext(summary="None", user_message="user: hi")

        monkeypatch.setattr(utils, "run_schema", fake_run_schema)
        out = await summarize_and_rephrase(state, "hi")
        assert out.user_message == "user: hi"

    async def test_history_is_included(self, monkeypatch):
        state = StateSnapshot(
            values={"messages": [HumanMessage("old")]},
            next=(),
            config={},
            metadata=None,
            created_at=None,
            parent_config=None,
            tasks=(),
            interrupts=(),
        )
        captured: list[Any] = []

        async def fake_run_schema(messages, schema, provider=None):
            captured.extend(messages)
            return ReContext(summary="s", user_message="u")

        monkeypatch.setattr(utils, "run_schema", fake_run_schema)
        await summarize_and_rephrase(state, "new")
        assert any("old" in str(m.content) for m in captured)
        assert any("new" in str(m.content) for m in captured)
