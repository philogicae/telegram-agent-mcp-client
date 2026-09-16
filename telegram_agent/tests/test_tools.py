"""Tests for ``telegram_agent/src/core/tools.py``."""

from typing import Any

import pytest
from langchain_core.tools import StructuredTool

from telegram_agent.src.core import tools as tools_mod


def make_tool(
    name: str,
    schema: dict[str, Any] | None = None,
    calls: list[Any] | None = None,
) -> StructuredTool:
    """A real StructuredTool whose coroutine records its calls."""

    async def _coro(**kwargs: Any) -> str:
        if calls is not None:
            calls.append(kwargs)
        return "ok"

    _coro.__name__ = f"coro_{name}"
    return StructuredTool(
        name=name,
        description="test tool",
        args_schema=schema if schema is not None else {},
        coroutine=_coro,
    )


@pytest.fixture
def tool_dir(tmp_path, monkeypatch):
    directory = tmp_path / "tools"
    directory.mkdir()
    monkeypatch.setattr(tools_mod, "TOOL_DIR", directory)
    return directory


class TestLoadServerConfigs:
    def test_loads_nested_files_by_relative_name(self, tool_dir):
        (tool_dir / "web").mkdir()
        (tool_dir / "web" / "search.json").write_text('{"command": "cmd"}')
        assert tools_mod._load_server_configs() == {"web/search": {"command": "cmd"}}

    def test_underscore_files_excluded(self, tool_dir):
        (tool_dir / "_hidden.json").write_text("{}")
        assert tools_mod._load_server_configs() == {}

    def test_invalid_json_skipped(self, tool_dir):
        (tool_dir / "broken.json").write_text("{nope")
        assert tools_mod._load_server_configs() == {}

    def test_missing_env_var_skips_file(self, tool_dir, monkeypatch):
        monkeypatch.delenv("TAM_TEST_TOKEN", raising=False)
        (tool_dir / "s.json").write_text('{"headers": {"X": "{ENV:TAM_TEST_TOKEN}"}}')
        assert tools_mod._load_server_configs() == {}

    def test_env_var_substituted(self, tool_dir, monkeypatch):
        monkeypatch.setenv("TAM_TEST_TOKEN", "secret")
        (tool_dir / "web").mkdir()
        (tool_dir / "web" / "s.json").write_text(
            '{"headers": {"X": "{ENV:TAM_TEST_TOKEN}"}}'
        )
        loaded = tools_mod._load_server_configs()
        assert loaded["web/s"]["headers"]["X"] == "secret"

    def test_env_var_default_used(self, tool_dir, monkeypatch):
        monkeypatch.delenv("TAM_TEST_TOKEN", raising=False)
        (tool_dir / "web").mkdir()
        (tool_dir / "web" / "s.json").write_text(
            '{"url": "{ENV:TAM_TEST_TOKEN:-fallback}"}'
        )
        loaded = tools_mod._load_server_configs()
        assert loaded["web/s"]["url"] == "fallback"

    def test_only_file_filters(self, tool_dir):
        (tool_dir / "web").mkdir()
        (tool_dir / "web" / "a.json").write_text("{}")
        (tool_dir / "web" / "b.json").write_text("{}")
        assert list(tools_mod._load_server_configs("web/b")) == ["web/b"]


