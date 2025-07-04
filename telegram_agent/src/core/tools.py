from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from rich.console import Console

from .config import get_config


async def get_tools(display: bool = True) -> list[BaseTool]:
    config, edit_config = get_config()
    client = MultiServerMCPClient(config)
    raw_tools = await client.get_tools()
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
