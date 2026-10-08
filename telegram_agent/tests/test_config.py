"""Tests for ``telegram_agent/src/core/config.py``."""

from types import SimpleNamespace
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.errors import GraphInterrupt
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from mcp.shared.exceptions import MCPError

from telegram_agent.src.core import config as config_mod
from telegram_agent.tests.test_tools import make_tool


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    directory = tmp_path / "config"
    directory.mkdir()
    monkeypatch.setattr(config_mod, "CONFIG_DIR", str(directory))
    return directory


@pytest.fixture
def patched_agent_creation(monkeypatch):
    """Replace LLM/get + create_agent + handoff tools with inert fakes."""
    created: list[dict[str, Any]] = []

    def fake_create_agent(**kwargs: Any) -> Any:
        created.append(kwargs)
        return SimpleNamespace(name=kwargs.get("name"), kwargs=kwargs)

    def fake_handoff(agent_name: str, description: str) -> Any:
        return SimpleNamespace(name=f"transfer_to_{agent_name}")

    monkeypatch.setattr(config_mod, "create_agent", fake_create_agent)
    monkeypatch.setattr(config_mod, "create_handoff_tool", fake_handoff)
    monkeypatch.setattr(
        config_mod, "LLM", SimpleNamespace(get=staticmethod(lambda: object()))
    )
    return created


def write_config(config_dir, payload: dict[str, Any]) -> None:
    from json import dumps

    (config_dir / "agent_config.json").write_text(dumps(payload))


BASE = {
    "agents": {
        "Alpha": {"transfer": "To Alpha", "prompt": "You are Alpha.", "tools": ["ta"]},
        "Beta": {"transfer": "To Beta", "prompt": "You are Beta."},
    },
    "common": {"tools": ["common"], "handoff": "Transfer to {agent}"},
}