class TestConfigureTransport:
    def test_command_env_prefix_hoisted_and_shell_wrapped(self, monkeypatch):
        monkeypatch.setenv("TAM_TEST_HOME", "/home/tester")
        settings: dict[str, Any] = {
            "command": "TOKEN=abc PATH=$TAM_TEST_HOME/bin cmd --flag"
        }
        tools_mod._configure_transport(settings)
        assert settings["transport"] == "stdio"
        assert settings["env"] == {"TOKEN": "abc", "PATH": "/home/tester/bin"}
        assert settings["command"] == "sh"
        assert settings["args"] == ["-c", "cmd --flag 2>/dev/null"]

    def test_single_word_command(self, tool_dir):
        settings: dict[str, Any] = {"command": "cmd"}
        tools_mod._configure_transport(settings)
        assert settings["args"] == ["-c", "cmd 2>/dev/null"]

    def test_windows_skips_shell_wrap(self, monkeypatch):
        monkeypatch.setattr(tools_mod, "os_name", "nt")
        settings: dict[str, Any] = {"command": "cmd"}
        tools_mod._configure_transport(settings)
        assert settings["command"] == "cmd"
        assert "args" not in settings

    def test_explicit_args_kept(self, tool_dir):
        settings: dict[str, Any] = {"command": "cmd", "args": ["x"]}
        tools_mod._configure_transport(settings)
        assert settings["args"] == ["-c", "cmd x 2>/dev/null"]

    def test_sse_url_inferred_and_trailing_slash_stripped(self):
        settings: dict[str, Any] = {"url": "http://host:1/sse/"}
        tools_mod._configure_transport(settings)
        assert settings["transport"] == "sse"
        assert settings["url"] == "http://host:1/sse"

    def test_http_url_inferred(self):
        settings: dict[str, Any] = {"url": "http://host:1/mcp"}
        tools_mod._configure_transport(settings)
        assert settings["transport"] == "http"

    def test_unsupported_keys_dropped(self, capsys):
        settings: dict[str, Any] = {"command": "cmd", "nonsense": True}
        tools_mod._configure_transport(settings)
        assert "nonsense" not in settings
        assert "Ignored unsupported server option 'nonsense'" in capsys.readouterr().out

    def test_unknown_transport_drops_everything(self):
        settings: dict[str, Any] = {"weird": 1}
        tools_mod._configure_transport(settings)
        assert settings == {}


class TestProcessServerConfigs:
    def test_disable_true_removes_server(self):
        configs, filters = tools_mod._process_server_configs(
            {"s": {"command": "cmd", "disable": True}}
        )
        assert configs == {}
        assert filters == {}

    def test_filters_and_metadata_stripped(self):
        configs, filters = tools_mod._process_server_configs(
            {
                "s": {
                    "command": "cmd",
                    "disable": ["a"],
                    "enable": ["b"],
                    "edit": {"b": {"name": "c"}},
                    "description": "human text",
                }
            }
        )
        assert "description" not in configs["s"]
        assert "disable" not in configs["s"]
        assert filters["s"] == {
            "disable": ["a"],
            "enable": ["b"],
            "edit": {"b": {"name": "c"}},
        }

    def test_empty_filter_lists_skipped(self):
        configs, filters = tools_mod._process_server_configs(
            {"s": {"command": "cmd", "disable": [], "enable": "bad"}}
        )
        assert filters == {}
        assert configs["s"]["transport"] == "stdio"


class TestStripSchemaMetaKeys:
    def test_recursive_stripping(self):
        schema = {
            "$schema": "x",
            "$id": "y",
            "$comment": "z",
            "type": "object",
            "properties": {"a": {"$schema": "drop", "type": "string"}},
            "anyOf": [{"$id": "drop2", "type": "integer"}],
        }
        cleaned = tools_mod._strip_schema_meta_keys(schema)
        assert cleaned == {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "anyOf": [{"type": "integer"}],
        }

    def test_scalars_pass_through(self):
        assert tools_mod._strip_schema_meta_keys("x") == "x"


class TestApplyToolEdits:
    def test_rename_and_description(self):
        tool = make_tool("a")
        out = tools_mod._apply_tool_edits(
            tool, {"a": {"name": "b", "description": "new"}}
        )
        assert out.name == "b"
        assert out.description == "new"

    def test_partial_edit_keeps_other_field(self):
        tool = make_tool("a")
        tools_mod._apply_tool_edits(tool, {"a": {"name": "b"}})
        assert tool.description == "test tool"

    def test_no_edit_returns_same_tool(self):
        tool = make_tool("a")
        assert tools_mod._apply_tool_edits(tool, {}) is tool


