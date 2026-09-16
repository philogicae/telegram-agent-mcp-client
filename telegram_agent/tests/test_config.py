"""Tests for ``telegram_agent/src/core/config.py``."""

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

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
