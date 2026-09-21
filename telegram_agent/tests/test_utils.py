"""Tests for ``telegram_agent/src/utils.py``."""

from types import SimpleNamespace

from telegram_agent.src.utils import (
    Singleton,
    Timer,
    extract_response,
    is_tool_call_markup_only,
    parse_tool_call_markup,
)


class TestSingleton:
    def test_same_instance_and_subclass_isolation(self):
        class A(Singleton):
            pass

        class B(Singleton):
            pass

        assert A() is A()
        assert B() is B()
        assert A() is not B()


class TestTimer:
    def test_done_formats_seconds(self):
        timer = Timer()
        timer.start -= 1.25
        assert timer.done() == "1.25s"


class TestExtractResponse:
    def test_plain_string_content(self):
        assert extract_response(SimpleNamespace(content=" hi ")) == ("hi", None)

    def test_non_message_object_is_its_own_content(self):
        assert extract_response(" raw ") == ("raw", None)

    def test_content_block_list_collects_text(self):
        msg = SimpleNamespace(
            content=[
                {"type": "text", "text": " one "},
                {"type": "text", "text": "two"},
                {"type": "tool_use", "id": "x"},
            ]
        )
        assert extract_response(msg) == ("one\ntwo", None)

    def test_string_items_inside_content_list(self):
        msg = SimpleNamespace(content=["a", " b "])
        assert extract_response(msg) == ("a\nb", None)

    def test_reasoning_kwargs_first_key_wins(self):
        msg = SimpleNamespace(
            content="answer",
            additional_kwargs={"reasoning_content": " deep ", "reasoning": "other"},
        )
        assert extract_response(msg) == ("answer", "deep")

    def test_reasoning_skips_empty_values(self):
        msg = SimpleNamespace(content="a", additional_kwargs={"reasoning": "  "})
        assert extract_response(msg) == ("a", None)

    def test_additional_kwargs_must_be_dict(self):
        msg = SimpleNamespace(content="a", additional_kwargs=["nope"])
        assert extract_response(msg) == ("a", None)

    def test_anthropic_thinking_block(self):
        msg = SimpleNamespace(
            content=[
                {"type": "thinking", "thinking": " hmm "},
                {"type": "text", "text": "done"},
            ]
        )
        assert extract_response(msg) == ("done", "hmm")

    def test_inline_think_tags_become_reasoning(self):
        msg = SimpleNamespace(content="<thinking>deep</thinking>final")
        assert extract_response(msg) == ("final", "deep")

    def test_inline_think_tag_unclosed(self):
        msg = SimpleNamespace(content="answer<think>later")
        assert extract_response(msg) == ("answer", "later")

    def test_kwargs_reasoning_wins_over_inline_tags(self):
        msg = SimpleNamespace(
            content="<think>inline</think>text",
            additional_kwargs={"reasoning": "kwarg"},
        )
        assert extract_response(msg) == ("text", "kwarg")

    def test_think_tag_without_content_is_ignored(self):
        msg = SimpleNamespace(content="<think>   </think>")
        assert extract_response(msg) == ("", None)

    def test_no_recognized_content_returns_empty(self):
        assert extract_response(SimpleNamespace(content=123)) == ("", None)
        assert extract_response(SimpleNamespace(content=[])) == ("", None)


# =============================================================================
# GLM tool-call markup: provider leaked tool calls as text (prod 2026-09-21).
# =============================================================================

_LEAK = (
    "<tool_call>update_task<arg_key>status</arg_key><arg_value>completed</arg_value>"
    "<arg_key>taskId</arg_key><arg_value>uf8zims25ea7a2s7qdq5mrr7</arg_value></tool_call>"
    "<tool_call>update_task<arg_key>status</arg_key><arg_value>done</arg_value>"
    "<arg_key>taskId</arg_key><arg_value>eh0ppchgcpoi1kp6hugave5t</arg_value></tool_call>"
    '<tool_call>web_search<arg_key>query</arg_key><arg_value>{"q": "test", "limit": 5}'
    "</arg_value></tool_call>"
)


class TestParseToolCallMarkup:
    def test_extracts_concatenated_leaked_calls(self):
        prose, calls = parse_tool_call_markup(_LEAK)
        assert prose == ""
        assert [c["name"] for c in calls] == [
            "update_task",
            "update_task",
            "web_search",
        ]
        assert calls[0]["args"] == {
            "status": "completed",
            "taskId": "uf8zims25ea7a2s7qdq5mrr7",
        }
        assert calls[1]["args"] == {
            "status": "done",
            "taskId": "eh0ppchgcpoi1kp6hugave5t",
        }
        assert calls[2]["args"] == {"query": {"q": "test", "limit": 5}}
        assert all(c["type"] == "tool_call" for c in calls)
        assert len({c["id"] for c in calls}) == 3  # unique ids for result pairing

    def test_keeps_prose_and_strips_spans(self):
        prose, calls = parse_tool_call_markup("Working on it.\n\n" + _LEAK)
        assert prose == "Working on it."
        assert len(calls) == 3

    def test_scalars_stay_strings_when_not_json(self):
        prose, calls = parse_tool_call_markup(
            "<tool_call>t<arg_key>k</arg_key><arg_value>{not json}</arg_value></tool_call>"
        )
        assert calls[0]["args"] == {"k": "{not json}"}

    def test_unclosed_span_left_as_prose(self):
        prose, calls = parse_tool_call_markup("<tool_call>update_task<arg_key>a")
        assert calls == []
        assert "update_task" in prose

    def test_empty_and_none(self):
        assert parse_tool_call_markup("") == ("", [])
        assert parse_tool_call_markup("plain text") == ("plain text", [])


class TestIsToolCallMarkupOnly:
    def test_flags_spans_but_not_prose(self):
        assert is_tool_call_markup_only(_LEAK)
        assert is_tool_call_markup_only(_LEAK + "\n\n")  # blank edges ignored
        assert not is_tool_call_markup_only("Working on it.\n\n" + _LEAK)
        assert not is_tool_call_markup_only("")
        assert not is_tool_call_markup_only("The <tool_call> syntax is XML-like.")
