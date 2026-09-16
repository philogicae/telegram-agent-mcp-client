"""Tests for ``telegram_agent/src/core/agent.py``."""

from json import dumps
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.console import Console

from telegram_agent.src.core import agent as agent_mod
from telegram_agent.src.core.agent import (
    Agent,
    _last_error,
    _media_blocks,
    _raw_model_summary,
)
from telegram_agent.tests.fakes import make_message


class FakeStreamAgent:
    """Scripted ``swarm.agent``: one astream per entry, plus state snapshots."""

    def __init__(
        self, streams: list[list[dict[str, Any]]] | None = None, history: Any = None
    ) -> None:
        self.streams = list(streams or [])
        self.history = history if history is not None else []
        self.inputs: list[Any] = []

    async def astream(self, payload: Any, config: Any, subgraphs: bool = False):
        self.inputs.append(payload)
        for chunk in self.streams.pop(0):
            yield ("", chunk)

    async def aget_state(self, config: Any) -> Any:
        return SimpleNamespace(values={"messages": list(self.history)})


def make_swarm(
    active: str = "A",
    tools_by_agent: dict[str, list[str]] | None = None,
    streams: list[list[dict[str, Any]]] | None = None,
    history: Any = None,
) -> Any:
    return SimpleNamespace(
        config=SimpleNamespace(
            active=active,
            tools_by_agent=tools_by_agent
            if tools_by_agent is not None
            else {active: []},
        ),
        active={},
        agent=FakeStreamAgent(streams, history),
    )


def make_chat_agent(
    user_config: dict[str, Any] | None = None,
    agents: dict[str, Any] | None = None,
) -> Agent:
    agent = Agent.__new__(Agent)
    agent.user_config = user_config or {}
    agent.agents = agents or {}
    agent.console = Console()
    agent.dev = False
    agent.debug = False
    agent.thread_mappings = {}
    return agent


def chunk_model(*messages: Any) -> dict[str, Any]:
    return {"model": {"messages": list(messages)}}


def chunk_tools(*messages: Any) -> dict[str, Any]:
    return {"tools": {"messages": list(messages)}}


class TestRawModelSummary:
    def test_none(self):
        assert _raw_model_summary(None) == "no message"

    def test_full_ai_message(self):
        msg = AIMessage(
            "abc",
            tool_calls=[{"name": "t", "id": "1", "args": {}}],
            additional_kwargs={"reasoning_content": "r"},
            response_metadata={"finish_reason": "stop", "model_name": "m"},
        )
        out = _raw_model_summary(msg)
        assert "content='abc'" in out
        assert "tool_calls=['t']" in out
        assert "reasoning='r'" in out
        assert "finish='stop'" in out

    def test_non_string_content_is_stringified(self):
        msg = AIMessage(content=[{"type": "text", "text": "x"}])
        assert "content=" in _raw_model_summary(msg)


class TestLastError:
    def test_prefers_most_recent_error(self):
        msgs = [
            HumanMessage("hi"),
            ToolMessage("error: first", name="a", tool_call_id="1"),
            ToolMessage("failed: second", name="b", tool_call_id="2"),
        ]
        assert _last_error(msgs) == "failed: second"

    def test_status_error_counts_without_prefix(self):
        msg = ToolMessage("boom", name="a", tool_call_id="1", status="error")
        assert _last_error([msg]) == "boom"

    def test_plain_tool_output_ignored(self):
        assert (
            _last_error([ToolMessage("all good", name="a", tool_call_id="1")]) is None
        )

    def test_empty_tool_output_ignored(self):
        assert _last_error([ToolMessage("", name="a", tool_call_id="1")]) is None

    def test_no_tool_messages(self):
        assert _last_error([]) is None

    def test_long_error_truncated_to_first_line(self):
        msg = ToolMessage(
            "error: " + "x" * 500 + "\nsecond line", name="a", tool_call_id="1"
        )
        out = _last_error([msg])
        assert out is not None
        assert out.startswith("error:")
        assert "\n" not in out
        assert len(out) <= 300


class TestMediaBlocks:
    def test_audio_becomes_audio_block(self):
        out = _media_blocks([{"data": b"abc", "mime_type": "audio/ogg"}])
        assert out[0]["type"] == "audio"
        assert out[0]["mime_type"] == "audio/ogg"
        assert out[0]["base64"] == "YWJj"

    def test_image_becomes_data_url(self):
        out = _media_blocks([{"data": b"abc", "mime_type": "image/jpeg"}])
        assert out[0]["image_url"]["url"] == "data:image/jpeg;base64,YWJj"

    def test_non_bytes_passed_through(self):
        raw = {"type": "text", "text": "x"}
        assert _media_blocks([raw]) == [raw]


