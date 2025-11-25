from os import getenv, path
from shutil import copyfile
from typing import Any

from dotenv import load_dotenv
from langchain.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from pyjson5 import load  # pylint: disable=no-name-in-module
from rich.console import Console

load_dotenv()

MCP_CONFIG = getenv("MCP_CONFIG", "./config")


def get_tool_config() -> tuple[dict[str, Any], dict[str, Any]]:
    config_file = MCP_CONFIG + "/mcp_config.json"
    if not path.exists(config_file):
        print("mcp_config.json file not found: creating from example")
        copyfile("mcp_config.example.json", config_file)

    config = load(open(config_file, "r", encoding="utf-8"))
    mcp_servers = config.get("mcpServers", {})
    langchain_config, edit_config = {}, {}
    for server in mcp_servers:
        settings = mcp_servers[server]

        disabled: bool | None = settings.get("disabled")
        if disabled is not None:
            del settings["disabled"]
        if disabled:
            # Ignore disabled servers
            continue

        # stdio
        if settings.get("command"):
            command = settings.get("command").split(" ")
            if len(command) > 1 and not settings.get("args"):
                settings["command"], settings["args"] = command[0], command[1:]
            settings["transport"] = "stdio"

        # sse or streamable_http
        elif settings.get("serverUrl"):
            settings["url"] = settings["serverUrl"]
            del settings["serverUrl"]
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

    return langchain_config, edit_config


async def get_tools(display: bool = True) -> list[BaseTool]:
    config, edit_config = get_tool_config()
    if not config:
        return []

    client = MultiServerMCPClient(config)
    # Set higher timeout and disable logging callback
    for c in client.connections:
        if client.connections[c]["transport"] in [
            "sse",
            "streamable_http",
        ]:
            client.connections[c]["timeout"] = 30.0  # type: ignore
        client.connections[c]["session_kwargs"] = {
            "logging_callback": lambda *args: None
        }

    console = Console()
    tools: list[BaseTool] = []
    try:
        for server in config:
            console.print(f"[cyan]Loading tools from:[/cyan] [purple]{server}[/purple]")
            raw_tools = await client.get_tools(server_name=server)
            # Override and filter tools
            for tool in raw_tools:
                item = edit_config.get(server)
                if isinstance(item, dict):
                    edits = item.get(tool.name)
                    if isinstance(edits, dict):
                        tool.name = edits.get("name") or tool.name
                        tool.description = edits.get("description") or tool.description
                    elif edits is False:
                        continue
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
            f"- [bright_cyan][bold]{tool.name}[/bold][/bright_cyan]:\n[orange3]{tool.description}[/orange3]"
        )
