"""MCP tool configuration and loading."""

from importlib.util import module_from_spec, spec_from_file_location
from inspect import getmembers
from os import getenv
from pathlib import Path
from re import DOTALL
from re import compile as re_compile
from re import sub
from typing import Any, TypeAlias

from dotenv import load_dotenv
from langchain.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from pyjson5 import loads  # pylint: disable=no-name-in-module
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

load_dotenv()

# Type aliases
ServerConfig: TypeAlias = dict[str, Any]
ToolFilterConfig: TypeAlias = dict[str, dict[str, Any]]
ToolConfig: TypeAlias = tuple[ServerConfig, ToolFilterConfig]
ENV_NOT_FOUND = "ENV_NOT_FOUND"

# Configuration
TOOL_DIR = Path(getenv("CONFIG", "./config")) / "tools"
_console = Console()


def _replace_env_var(match: Any) -> str:
    """Replace environment variables in tool config."""
    env_name = match.group(1)
    return getenv(env_name) or ENV_NOT_FOUND


def _load_server_configs(only_file: str | None = None) -> ServerConfig:
    """Load all JSON server configuration files."""
    servers: ServerConfig = {}

    for filepath in TOOL_DIR.rglob("*.json"):
        server_name = filepath.stem
        server_path = f"{filepath.parent.name}/{server_name}"
        if only_file and server_path != only_file:
            continue
        if server_name.startswith("_"):
            _console.print(f"Ignored '{server_path}': Excluded", style="orange3")
            continue
        try:
            with filepath.open(encoding="utf-8") as f:
                content = f.read()
                content = sub(r"\{ENV:(\w+)\}", _replace_env_var, content)
                if ENV_NOT_FOUND in content:
                    _console.print(
                        f"Ignored '{server_path}': Missing environment variable",
                        style="orange3",
                    )
                    continue
                servers[server_path] = loads(content)
        except Exception:
            _console.print(
                f"Ignored '{server_path}': Error loading file", style="orange3"
            )

    return servers


def _configure_transport(settings: ServerConfig) -> None:
    """Configure transport type based on settings."""
    if command := settings.get("command"):
        parts = command.split()
        if len(parts) > 1 and not settings.get("args"):
            settings["command"] = parts[0]
            settings["args"] = parts[1:]
        settings["transport"] = "stdio"
    elif url := settings.get("url"):
        settings["url"] = url.rstrip("/")
        settings["transport"] = "sse" if "/sse" in url else "streamable_http"


def _process_server_configs(mcp_servers: ServerConfig) -> ToolConfig:
    """Process server configs into langchain format."""
    langchain_config: ServerConfig = {}
    filter_config: ToolFilterConfig = {}

    for server, settings in mcp_servers.items():
        server_filters: dict[str, list[str] | bool] = {}

        # Handle disable servers/tools
        disable = settings.pop("disable", None)
        if disable is True:
            # Server completely disabled, skip adding to langchain_config
            continue
        if disable and isinstance(disable, list):
            server_filters["disable"] = disable

        # Handle enable tools
        enable = settings.pop("enable", None)
        if enable and isinstance(enable, list):
            server_filters["enable"] = enable

        # Handle edit configuration
        edit = settings.pop("edit", {})
        if edit and isinstance(edit, dict):
            server_filters["edit"] = edit

        # Store filters if any exist
        if server_filters:
            filter_config[server] = server_filters

        _configure_transport(settings)
        langchain_config[server] = settings

    return langchain_config, filter_config


def _load_tool_config(only_file: str | None = None) -> ToolConfig:
    """Load all tool configuration files from TOOL_DIR."""
    TOOL_DIR.mkdir(parents=True, exist_ok=True)
    mcp_servers = _load_server_configs(only_file)
    return _process_server_configs(mcp_servers)


def _load_python_tools(only_file: str | None = None) -> dict[str, list[BaseTool]]:
    """Import Python files from config/tools and list their methods."""
    py_tools: dict[str, list[BaseTool]] = {}

    for filepath in TOOL_DIR.rglob("*.py"):
        filename = filepath.stem
        server_path = f"{filepath.parent.name}/{filename}"
        if only_file and server_path != only_file:
            continue
        module_name = f"config_tools_{filename}"
        if filename == "_template":
            continue
        if filename.startswith("_"):
            _console.print(f"Ignored '{server_path}': Excluded", style="orange3")
            continue

        try:
            spec = spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                _console.print(
                    f"Ignored '{server_path}': Could not create spec", style="orange3"
                )
                continue

            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            for _, tool in getmembers(module):
                if isinstance(tool, BaseTool):
                    if filename not in py_tools:
                        _console.print(
                            f"[cyan]Loading tools from:[/cyan] [yellow]{server_path}[/yellow] [dim](pytool)[/dim]"
                        )
                        py_tools[server_path] = []
                    py_tools[server_path].append(tool)
        except Exception as e:
            _console.print(
                f"Ignored '{server_path}': Error importing - {e}", style="orange3"
            )

    return py_tools


