from asyncio import get_running_loop

import nest_asyncio
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from rich.console import Console

from .config import get_config


def get_tools() -> list[BaseTool]:
    nest_asyncio.apply()  # type: ignore
    config, edit_config = get_config()
    client = MultiServerMCPClient(config)
    raw_tools = get_running_loop().run_until_complete(client.get_tools())
    tools: list[BaseTool] = []
    for tool in raw_tools:
        if tool.name in edit_config:
            item = edit_config[tool.name]
            if item is False:
                continue
            tool.name = item.get("name") or tool.name
            tool.description = item.get("description") or tool.description
        tools.append(tool)
    console = Console()
    console.print(f"\nAvailable tools: {len(tools)}")
    if tools:
        console.print(", ".join(tool.name for tool in tools), "\n", style="bold green")
    return tools
