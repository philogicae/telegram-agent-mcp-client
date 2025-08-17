from enum import Enum
from json import dump
from os import getenv, path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool
from pydantic import BaseModel
from pyjson5 import load  # pylint: disable=no-name-in-module
from rich.console import Console

from .llm import get_llm

load_dotenv()


class Flag(Enum):
    _ERROR = " error"
    ERROR_ = "error "
    _FAILED = " failed"
    FAILED_ = "failed "


def get_tool_config() -> tuple[dict[str, Any], dict[str, Any]]:
    config_file = getenv("MCP_CONFIG", "./config") + "/mcp_config.json"
    if not path.exists(config_file):
        print("mcp_config.json file not found: creating a empty one")
        with open(config_file, "w", encoding="utf-8") as f:
            dump({"mcpServers": {}}, f, indent=2)

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


def pre_model_hook(state: dict[str, Any]) -> dict[str, Any]:
    trimmed_messages = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=10000,
        start_on="human",
        end_on=("human", "tool"),
    )
    return {"llm_input_messages": trimmed_messages}


class AgentConfig(BaseModel):
    agents: list[Any]
    active: str


def get_agent_config(tools: list[BaseTool], display: bool = True) -> AgentConfig:
    config_file = getenv("MCP_CONFIG", "./config") + "/agent_config.json"
    if not path.exists(config_file):
        print("agent_config.json file not found: creating a empty one")
        with open(config_file, "w", encoding="utf-8") as f:
            dump(
                {
                    "agents": {
                        "Agent": {
                            "prompt": "You are an ultra smart helpful agent. You are empowered with a set of useful tools, but you can only call one at a time.",
                            "tools": ["think"],
                        }
                    }
                },
                f,
                indent=2,
            )

    agent_config: dict[str, Any] = load(open(config_file, "r", encoding="utf-8")).get(
        "agents"
    )
    if len(agent_config) < 1:
        raise ValueError("No agents found in agent_config.json")

    available_tools: dict[str, BaseTool] = {tool.name: tool for tool in tools}
    handoff_tools: list[tuple[str, BaseTool]] = []
    for name, config in agent_config.items():
        handoff = config.get("handoff")
        if handoff:
            handoff_tools.append(
                (
                    name,
                    create_handoff_tool(
                        agent_name=name,
                        description=handoff,
                    ),
                )
            )

    console = Console()
    if display:
        console.print(f"\nAvailable agents: {len(agent_config)}")
    model = get_llm()
    agents: list[Any] = []
    for name, config in agent_config.items():
        agent_tools: list[BaseTool] = []
        if len(agent_config) > 1:
            agent_tools.extend(
                [
                    handoff_tool
                    for _, handoff_tool in handoff_tools
                    if handoff_tool.name != name
                ]
            )
        if tools:
            agent_tools.extend(
                filter(
                    None,
                    [available_tools.get(tool) for tool in config.get("tools", [])],
                )
            )
        agent = create_react_agent(
            model=model,
            pre_model_hook=pre_model_hook,
            name=name,
            prompt=config.get(
                "prompt", f"Missing system prompt for {name}. Signal it to the user."
            ),
            tools=agent_tools,
        )
        if display:
            console.print(
                f"- [bright_cyan][bold]{name}[/bold][/bright_cyan]: [orange3]{', '.join(tool.name for tool in agent_tools)}[/orange3]"
            )
        agents.append(agent)

    active: str = str(list(agent_config.keys())[0])
    if display:
        console.print(f"Active agent: {active}")
    return AgentConfig(agents=agents, active=active)
