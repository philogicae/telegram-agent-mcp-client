"""Tests for ``telegram_agent/src/core/llm.py``."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek

from telegram_agent.src.core import llm as llm_mod
from telegram_agent.src.core.llm import (
    _OPENCODE_SESSION,
    LLM,
    OpenCodeChatModel,
    _env_num,
    _order,
    _repair_tool_call_markup,
    _set_opencode_session_header,
    _split,
    can_docs,
    can_draw,
    can_listen,
    can_read,
    can_see,
    can_speak,
    can_struct,
    can_watch,
    mark_alive,
    mark_dead,
    supports,
)


@pytest.fixture(autouse=True)
def clean_llm_state(monkeypatch):
    """Deterministic LLM state: no singleton leakage, no real API keys."""
    for var in (
        "GEMINI_API_KEY",
        "FIREWORKS_API_KEY",
        "OPENCODE_API_KEY",
        "OPENROUTER_API_KEY",
        "OLLAMA_API_BASE",
        "LLM_JAIL_STRIKES",
        "LLM_JAIL_HOURS",
        "LLM_DEAD_COOLDOWN",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(llm_mod, "_jail", {})
    instance = LLM()
    monkeypatch.setattr(instance, "llm", {})
    monkeypatch.setattr(instance, "extra", {})
    return instance


class TestOrder:
    def test_parses_and_trims(self, monkeypatch):
        monkeypatch.setenv("SOME_ORDER", " a, b ,,c ")
        assert _order("SOME_ORDER", "x") == ["a", "b", "c"]

    def test_default_used_when_unset(self, monkeypatch):
        monkeypatch.delenv("SOME_ORDER", raising=False)
        assert _order("SOME_ORDER", "a,b") == ["a", "b"]


class TestSplit:
    def test_none_and_empty(self):
        assert _split(None) == ("", frozenset())
        assert _split("") == ("", frozenset())

    def test_model_and_caps(self):
        assert _split("m|a+b") == ("m", frozenset({"a", "b"}))

    def test_trailing_separator_dropped(self):
        assert _split("m|a+") == ("m", frozenset({"a"}))

    def test_model_without_caps(self):
        assert _split("m") == ("m", frozenset())


class TestSupports:
    def test_matching_provider(self, monkeypatch):
        monkeypatch.setattr(llm_mod, "CAPABILITIES", {"p": frozenset({"text"})})
        assert supports("p", "text")

    def test_missing_capability(self, monkeypatch):
        monkeypatch.setattr(llm_mod, "CAPABILITIES", {"p": frozenset({"text"})})
        assert not supports("p", "vision")

    def test_none_falls_back_to_first_order_entry(self, monkeypatch):
        monkeypatch.setattr(llm_mod, "CAPABILITIES", {"first": frozenset({"text"})})
        monkeypatch.setattr(llm_mod, "LLM_ORDER", ["first", "second"])
        assert supports(None, "text")

    def test_unknown_provider(self, monkeypatch):
        monkeypatch.setattr(llm_mod, "CAPABILITIES", {})
        assert not supports("nope", "text")
        # Without a requested capability every provider trivially qualifies.
        assert supports("nope")


class TestCapabilityHelpers:
    def test_each_helper_reads_its_capability(self, monkeypatch):
        monkeypatch.setattr(
            llm_mod,
            "CAPABILITIES",
            {
                "p": frozenset(
                    {
                        "text",
                        "pdf",
                        "structured",
                        "vision",
                        "stt",
                        "tts",
                        "video",
                        "image",
                    }
                )
            },
        )
        for helper in (
            can_read,
            can_docs,
            can_struct,
            can_see,
            can_listen,
            can_speak,
            can_watch,
            can_draw,
        ):
            assert helper("p")

    def test_absent_capability(self, monkeypatch):
        monkeypatch.setattr(llm_mod, "CAPABILITIES", {"p": frozenset()})
        assert not can_read("p")


class TestJail:
    def test_strike_parks_then_releases(self, monkeypatch):
        monkeypatch.setenv("LLM_DEAD_COOLDOWN", "0")
        mark_dead("p")
        assert llm_mod._jail["p"]["fails"] == 1
        assert llm_mod._alive("p")  # cooldown elapsed immediately

    def test_provider_dead_during_cooldown(self, monkeypatch):
        monkeypatch.setenv("LLM_DEAD_COOLDOWN", "300")
        mark_dead("p")
        assert not llm_mod._alive("p")

    def test_explicit_cooldown_argument(self, monkeypatch):
        monkeypatch.setenv("LLM_DEAD_COOLDOWN", "0")
        mark_dead("p", cooldown=3600)
        assert not llm_mod._alive("p")

    def test_jail_after_strikes(self, monkeypatch):
        monkeypatch.setenv("LLM_JAIL_STRIKES", "2")
        monkeypatch.setenv("LLM_JAIL_HOURS", "24")
        mark_dead("p")
        mark_dead("p")
        assert llm_mod._jail["p"]["fails"] == 0.0
        assert not llm_mod._alive("p")

    def test_mark_alive_clears_history(self):
        mark_dead("p", cooldown=999)
        mark_alive("p")
        assert "p" not in llm_mod._jail


class TestEnvNum:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("N", raising=False)
        assert _env_num("N", 1.5) == 1.5

    def test_parsed_value(self, monkeypatch):
        monkeypatch.setenv("N", "2.5")
        assert _env_num("N", 1.5) == 2.5

    def test_garbage_falls_back(self, monkeypatch):
        monkeypatch.setenv("N", "abc")
        assert _env_num("N", 1.5) == 1.5


class TestOpencodeSessionHeader:
    def test_header_injected_when_session_bound(self):
        request = httpx.Request("GET", "http://x")
        token = _OPENCODE_SESSION.set("sess-1")
        try:
            _set_opencode_session_header(request)
        finally:
            _OPENCODE_SESSION.reset(token)
        assert request.headers["x-opencode-session"] == "sess-1"

    def test_header_absent_without_session(self):
        request = httpx.Request("GET", "http://x")
        _set_opencode_session_header(request)
        assert "x-opencode-session" not in request.headers


class TestPick:
    def test_no_configured_providers(self, clean_llm_state, monkeypatch):
        monkeypatch.setattr(llm_mod, "LLM_ORDER", ["a"])
        monkeypatch.setattr(llm_mod, "LLM_ORDER_FAST", ["a"])
        # Configured models exist, but none of them is in the run order.
        monkeypatch.setattr(clean_llm_state, "llm", {"other": object()})
        assert LLM.pick() is None

    def test_first_configured_in_order(self, clean_llm_state, monkeypatch):
        monkeypatch.setattr(llm_mod, "LLM_ORDER", ["b", "a"])
        monkeypatch.setattr(llm_mod, "LLM_ORDER_FAST", ["a", "b"])
        monkeypatch.setattr(clean_llm_state, "llm", {"a": object(), "b": object()})
        assert LLM.pick() == "b"
        assert LLM.pick(fast=True) == "a"

    def test_capability_filtering_and_aux_endpoints(self, clean_llm_state, monkeypatch):
        monkeypatch.setattr(llm_mod, "LLM_ORDER", ["a"])
        monkeypatch.setattr(llm_mod, "LLM_ORDER_FAST", ["a"])
        monkeypatch.setattr(clean_llm_state, "llm", {"a": object()})
        monkeypatch.setattr(
            llm_mod, "CAPABILITIES", {"a": frozenset(), "aux": frozenset({"tts"})}
        )
        monkeypatch.setattr(llm_mod, "SPECS", {"tts-help": ("x", frozenset({"tts"}))})
        # "aux" is not configured anywhere, so it cannot be picked.
        assert LLM.pick("tts") is None

    def test_extra_configured_provider_selected_for_capability(
        self, clean_llm_state, monkeypatch
    ):
        monkeypatch.setattr(llm_mod, "LLM_ORDER", ["a"])
        monkeypatch.setattr(llm_mod, "LLM_ORDER_FAST", ["a"])
        monkeypatch.setattr(clean_llm_state, "llm", {"a": object()})
        monkeypatch.setattr(clean_llm_state, "extra", {"tts1": object()})
        monkeypatch.setattr(
            llm_mod, "CAPABILITIES", {"a": frozenset(), "tts1": frozenset({"tts"})}
        )
        assert LLM.pick("tts") == "tts1"

    def test_dead_provider_sorted_last(self, clean_llm_state, monkeypatch):
        monkeypatch.setattr(llm_mod, "LLM_ORDER", ["a", "b"])
        monkeypatch.setattr(llm_mod, "LLM_ORDER_FAST", ["a", "b"])
        monkeypatch.setattr(clean_llm_state, "llm", {"a": object(), "b": object()})
        mark_dead("a", cooldown=999)
        assert LLM.pick() == "b"


class TestGet:
    def test_unknown_provider_raises(self, clean_llm_state, monkeypatch):
        monkeypatch.setattr(clean_llm_state, "llm", {"known": object()})
        with pytest.raises(ValueError, match="not found"):
            LLM.get("unknown")

    def test_returns_cached_model(self, clean_llm_state, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(clean_llm_state, "llm", {"p": sentinel})
        assert LLM.get("p") is sentinel


class _FakeChatLLM:
    def __init__(self, reply: Any = None, error: Exception | None = None):
        self.reply = reply
        self.error = error

    async def ainvoke(self, messages: Any) -> Any:
        if self.error:
            raise self.error
        return self.reply


class TestGetConstructsProviders:
    def _patch_models(self, monkeypatch, gemini_model: str) -> list[Any]:
        created: list[Any] = []

        def factory(name: str):
            def make(**kwargs: Any) -> Any:
                obj = SimpleNamespace(name=name, kwargs=kwargs)
                created.append(obj)
                return obj

            return make

        monkeypatch.setattr(llm_mod, "ChatOllama", factory("ollama"))
        monkeypatch.setattr(llm_mod, "ChatGoogleGenerativeAI", factory("gemini"))
        monkeypatch.setattr(llm_mod, "ChatAnthropic", factory("anthropic"))
        monkeypatch.setattr(llm_mod, "ChatDeepSeek", factory("deepseek"))
        monkeypatch.setattr(
            llm_mod,
            "AsyncOpenAI",
            lambda **kwargs: SimpleNamespace(audio=SimpleNamespace(speech="speech")),
        )
        monkeypatch.setattr(
            llm_mod,
            "SPECS",
            {
                "ollama": ("llama", frozenset()),
                "gemini": (gemini_model, frozenset()),
                "gemini-small": ("gemini-small", frozenset()),
                "fireworks": ("fw", frozenset()),
                "opencode": ("oc", frozenset()),
                "opencode-alt": ("oc-alt", frozenset()),
                "openrouter-tts": ("tts", frozenset()),
            },
        )
        for var, value in (
            ("OLLAMA_API_BASE", "http://ollama"),
            ("GEMINI_API_KEY", "k"),
            ("FIREWORKS_API_KEY", "k"),
            ("OPENCODE_API_KEY", "k"),
            ("OPENROUTER_API_KEY", "k"),
        ):
            monkeypatch.setenv(var, value)
        monkeypatch.setattr(llm_mod, "LLM_ORDER", ["opencode"])
        monkeypatch.setattr(llm_mod, "LLM_ORDER_FAST", ["opencode"])
        return created

    def test_registers_all_configured_providers(self, clean_llm_state, monkeypatch):
        self._patch_models(monkeypatch, "gemini-3-pro")
        model = LLM.get()
        assert model is clean_llm_state.llm["opencode"]
        assert set(clean_llm_state.llm) == {
            "ollama",
            "gemini",
            "gemini-small",
            "fireworks",
            "opencode",
            "opencode-alt",
        }
        assert clean_llm_state.extra["openrouter-tts"] == "speech"
        # Gemini 3 models use a thinking level instead of a token budget.
        gemini = clean_llm_state.llm["gemini"]
        assert gemini.kwargs["thinking_level"] == "low"
        assert "thinking_budget" not in gemini.kwargs

    def test_gemini_pre3_uses_thinking_budget(self, clean_llm_state, monkeypatch):
        self._patch_models(monkeypatch, "gemini-2.5-pro")
        LLM.get()
        assert clean_llm_state.llm["gemini"].kwargs["thinking_budget"] == 512


class TestTtsAdapt:
    async def test_adapts_text(self, monkeypatch):
        fake = _FakeChatLLM(AIMessage(content=" spoken "))
        monkeypatch.setattr(LLM, "get", staticmethod(lambda p=None: fake))
        monkeypatch.setattr(LLM, "pick", staticmethod(lambda *caps, **kw: "p"))
        assert await LLM.tts_adapt("**hello**") == "spoken"

    async def test_failure_returns_original(self, monkeypatch):
        fake = _FakeChatLLM(error=RuntimeError("boom"))
        monkeypatch.setattr(LLM, "get", staticmethod(lambda p=None: fake))
        monkeypatch.setattr(LLM, "pick", staticmethod(lambda *caps, **kw: "p"))
        assert await LLM.tts_adapt("original") == "original"

    async def test_empty_reply_returns_original(self, monkeypatch):
        fake = _FakeChatLLM(AIMessage(content="  "))
        monkeypatch.setattr(LLM, "get", staticmethod(lambda p=None: fake))
        monkeypatch.setattr(LLM, "pick", staticmethod(lambda *caps, **kw: "p"))
        assert await LLM.tts_adapt("original") == "original"


class _FakeSpeech:
    def __init__(
        self, content: bytes | None = b"audio", error: Exception | None = None
    ):
        self.content = content
        self.error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.content)


class TestTts:
    async def test_no_client_returns_none(self, clean_llm_state, monkeypatch):
        monkeypatch.setattr(clean_llm_state, "extra", {})
        assert await LLM.tts("hello") is None

    async def test_generates_audio_and_strips_emotion_tags(
        self, clean_llm_state, monkeypatch
    ):
        speech = _FakeSpeech()
        monkeypatch.setattr(clean_llm_state, "extra", {"openrouter-tts": speech})
        monkeypatch.setenv("OPENROUTER_TTS_SPEED", "1.5")
        monkeypatch.setenv("OPENROUTER_TTS_VOICE", "eve")
        out = await LLM.tts("[excited] Hi [smiles]there")
        assert out == b"audio"
        assert speech.kwargs["input"] == "Hi there"
        assert "excited" in speech.kwargs["instructions"]
        assert speech.kwargs["speed"] == 1.5

    async def test_invalid_speed_falls_back(self, clean_llm_state, monkeypatch):
        speech = _FakeSpeech()
        monkeypatch.setattr(clean_llm_state, "extra", {"openrouter-tts": speech})
        monkeypatch.setenv("OPENROUTER_TTS_SPEED", "fast")
        assert await LLM.tts("hi") == b"audio"
        assert speech.kwargs["speed"] == 1.15

    async def test_out_of_range_speed_clamped(self, clean_llm_state, monkeypatch):
        speech = _FakeSpeech()
        monkeypatch.setattr(clean_llm_state, "extra", {"openrouter-tts": speech})
        monkeypatch.setenv("OPENROUTER_TTS_SPEED", "10")
        assert await LLM.tts("hi") == b"audio"
        assert speech.kwargs["speed"] == 4.0

    async def test_generation_failure_returns_none(self, clean_llm_state, monkeypatch):
        speech = _FakeSpeech(error=RuntimeError("boom"))
        monkeypatch.setattr(clean_llm_state, "extra", {"openrouter-tts": speech})
        assert await LLM.tts("hi") is None


# =============================================================================
# GLM tool-call markup repair: leaked spans -> structured calls.
# =============================================================================

_LEAK = (
    "<tool_call>update_task<arg_key>status</arg_key><arg_value>completed</arg_value>"
    "<arg_key>taskId</arg_key><arg_value>uf8zims25ea7a2s7qdq5mrr7</arg_value></tool_call>"
    "<tool_call>update_task<arg_key>status</arg_key><arg_value>done</arg_value>"
    "<arg_key>taskId</arg_key><arg_value>eh0ppchgcpoi1kp6hugave5t</arg_value></tool_call>"
)


def _leak_message(**kwargs: Any) -> AIMessage:
    return AIMessage(content=_LEAK, **kwargs)


class TestRepairToolCallMarkup:
    def test_converts_leaked_text_into_tool_calls(self):
        repaired = _repair_tool_call_markup(_leak_message(id="m1"))
        assert len(repaired.tool_calls) == 2
        assert repaired.content == ""
        assert repaired.id == "m1"
        assert repaired.tool_calls[0]["args"] == {
            "status": "completed",
            "taskId": "uf8zims25ea7a2s7qdq5mrr7",
        }

    def test_preserves_metadata_and_reasoning(self):
        msg = AIMessage(
            content=_LEAK,
            id="m2",
            additional_kwargs={"reasoning_content": "mark tasks done"},
            response_metadata={"finish_reason": "stop", "model_name": "glm-5.3-flash"},
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
        )
        repaired = _repair_tool_call_markup(msg)
        assert repaired.additional_kwargs["reasoning_content"] == "mark tasks done"
        assert repaired.response_metadata["finish_reason"] == "stop"
        assert repaired.usage_metadata["input_tokens"] == 10

    def test_keeps_prose_alongside_calls(self):
        repaired = _repair_tool_call_markup(
            AIMessage(content="Marking them now.\n\n" + _LEAK, id="m3")
        )
        assert repaired.content == "Marking them now."
        assert len(repaired.tool_calls) == 2

    def test_leaves_clean_messages_untouched(self):
        clean = AIMessage(content="The answer is 42.", id="m4")
        assert _repair_tool_call_markup(clean) is clean

    def test_skips_messages_with_structured_tool_calls(self):
        with_calls = AIMessage(
            content=_LEAK,
            tool_calls=[{"name": "t", "args": {}, "id": "call_x", "type": "tool_call"}],
            id="m5",
        )
        assert _repair_tool_call_markup(with_calls) is with_calls

    def test_skips_non_string_content(self):
        blocks = AIMessage(
            content=[{"type": "text", "text": "<tool_call>x</tool_call>"}]
        )
        assert _repair_tool_call_markup(blocks) is blocks


class TestOpenCodeChatModel:
    def _model(self) -> OpenCodeChatModel:
        return OpenCodeChatModel(model="glm-5.3-flash", api_key="test-key")

    def _patch_super(self, monkeypatch, message: AIMessage, async_: bool = False):
        from langchain_core.outputs import ChatGeneration, ChatResult

        result = ChatResult(generations=[ChatGeneration(message=message)])
        if async_:

            async def fake(*args: Any, **kwargs: Any):
                return result

        else:

            def fake(*args: Any, **kwargs: Any):
                return result

        monkeypatch.setattr(ChatDeepSeek, "_agenerate" if async_ else "_generate", fake)

    async def test_agenerate_repairs_leaked_markup(self, monkeypatch):
        self._patch_super(monkeypatch, _leak_message(id="m6"), async_=True)
        result = await self._model()._agenerate([])
        assert len(result.generations[0].message.tool_calls) == 2

    def test_generate_repairs_leaked_markup(self, monkeypatch):
        self._patch_super(monkeypatch, _leak_message(id="m7"))
        result = self._model()._generate([])
        assert len(result.generations[0].message.tool_calls) == 2

    def test_opencode_providers_routed_through_repair_model(
        self, monkeypatch, clean_llm_state
    ):
        monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
        monkeypatch.setattr(
            llm_mod,
            "SPECS",
            {
                **llm_mod.SPECS,
                "opencode": ("deepseek-v4-flash", frozenset({"text"})),
                "opencode-alt": ("glm-5.3-flash", frozenset({"text"})),
            },
        )
        assert isinstance(LLM.get("opencode"), OpenCodeChatModel)
        assert isinstance(LLM.get("opencode-alt"), OpenCodeChatModel)