class TestCacheIntrospection:
    def test_non_cacheable_tool_untouched(self, monkeypatch):
        monkeypatch.setattr(tools_mod, "_introspection_cache", {})
        tool = make_tool("other_tool")
        assert tools_mod._cache_introspection(tool) is tool

    async def test_cacheable_tool_cached_per_arguments(self, monkeypatch):
        monkeypatch.setattr(tools_mod, "_introspection_cache", {})
        calls: list[Any] = []
        tool = make_tool("list_workspaces", calls=calls)
        wrapped = tools_mod._cache_introspection(tool)
        assert wrapped is tool
        assert await tool.coroutine() == "ok"
        assert await tool.coroutine() == "ok"
        assert len(calls) == 1
        assert await tool.coroutine(extra=1) == "ok"
        assert len(calls) == 2

    def test_tool_without_coroutine_untouched(self, monkeypatch):
        monkeypatch.setattr(tools_mod, "_introspection_cache", {})
        tool = make_tool("list_workspaces")
        object.__setattr__(tool, "coroutine", None)
        assert tools_mod._cache_introspection(tool) is tool


class TestUpdateToolsComment:
    def test_comment_created_then_replaced(self, tool_dir):
        (tool_dir / "web").mkdir()
        path = tool_dir / "web" / "s.json"
        path.write_text('{"command": "cmd"}\n')
        tools_mod._update_tools_comment("web/s", ["b", "a"])
        content = path.read_text()
        assert "all found tools: 2" in content
        assert content.index("a") < content.index("b")

        tools_mod._update_tools_comment("web/s", ["c"])
        content = path.read_text()
        assert "all found tools: 1" in content
        assert "\nc" in content

    def test_missing_file_warns_without_raising(self, tool_dir, capsys):
        tools_mod._update_tools_comment("nope/no", ["x"])
        assert "Could not update tools comment" in capsys.readouterr().out


class TestLoadPythonTools:
    def test_loads_tool_functions(self, tool_dir):
        (tool_dir / "web").mkdir()
        (tool_dir / "web" / "mine.py").write_text(
            "from langchain.tools import tool\n\n\n"
            "@tool\n"
            "def my_tool(x: int) -> int:\n"
            '    """Doc."""\n'
            "    return x\n"
        )
        loaded = tools_mod._load_python_tools()
        assert list(loaded) == ["web/mine"]
        assert loaded["web/mine"][0].name == "my_tool"

    def test_template_and_underscore_skipped(self, tool_dir):
        (tool_dir / "_template.py").write_text("x = 1")
        (tool_dir / "_parked.py").write_text("x = 1")
        assert tools_mod._load_python_tools() == {}

    def test_broken_module_ignored(self, tool_dir):
        (tool_dir / "bad.py").write_text("import not_a_real_module_xyz")
        assert tools_mod._load_python_tools() == {}

    def test_only_file_filters(self, tool_dir):
        (tool_dir / "web").mkdir()
        body = (
            "from langchain.tools import tool\n\n\n"
            "@tool\n"
            "def t{x}(v: int) -> int:\n"
            '    """Doc."""\n'
            "    return v\n"
        )
        (tool_dir / "web" / "a.py").write_text(body.format(x="a"))
        (tool_dir / "web" / "b.py").write_text(body.format(x="b"))
        assert list(tools_mod._load_python_tools("web/a")) == ["web/a"]


def _patch_loader(monkeypatch, mcp_config, filters):
    monkeypatch.setattr(tools_mod, "_load_python_tools", lambda only_file=None: {})
    monkeypatch.setattr(
        tools_mod, "_load_tool_config", lambda only_file=None: (mcp_config, filters)
    )


def _patch_adapter(monkeypatch, tools_by_server, failing=()):
    calls: list[dict[str, Any]] = []

    class FakeAdapter:
        def __init__(self, target: dict[str, Any]) -> None:
            self.server = next(iter(target["mcpServers"]))
            calls.append(target["mcpServers"][self.server])

        async def list_tools(self) -> list[StructuredTool]:
            if self.server in failing:
                raise RuntimeError("adapter boom")
            return list(tools_by_server.get(self.server, []))

    monkeypatch.setattr(tools_mod, "MCPAdapter", FakeAdapter)
    return calls