def _apply_tool_edits(tool: BaseTool, edits: dict[str, str]) -> BaseTool:
    """Apply name/description overrides to a tool."""
    tool_edits = edits.get(tool.name)
    if isinstance(tool_edits, dict):
        tool.name = tool_edits.get("name", tool.name)
        tool.description = tool_edits.get("description", tool.description)
    return tool


def _update_tools_comment(server: str, tool_names: list[str]) -> None:
    """Update <server>.json file with a comment listing all available tools."""
    try:
        filepath = TOOL_DIR / Path(f"{server}.json")
        with filepath.open(encoding="utf-8") as f:
            content = f.read()

        # Check if tools comment already exists
        tools_comment_pattern = r"/\*\s*all found tools:.*?\*/"
        all_tools = "\n".join(sorted(tool_names))
        new_comment = f"/* all found tools: {len(tool_names)}\n{all_tools} */"

        if "all found tools:" in content:
            # Replace existing comment - use a more precise pattern
            pattern = re_compile(tools_comment_pattern, DOTALL)
            content = pattern.sub(new_comment, content)
        else:
            # Add comment at the end
            content = content.rstrip() + f"\n{new_comment}\n"

        with filepath.open("w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        _console.print(
            f"[orange3]Warning: Could not update tools comment for {filepath.name}: {e}[/orange3]"
        )


async def get_tools(
    display: bool = True, only_file: str | None = None
) -> list[BaseTool]:
    """Load and configure all available MCP tools."""
    tools: list[BaseTool] = []
    only_file = only_file.rstrip(".json").rstrip(".py") if only_file else None
    py_tools = _load_python_tools(only_file)
    mcp_config, mcp_filter_config = _load_tool_config(only_file)

    if only_file:
        if only_file not in mcp_config and only_file not in py_tools:
            _console.print(
                f"Error: Server '{only_file}' not found in configuration", style="red"
            )
            return []
        elif only_file in mcp_config:
            mcp_config = {only_file: mcp_config[only_file]}

    if not mcp_config and not py_tools:
        return []

    if py_tools:
        tools.extend([tool for tools in py_tools.values() for tool in tools])

    if mcp_config:
        client = MultiServerMCPClient(mcp_config)
        for server, config in mcp_config.items():
            try:
                _console.print(
                    f"[cyan]Loading tools from:[/cyan] [yellow]{server}[/yellow] [dim]({config['transport']})[/dim]"
                )
                raw_tools = await client.get_tools(server_name=server)

                # Update server.json with tools list if needed
                if server in mcp_config:
                    _update_tools_comment(server, [tool.name for tool in raw_tools])

                # Filter tools based on enable/disable/edit
                server_filters = mcp_filter_config.get(server, {})
                enabled_tools = server_filters.get("enable", [])
                disabled_tools = server_filters.get("disable", [])
                edit_config = server_filters.get("edit", {})
                filtered_tools = []
                for tool in raw_tools:
                    if disabled_tools and tool.name in disabled_tools:
                        continue
                    if enabled_tools and tool.name not in enabled_tools:
                        continue
                    filtered_tools.append(tool)
                tools.extend(
                    _apply_tool_edits(tool, edit_config) for tool in filtered_tools
                )
            except Exception as e:
                _console.print(f"{e}\n[red]Error loading tools from: {server}[/red]")

    if display:
        _console.print(f"Available tools: {len(tools)}")
        if tools:
            _console.print(", ".join(t.name for t in tools), style="bold green")

    return tools


async def print_tools(only_file: str | None = None) -> None:
    """Display detailed information about all available tools."""
    tools = await get_tools(display=False, only_file=only_file)
    content = Text()
    for tool in tools:
        content.append("• ", style="magenta")
        content.append(tool.name, style="bold bright_white")
        content.append(f"\n{tool.description}\n\n", style="dim")
    content.rstrip()
    _console.print(
        Panel(
            content,
            title=f"Available Tools ({len(tools)})",
            border_style="magenta",
        )
    )
