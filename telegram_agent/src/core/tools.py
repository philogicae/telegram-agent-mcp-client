from os import getenv, path
from shutil import copyfile
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import BaseTool
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

        # Ignore disabled servers
        if settings.get("disabled"):
            continue
        del settings["disabled"]

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
            if settings["url"].endswith("/sse"):
                settings["transport"] = "sse"
            elif settings["url"].endswith("/mcp"):
                settings["transport"] = "streamable_http"

        # To rename or disable a tool
        if settings.get("edit"):
            edit_config.update(settings.get("edit"))
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

    try:
        raw_tools = await client.get_tools()
    except Exception:
        Console().print_exception()
        exit()

    # Override tools
    tools: list[BaseTool] = []
    for tool in raw_tools:
        if tool.name in edit_config:
            item = edit_config[tool.name]
            if item is False:
                continue
            tool.name = item.get("name") or tool.name
            tool.description = item.get("description") or tool.description
        tools.append(tool)

    if display:
        console = Console()
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
