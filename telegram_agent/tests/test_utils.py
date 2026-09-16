"""Tests for ``telegram_agent/src/utils.py``."""

from types import SimpleNamespace

from telegram_agent.src.utils import Singleton, Timer, extract_response


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