class TestGetAgentConfig:
    def test_creates_config_from_example_when_missing(
        self, config_dir, patched_agent_creation, monkeypatch
    ):
        from json import dumps

        (config_dir / "agent_config.example.json").write_text(dumps(BASE))
        monkeypatch.chdir(config_dir)
        assert not (config_dir / "agent_config.json").exists()
        result = config_mod.get_agent_config([], display=False)
        assert (config_dir / "agent_config.json").exists()
        assert result is not None
        assert result.active == "Alpha"

    def test_basic_agents_and_tools(self, config_dir, patched_agent_creation):
        write_config(config_dir, BASE)
        result = config_mod.get_agent_config(
            [make_tool("common"), make_tool("ta")], display=False
        )
        assert result is not None
        assert result.active == "Alpha"
        assert result.tools_by_agent["Alpha"] == ["transfer_to_Beta", "common", "ta"]
        assert result.tools_by_agent["Beta"] == ["transfer_to_Alpha", "common"]
        assert result.transfer_instructions["Alpha"] == "Transfer to Alpha, To Alpha"

    def test_single_agent_has_no_handoff_tools(
        self, config_dir, patched_agent_creation
    ):
        write_config(config_dir, {"agents": {"Only": {"transfer": "x"}}})
        result = config_mod.get_agent_config([], display=False)
        assert result is not None
        assert result.tools_by_agent["Only"] == []

    def test_only_agents_filter_and_miss(self, config_dir, patched_agent_creation):
        write_config(config_dir, BASE)
        result = config_mod.get_agent_config([], only_agents=["Alpha"], display=False)
        assert result is not None
        assert list(result.tools_by_agent) == ["Alpha"]
        assert (
            config_mod.get_agent_config([], only_agents=["Missing"], display=False)
            is None
        )

    def test_no_agents_raises(self, config_dir, patched_agent_creation):
        write_config(config_dir, {"agents": {}})
        with pytest.raises(ValueError, match="No agents found"):
            config_mod.get_agent_config([], display=False)

    def test_missing_transfer_raises(self, config_dir, patched_agent_creation):
        write_config(config_dir, {"agents": {"Alpha": {"prompt": "x"}}})
        with pytest.raises(ValueError, match="Missing `transfer`"):
            config_mod.get_agent_config([], display=False)

    def test_guidelines_and_routines_added_to_prompt(
        self, config_dir, patched_agent_creation
    ):
        write_config(
            config_dir,
            {
                "agents": {"Alpha": {"transfer": "t", "prompt": "P"}},
                "common": {
                    "guidelines": ["be nice", "be quick"],
                    "routines": {
                        "guidelines": ["follow the routine"],
                        "default": {
                            "daily": {
                                "trigger": "every day",
                                "steps": ["wake up", "work"],
                            }
                        },
                    },
                },
            },
        )
        config_mod.get_agent_config([], display=False)
        prompt = patched_agent_creation[0]["system_prompt"]
        assert "# Mandatory guidelines:\n- be nice\n- be quick" in prompt
        assert "\n# Routines:" in prompt
        assert "## daily (every day):" in prompt
        assert "1) wake up\n2) work" in prompt

    def test_agent_specific_routines_merge_and_override(
        self, config_dir, patched_agent_creation
    ):
        write_config(
            config_dir,
            {
                "agents": {
                    "Alpha": {
                        "transfer": "t",
                        "prompt": "P",
                        "routines": {
                            "daily": {"trigger": "custom", "steps": ["step"]},
                            "extra": {"trigger": "once", "steps": ["e"]},
                        },
                    }
                },
                "common": {
                    "routines": {"default": {"daily": {"trigger": "d", "steps": ["s"]}}}
                },
            },
        )
        config_mod.get_agent_config([], display=False)
        prompt = patched_agent_creation[0]["system_prompt"]
        assert "## daily (custom):" in prompt
        assert "## extra (once):" in prompt

    def test_routine_without_valid_trigger_skipped(
        self, config_dir, patched_agent_creation
    ):
        write_config(
            config_dir,
            {
                "agents": {"Alpha": {"transfer": "t", "prompt": "P"}},
                "common": {
                    "routines": {
                        "default": {
                            "bad": {"trigger": "", "steps": ["x"]},
                            "good": {"trigger": "t", "steps": "not-a-list"},
                        }
                    }
                },
            },
        )
        config_mod.get_agent_config([], display=False)
        prompt = patched_agent_creation[0]["system_prompt"]
        assert "## bad" not in prompt
        # A routine needs a valid trigger AND a non-empty step list: a
        # string/empty `steps` value adds no title at all.
        assert "## good" not in prompt

    def test_non_list_common_tools_ignored(self, config_dir, patched_agent_creation):
        write_config(
            config_dir,
            {"agents": {"Alpha": {"transfer": "t"}}, "common": {"tools": "bad"}},
        )
        result = config_mod.get_agent_config([], display=False)
        assert result is not None
        assert result.tools_by_agent["Alpha"] == []

    def test_missing_prompt_gets_warning_prompt(
        self, config_dir, patched_agent_creation
    ):
        write_config(config_dir, {"agents": {"Alpha": {"transfer": "t"}}})
        config_mod.get_agent_config([], display=False)
        assert "Missing system prompt" in patched_agent_creation[0]["system_prompt"]

    def test_verbose_output(self, config_dir, patched_agent_creation, capsys):
        write_config(config_dir, BASE)
        config_mod.get_agent_config([], verbose=True)
        out = capsys.readouterr().out
        assert "Available agents: 2" in out
        assert "Alpha" in out

    def test_display_only_lists_tools(self, config_dir, patched_agent_creation, capsys):
        write_config(config_dir, BASE)
        config_mod.get_agent_config(
            [make_tool("common")], config_name="Group", display=True
        )
        out = capsys.readouterr().out
        assert "Group - Available agents: 2" in out
        assert "Active agent:" in out


class TestPruneHistory:
    def test_before_agent_returns_remove_all_update(self):
        middleware = config_mod.PruneHistory()
        msgs = [HumanMessage("a"), HumanMessage("b")]
        out = middleware.before_agent({"messages": msgs}, None)
        assert out is not None
        assert out["messages"][0].id == REMOVE_ALL_MESSAGES

    async def test_abefore_agent_matches_sync(self):
        middleware = config_mod.PruneHistory()
        out = await middleware.abefore_agent({"messages": [HumanMessage("a")]}, None)
        assert out is not None
        assert out["messages"][0].id == REMOVE_ALL_MESSAGES

    def test_max_tokens_default(self):
        assert config_mod.PruneHistory().max_tokens == 120_000