class TestUserManagement:
    def make(self, **kwargs: Any) -> Agent:
        agent = Agent.__new__(Agent)
        agent.user_config = kwargs.get("user_config", {})
        return agent

    def test_group_users_handles_bad_shapes(self):
        agent = self.make(
            user_config={"admin": "bad", "allowed": {"users": {"1": "a"}}}
        )
        assert agent._group_users("admin") == {}
        assert agent._group_users("missing") == {}
        assert agent._group_users("allowed") == {"1": "a"}

    def test_is_allowed_across_groups(self):
        agent = self.make(user_config={"admin": {"users": {"1": "a"}}})
        assert agent.is_allowed(1)
        assert agent.is_allowed("1")
        assert not agent.is_allowed(2)

    def test_is_admin_only_admin_group(self):
        agent = self.make(
            user_config={
                "admin": {"users": {"1": "a"}},
                "allowed": {"users": {"2": "b"}},
            }
        )
        assert agent.is_admin(1)
        assert not agent.is_admin(2)

    def test_match_group_by_id_then_name(self):
        agent = self.make(
            user_config={"admin": {"users": {"1": "Boss"}}, "allowed": {"users": {}}}
        )
        assert agent._match_group("1", "Nobody") == "admin"
        assert agent._match_group("", "boss") == "admin"
        assert agent._match_group("", "nobody") is None

    def test_add_and_remove_allowed_user_persist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agent_mod, "CONFIG_DIR", str(tmp_path))
        agent = self.make(user_config={})
        agent.add_allowed_user(5, "New")
        assert agent._group_users("allowed") == {"5": "New"}
        assert (tmp_path / "user_config.json").exists()

        assert agent.remove_allowed_user(5) is True
        assert agent.remove_allowed_user(5) is False

    def test_add_allowed_user_repairs_bad_shapes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agent_mod, "CONFIG_DIR", str(tmp_path))
        agent = self.make(user_config={"allowed": {"users": "bad"}})
        agent.add_allowed_user(5, "New")
        assert agent._group_users("allowed") == {"5": "New"}


class TestAgentInit:
    async def test_init_without_tools(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agent_mod, "CONFIG_DIR", str(tmp_path))

        async def fake_load_tools() -> list[Any]:
            return []

        monkeypatch.setattr(Agent, "load_tools", staticmethod(fake_load_tools))
        agent = await Agent.init(dev=True, enable_tools=True)
        assert agent.tools == []

    async def test_load_tools_uses_get_tools(self, monkeypatch):
        sentinel = [object()]

        async def fake_get_tools() -> list[Any]:
            return sentinel

        monkeypatch.setattr(agent_mod, "get_tools", fake_get_tools)
        assert await Agent.load_tools() is sentinel


