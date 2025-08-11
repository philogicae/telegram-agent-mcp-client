from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from rich.console import Console

from .config import get_config


async def get_tools(display: bool = True) -> list[BaseTool]:
    config, edit_config = get_config()
    if not config:
        return []

    client = MultiServerMCPClient(config)
    # Set higher timeout and disable logging callback
    for c in client.connections:
        if client.connections[c]["transport"] in [
            "sse",
            "streamable_http",
        ]:
            client.connections[c]["timeout"] = 30.0
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
            console.print(
                ", ".join(tool.name for tool in tools), "\n", style="bold green"
            )
    return tools


async def run_tools() -> None:
    tools = await get_tools(display=False)
    console = Console()
    console.print(f"Available tools: {len(tools)}")
    for tool in tools:
        console.print(
            f"- [bright_cyan][bold]{tool.name}[/bold][/bright_cyan]:\n[orange3]{tool.description}[/orange3]"
        )
