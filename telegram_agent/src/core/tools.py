from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from rich.console import Console

from .config import get_config


async def get_tools() -> list[BaseTool]:
    config, edit_config = get_config()
    raw_tools = await MultiServerMCPClient(config).get_tools()
    tools: list[BaseTool] = []
    for tool in raw_tools:
        if tool.name in edit_config:
            item = edit_config[tool.name]
            if item is False:
                continue
            if item.get("name"):
                tool.name = item.get("name")
            if item.get("description"):
                tool.description = item.get("description")
        tools.append(tool)
    console = Console()
    console.print(f"\nAvailable tools: {len(tools)}")
    if tools:
        console.print(", ".join(tool.name for tool in tools), "\n", style="bold green")
    return tools