class TestChat:
    def make(self, user_config: dict[str, Any], agents: dict[str, Any]) -> Agent:
        return make_chat_agent(user_config, agents)

    async def test_unknown_user_gets_no_reply(self):
        agent = self.make({"admin": {"users": {"1": "a"}}}, {})
        assert [event async for event in agent.chat("hi")] == []

    async def test_empty_content_yields_placeholder(self):
        swarm = make_swarm()
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("   ")]
        assert events == [("A", "...?", True, {})]

    async def test_final_text_response(self):
        swarm = make_swarm(streams=[[chunk_model(AIMessage("hello"))]])
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("hi")]
        assert events == [("A", "hello", True, {})]

    async def test_media_message_becomes_blocks(self):
        swarm = make_swarm(streams=[[chunk_model(AIMessage("seen"))]])
        agent = self.make({"admin": {"users": {"456": "Tester"}}}, {"admin": swarm})
        msg = make_message(text="check")
        msg.media = [{"type": "media", "data": b"abc", "mime_type": "image/jpeg"}]  # ty: ignore[unresolved-attribute]
        async for _event in agent.chat(msg):
            pass
        sent = swarm.agent.inputs[0]["messages"][-1].content
        assert any(block.get("type") == "image_url" for block in sent)

    async def test_tool_error_flag_and_retry(self):
        call = AIMessage(
            "", tool_calls=[{"name": "web_search", "id": "1", "args": {"q": "x"}}]
        )
        result = ToolMessage("error: boom", name="web_search", tool_call_id="1")
        swarm = make_swarm(
            tools_by_agent={"A": ["web_search"]},
            streams=[
                [chunk_model(call)],
                [chunk_tools(result)],
                [chunk_model(AIMessage("recovered"))],
            ],
            history=[AIMessage("previous")],
        )
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("hi")]
        assert events[-1][:3] == ("A", "recovered", True)
        tool_events = [e for e in events if e[3].get("tool") == "web_search"]
        assert tool_events
        assert tool_events[-1][3]["tool_ok"] is False
        assert "❌" in tool_events[-1][1]

    async def test_tool_timeout_reported_as_neutral(self):
        call = AIMessage("", tool_calls=[{"name": "dev", "id": "1", "args": {}}])
        result = ToolMessage(
            dumps({"timeout": True, "timeout_at": "12s"}), name="dev", tool_call_id="1"
        )
        swarm = make_swarm(
            tools_by_agent={"A": ["dev"]},
            streams=[
                [chunk_model(call)],
                [chunk_tools(result)],
                [chunk_model(AIMessage("done"))],
            ],
            history=[AIMessage("previous")],
        )
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("hi")]
        timeout_events = [
            e for e in events if e[3].get("tool_ok") is None and e[3].get("tool")
        ]
        assert timeout_events
        assert "Timeout after" in timeout_events[-1][1]

    async def test_invalid_tool_is_ignored_then_continues(self):
        valid = AIMessage("", tool_calls=[{"name": "known", "id": "1", "args": {}}])
        invalid = AIMessage(
            "", tool_calls=[{"name": "not_allowed", "id": "2", "args": {}}]
        )
        spy = ToolMessage("spy", name="not_allowed", tool_call_id="2")
        swarm = make_swarm(
            tools_by_agent={"A": ["known"]},
            streams=[
                [
                    chunk_model(valid),
                    chunk_model(invalid),
                    chunk_tools(spy),
                    chunk_model(AIMessage("ok")),
                ]
            ],
        )
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("hi")]
        assert events[-1][:3] == ("A", "ok", True)
        # The ignored tool's result never reaches the turn (no tool event for it).
        assert all(e[3].get("tool") != "not_allowed" for e in events)

    async def test_transfer_switches_active_agent(self):
        call = AIMessage(
            "", tool_calls=[{"name": "transfer_to_B", "id": "1", "args": {}}]
        )
        swarm = make_swarm(
            tools_by_agent={"A": ["transfer_to_B"], "B": []},
            streams=[[chunk_model(call)], [chunk_model(AIMessage("hi from B"))]],
            history=[AIMessage("previous")],
        )
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("hi")]
        assert swarm.active["test"] == "B"
        assert any("Transfer To B" in e[1] for e in events)
        assert events[-1][1] == "hi from B"

    async def test_relay_message_routes_to_first_group_with_swarm(self):
        swarm = make_swarm(streams=[[chunk_model(AIMessage("relayed"))]])
        agent = self.make(
            {
                "admin": {"users": {}},
                "worker": {"users": {}},
            },
            {"worker": swarm},
        )
        msg = make_message(text="fire", user_id=0, message_id=0)
        events = [event async for event in agent.chat(msg)]
        assert events[-1][1] == "relayed"

    async def test_recontext_rebases_thread(self, monkeypatch):
        swarm = make_swarm(streams=[[chunk_model(AIMessage("post-context"))]])
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        swarm.agent.history = [HumanMessage("x" * 500_000)]

        from telegram_agent.src.core.utils import ReContext

        async def fake_recontext(state, user_msg, provider=None):
            return ReContext(summary="SUMMARY", user_message="Developer: rephrased")

        monkeypatch.setattr(agent_mod, "summarize_and_rephrase", fake_recontext)
        events = [event async for event in agent.chat("hi")]
        assert events[-1][1] == "post-context"
        assert "test" in agent.thread_mappings
        new_thread = agent.thread_mappings["test"]
        assert new_thread.startswith("test:")
        assert swarm.active[new_thread] == "A"

    async def test_group_without_swarm_gets_no_reply(self):
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {})
        assert [event async for event in agent.chat("hi")] == []

    async def test_non_dict_state_does_not_break_history(self):
        swarm = make_swarm(streams=[[chunk_model(AIMessage("ok"))]])
        swarm.agent.aget_state = lambda config: _none_state()
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("hi")]
        assert events[-1][1] == "ok"

    async def test_empty_reply_exhausts_retries_with_last_error(self):
        history = [ToolMessage("error: boom", name="t", tool_call_id="1")]
        swarm = make_swarm(
            streams=[
                [chunk_tools(ToolMessage("", name="t", tool_call_id="1"))]
                for _ in range(4)
            ],
            history=history,
        )
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("hi")]
        final = events[-1]
        assert final[2] is True
        assert "Last error: error: boom" in final[1]

    async def test_empty_reply_exhausts_retries_without_cause(self):
        swarm = make_swarm(
            streams=[
                [chunk_tools(ToolMessage("", name="t", tool_call_id="1"))]
                for _ in range(4)
            ],
            history=[AIMessage("prev")],
        )
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("hi")]
        assert "same internal error occurred 3 times" in events[-1][1]

    async def test_completely_empty_stream_is_retried(self):
        swarm = make_swarm(
            streams=[
                [],
                [],
                [],
                [chunk_model(AIMessage("recovered"))],
            ],
            history=[AIMessage("prev")],
        )
        agent = self.make({"admin": {"users": {"-1": "Developer"}}}, {"admin": swarm})
        events = [event async for event in agent.chat("hi")]
        assert events[-1][1] == "recovered"