class TestGetTools:
    async def test_adapter_scoped_to_single_server(self, monkeypatch):
        config = {"media/x": {"url": "http://h/mcp", "transport": "http"}}
        _patch_loader(monkeypatch, config, {})
        calls = _patch_adapter(monkeypatch, {"media/x": [make_tool("t")]})
        out = await tools_mod.get_tools(display=False)
        assert [t.name for t in out] == ["t"]
        assert calls == [config["media/x"]]

    async def test_enable_disable_and_edit_filters(self, monkeypatch):
        config = {"s": {"command": "cmd", "transport": "stdio"}}
        filters = {
            "s": {
                "enable": ["a", "b"],
                "disable": ["b"],
                "edit": {"a": {"name": "renamed", "description": "x"}},
            }
        }
        _patch_loader(monkeypatch, config, filters)
        _patch_adapter(
            monkeypatch,
            {"s": [make_tool("a"), make_tool("b"), make_tool("c")]},
        )
        out = await tools_mod.get_tools(display=False)
        assert [t.name for t in out] == ["renamed"]
        assert out[0].description == "x"

    async def test_schema_meta_keys_stripped(self, monkeypatch):
        config = {"s": {"command": "cmd", "transport": "stdio"}}
        _patch_loader(monkeypatch, config, {})
        tool = make_tool("a", schema={"$schema": "x", "type": "object"})
        _patch_adapter(monkeypatch, {"s": [tool]})
        out = await tools_mod.get_tools(display=False)
        assert out[0].args_schema == {"type": "object"}

    async def test_tools_comment_updated(self, monkeypatch):
        config = {"s": {"command": "cmd", "transport": "stdio"}}
        _patch_loader(monkeypatch, config, {})
        _patch_adapter(monkeypatch, {"s": [make_tool("a")]})
        updated: list[tuple[str, list[str]]] = []
        monkeypatch.setattr(
            tools_mod,
            "_update_tools_comment",
            lambda s, names: updated.append((s, names)),
        )
        await tools_mod.get_tools(display=False)
        assert updated == [("s", ["a"])]

    async def test_failing_server_isolated(self, monkeypatch):
        config = {
            "bad": {"command": "cmd", "transport": "stdio"},
            "good": {"command": "cmd", "transport": "stdio"},
        }
        _patch_loader(monkeypatch, config, {})
        _patch_adapter(monkeypatch, {"good": [make_tool("ok")]}, failing={"bad"})
        out = await tools_mod.get_tools(display=False)
        assert [t.name for t in out] == ["ok"]

    async def test_only_file_unknown_returns_empty(self, monkeypatch):
        _patch_loader(monkeypatch, {}, {})
        assert await tools_mod.get_tools(display=False, only_file="missing") == []

    async def test_only_file_scopes_configs(self, monkeypatch):
        config = {
            "a": {"command": "cmd", "transport": "stdio"},
            "b": {"command": "cmd", "transport": "stdio"},
        }
        _patch_loader(monkeypatch, config, {})
        calls = _patch_adapter(
            monkeypatch,
            {"a": [make_tool("ta")], "b": [make_tool("tb")]},
        )
        out = await tools_mod.get_tools(display=False, only_file="b.json")
        assert [t.name for t in out] == ["tb"]
        assert len(calls) == 1

    async def test_no_servers_returns_empty(self, monkeypatch):
        _patch_loader(monkeypatch, {}, {})
        assert await tools_mod.get_tools(display=False) == []

    async def test_python_tools_loaded_alongside(self, monkeypatch):
        config = {"s": {"command": "cmd", "transport": "stdio"}}
        monkeypatch.setattr(
            tools_mod,
            "_load_python_tools",
            lambda only_file=None: {"pytool": [make_tool("native")]},
        )
        monkeypatch.setattr(
            tools_mod, "_load_tool_config", lambda only_file=None: (config, {})
        )
        _patch_adapter(monkeypatch, {"s": [make_tool("remote")]})
        out = await tools_mod.get_tools(display=False)
        assert [t.name for t in out] == ["native", "remote"]

    async def test_display_lists_tool_names(self, monkeypatch, capsys):
        config = {"s": {"command": "cmd", "transport": "stdio"}}
        _patch_loader(monkeypatch, config, {})
        _patch_adapter(monkeypatch, {"s": [make_tool("remote")]})
        await tools_mod.get_tools(display=True)
        out = capsys.readouterr().out
        assert "Available tools: 1" in out
