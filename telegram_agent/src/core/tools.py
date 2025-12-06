from os import getenv, mkdir, path, walk
from typing import Any

from dotenv import load_dotenv
from langchain.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from pyjson5 import load  # pylint: disable=no-name-in-module
from rich.console import Console

load_dotenv()

CONFIG_FOLDER = getenv("CONFIG_FOLDER") or "./config"
TOOLS_FOLDER = CONFIG_FOLDER + "/tools"


def get_tool_config() -> tuple[dict[str, Any], dict[str, Any], dict[str, list[str]]]:
    if not path.exists(TOOLS_FOLDER):
        mkdir(TOOLS_FOLDER)

    mcp_servers: dict[str, Any] = {}
    for root, dirs, files in walk(TOOLS_FOLDER):
        dirs[:] = [d for d in dirs if d != "examples"]
        for filename in files:
            if filename.endswith(".json") and not filename.startswith("_"):
                file_path = path.join(root, filename)
                key = filename[:-5]
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        mcp_servers[key] = load(f)
                except Exception as e:
                    print(f"Error loading {filename}: {e}")
                    exit()

    langchain_config, edit_config, disabled_config = {}, {}, {}
    for server, settings in mcp_servers.items():
        disabled = settings.get("disabled")
        if disabled:
            del settings["disabled"]
            if isinstance(disabled, list):
                disabled_config[server] = disabled
            elif isinstance(disabled, bool):
                # Ignore disabled servers
                continue

        # stdio
        if settings.get("command"):
            command = settings.get("command").split(" ")
            if len(command) > 1 and not settings.get("args"):
                settings["command"], settings["args"] = command[0], command[1:]
            settings["transport"] = "stdio"

        # sse or streamable_http
        elif settings.get("url"):
            if settings.get("url").endswith("/"):
                settings["url"] = settings["url"][:-1]
            if "/sse" in settings["url"]:
                settings["transport"] = "sse"
            elif "/mcp" in settings["url"]:
                settings["transport"] = "streamable_http"

        # To rename or disable a tool
        edits = edit_config[server] = settings.get("edit", {})
        if edits:
            del settings["edit"]
        langchain_config[server] = settings

    return langchain_config, edit_config, disabled_config


async def get_tools(display: bool = True) -> list[BaseTool]:
    config, edit_config, disabled_config = get_tool_config()
    if not config:
        return []

    client = MultiServerMCPClient(config)
    console = Console()
    tools: list[BaseTool] = []
    try:
        for server in config:
            console.print(f"[cyan]Loading tools from:[/cyan] [purple]{server}[/purple]")
            raw_tools = await client.get_tools(server_name=server)
            # Filter and override tools
            for tool in raw_tools:
                if tool.name not in disabled_config.get(server, []):
                    edits = edit_config.get(server, {}).get(tool.name)
                    if isinstance(edits, dict):
                        tool.name = edits.get("name") or tool.name
                        tool.description = edits.get("description") or tool.description
                    tools.append(tool)
    except Exception:
        console.print_exception()
        exit()

    if display:
        console.print(f"\nAvailable tools: {len(tools)}")
        if tools:
            console.print(", ".join(tool.name for tool in tools), style="bold green")
    return tools


async def print_tools() -> None:
    tools = await get_tools(display=False)
    console = Console()
    console.print(f"Available tools: {len(tools)}")
    for tool in tools:
        console.print(
            f"* [bright_cyan][bold]{tool.name}[/bold][/bright_cyan]:\n[orange3]{tool.description}[/orange3]"
        )