class TestAgentSwarmConstruction:
    def test_builds_swarms_from_user_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agent_mod, "CONFIG_DIR", str(tmp_path))
        (tmp_path / "user_config.json").write_text(
            dumps({"grp": {"agents": ["A"], "users": {}}})
        )
        fake_config = SimpleNamespace(
            agents=["agentA"],
            active="A",
            tools_by_agent={"A": []},
            transfer_instructions={},
        )
        monkeypatch.setattr(agent_mod, "get_agent_config", lambda *a, **k: fake_config)

        class FakeSwarmBuilder:
            def __init__(self, agents: Any, default_active_agent: str) -> None:
                self.args = (agents, default_active_agent)

            def compile(self, checkpointer: Any = None, debug: bool = False) -> str:
                return "compiled"

        monkeypatch.setattr(agent_mod, "create_swarm", FakeSwarmBuilder)
        monkeypatch.setattr(agent_mod, "checkpointer", lambda dev, persist: None)
        monkeypatch.setattr(Agent, "agents", agent_mod.Dict())

        agent = Agent([], persist=False, dev=True)
        assert agent.agents["grp"].agent == "compiled"
        assert agent.agents["grp"].config is fake_config
        assert agent.agents["grp"].active == {}

    def test_groups_without_valid_config_are_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agent_mod, "CONFIG_DIR", str(tmp_path))
        (tmp_path / "user_config.json").write_text(dumps({"grp": {"agents": []}}))
        monkeypatch.setattr(agent_mod, "get_agent_config", lambda *a, **k: None)
        monkeypatch.setattr(Agent, "agents", agent_mod.Dict())
        agent = Agent([], dev=True)
        assert agent.agents == {}


class TestRunAgentCli:
    class FakeInstance:
        def __init__(self, events: list[Any]) -> None:
            self.events = events

        def __enter__(self) -> TestRunAgentCli.FakeInstance:
            return self

        def __exit__(self, *args: Any) -> bool:
            return False

        async def chat(self, content: Any):
            for event in self.events:
                yield event

    async def test_cli_loop_breaks_on_empty_input(self, monkeypatch):
        instance = self.FakeInstance([("A", "hello", True, {})])
        inputs = iter(["hi", ""])
        monkeypatch.setattr("builtins.input", lambda *_: next(inputs))

        async def fake_init(**kwargs: Any) -> Any:
            return instance

        monkeypatch.setattr(Agent, "init", staticmethod(fake_init))
        await agent_mod.run_agent(dev=False)

    async def test_dev_mode_waits_between_steps(self, monkeypatch):
        instance = self.FakeInstance(
            [("A", "step", False, {}), ("A", "final", True, {})]
        )
        inputs = iter(["go", "enter", ""])
        monkeypatch.setattr("builtins.input", lambda *_: next(inputs))

        async def fake_init(**kwargs: Any) -> Any:
            return instance

        monkeypatch.setattr(Agent, "init", staticmethod(fake_init))
        await agent_mod.run_agent(dev=True)

    async def test_keyboard_interrupt_breaks_the_loop(self, monkeypatch):
        def raise_interrupt(*args: Any) -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", raise_interrupt)

        async def fake_init(**kwargs: Any) -> Any:
            return self.FakeInstance([])

        monkeypatch.setattr(Agent, "init", staticmethod(fake_init))
        await agent_mod.run_agent()


async def _none_state() -> Any:
    return SimpleNamespace(values={})