class TestStripMessageNames:
    def test_strips_names_without_mutating_originals(self):
        tagged = AIMessage("hi", name="Geppetto")
        tagged.additional_kwargs["name"] = "Geppetto"
        clean = HumanMessage("yo")
        out = config_mod.StripMessageNames._strip([tagged, clean])
        assert out[0].name is None
        assert "name" not in out[0].additional_kwargs
        assert out[1] is clean  # untagged messages are reused as-is
        assert tagged.name == "Geppetto"  # original history untouched

    async def test_hooks_sanitize_the_request_copy(self):
        middleware = config_mod.StripMessageNames()
        seen: dict[str, Any] = {}

        class FakeRequest:
            messages = [AIMessage("hi", name="Geppetto")]

            def override(self, **kwargs: Any) -> FakeRequest:
                seen.update(kwargs)
                return self

        async def handler(request: Any) -> str:
            return "ok"

        assert await middleware.awrap_model_call(FakeRequest(), handler) == "ok"
        assert seen["messages"][0].name is None
        assert middleware.wrap_model_call(FakeRequest(), lambda r: "ok") == "ok"

    def test_attached_to_every_agent(self, config_dir, patched_agent_creation):
        write_config(config_dir, BASE)
        config_mod.get_agent_config([], display=False)
        assert patched_agent_creation  # two agents created
        for kwargs in patched_agent_creation:
            kinds = {type(m).__name__ for m in kwargs["middleware"]}
            assert {"PruneHistory", "StripMessageNames", "GracefulToolErrors"} <= kinds


class TestGracefulToolErrors:
    """A failing tool must not abort the run - it becomes an error message."""

    class FakeRequest:
        def __init__(self, name: str = "search", call_id: str = "call-1") -> None:
            self.tool_call = {"name": name, "id": call_id, "args": {}}

    async def test_async_transport_failure_becomes_error_message(self):
        middleware = config_mod.GracefulToolErrors()
        error = MCPError(-32603, "Server returned an error response")

        async def handler(request: Any) -> Any:
            raise error

        result = await middleware.awrap_tool_call(self.FakeRequest(), handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert result.name == "search"
        assert result.tool_call_id == "call-1"
        assert "Server returned an error response" in result.content

    def test_sync_failure_becomes_error_message(self):
        middleware = config_mod.GracefulToolErrors()

        def handler(request: Any) -> Any:
            raise RuntimeError("boom")

        result = middleware.wrap_tool_call(self.FakeRequest("create_task"), handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "create_task" in result.content
        assert "boom" in result.content

    async def test_success_is_passed_through(self):
        middleware = config_mod.GracefulToolErrors()

        async def handler(request: Any) -> str:
            return "ok"

        assert await middleware.awrap_tool_call(self.FakeRequest(), handler) == "ok"
        assert middleware.wrap_tool_call(self.FakeRequest(), lambda r: "ok") == "ok"

    async def test_interrupts_propagate(self):
        middleware = config_mod.GracefulToolErrors()

        async def handler(request: Any) -> Any:
            raise GraphInterrupt()

        with pytest.raises(GraphInterrupt):
            await middleware.awrap_tool_call(self.FakeRequest(), handler)

        def sync_handler(request: Any) -> Any:
            raise GraphInterrupt()

        with pytest.raises(GraphInterrupt):
            middleware.wrap_tool_call(self.FakeRequest(), sync_handler)

    async def test_parallel_batch_survives_a_failing_call(self):
        """A failing MCP call in a parallel batch must not abort the run.

        Reproduces the prod crash: the model issues two tool calls at once,
        one transport-fails, and the sibling result must survive while the
        failure reaches the model as an error message.
        """

        class ScriptedToolModel(GenericFakeChatModel):
            def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
                return self

        async def failing(**kwargs: Any) -> str:
            raise MCPError(-32603, "Server returned an error response")

        flaky = StructuredTool(
            name="flaky", description="", args_schema={}, coroutine=failing
        )
        good = make_tool("good")
        model = ScriptedToolModel(
            messages=iter(
                [
                    AIMessage(
                        "",
                        tool_calls=[
                            {"name": "flaky", "id": "1", "args": {}},
                            {"name": "good", "id": "2", "args": {}},
                        ],
                    ),
                    AIMessage("done"),
                ]
            )
        )
        agent = create_agent(
            model=model,
            tools=[flaky, good],
            middleware=[config_mod.GracefulToolErrors()],
        )
        result = await agent.ainvoke({"messages": [HumanMessage("go")]})
        statuses = {
            message.name: message.status
            for message in result["messages"]
            if isinstance(message, ToolMessage)
        }
        assert statuses == {"flaky": "error", "good": "success"}
        assert result["messages"][-1].content == "done"


class TestPrintAgents:
    async def test_delegates_to_get_agent_config(self, monkeypatch):
        seen: dict[str, Any] = {}

        async def fake_get_tools(display: bool = True) -> list[Any]:
            seen["display"] = display
            return []

        def fake_get_agent_config(tools: Any, verbose: bool = False) -> None:
            seen["verbose"] = verbose

        monkeypatch.setattr(config_mod, "get_tools", fake_get_tools)
        monkeypatch.setattr(config_mod, "get_agent_config", fake_get_agent_config)
        await config_mod.print_agents()
        assert seen == {"display": False, "verbose": True}
