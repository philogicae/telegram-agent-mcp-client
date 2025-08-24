from os import path
from shutil import copyfile
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool
from pydantic import BaseModel
from pyjson5 import load  # pylint: disable=no-name-in-module
from rich.console import Console

from .llm import LLM
from .tools import MCP_CONFIG, get_tools
from .utils import pre_model_hook

load_dotenv()


class AgentConfig(BaseModel):
    agents: list[Any]
    active: str
    tools_by_agent: dict[str, list[str]]
    transfer_instructions: dict[str, str]


def get_agent_config(
    tools: list[BaseTool], display: bool = True, verbose: bool = False
) -> AgentConfig:
    config_file = MCP_CONFIG + "/agent_config.json"
    if not path.exists(config_file):
        print("agent_config.json file not found: creating from example")
        copyfile("agent_config.example.json", config_file)

    configuration: dict[str, Any] = load(open(config_file, "r", encoding="utf-8"))
    agent_config: dict[str, Any] = configuration.get("agents", {})
    if len(agent_config) < 1:
        raise ValueError("No agents found in agent_config.json")

    # Parse common settings
    common: dict[str, Any] = configuration.get("common", {})
    guidelines: Any = common.get("guidelines", "")
    routine_guidelines: Any = ""
    default_routines: Any = {}
    if isinstance(guidelines, list) and guidelines:
        guidelines = "# Mandatory guidelines:\n- " + "\n- ".join(guidelines)
        routines: Any = common.get("routines", "")
        if isinstance(routines, dict) and routines:
            routine_guidelines = routines.get("guidelines", "")
            if isinstance(routine_guidelines, list) and routine_guidelines:
                routine_guidelines = "\n- " + "\n- ".join(routine_guidelines)
            else:
                routine_guidelines = ""
            default_routines = routines.get("default", {})
            if not isinstance(default_routines, dict):
                default_routines = {}
    else:
        guidelines = ""

    # Create handoff tools
    handoff: str = (
        common.get("handoff", "Transfer to {agent} and continue current task") + ", "
    )
    handoff_tools: list[tuple[str, BaseTool]] = []
    transfer_instructions: dict[str, str] = {}
    for name, config in agent_config.items():
        transfer = config.get("transfer")
        if transfer:
            transfer_instruction: str = handoff.format(agent=name) + transfer
            handoff_tools.append(
                (
                    name,
                    create_handoff_tool(
                        agent_name=name,
                        description=transfer_instruction,
                    ),
                )
            )
            transfer_instructions[name] = transfer_instruction
        else:
            raise ValueError(f"Missing `transfer` instruction for agent {name}")

    # Create agents
    console = Console()
    if display or verbose:
        console.print(f"\nAvailable agents: {len(agent_config)}")
    model = LLM.get()
    agents: list[Any] = []
    tools_by_agent: dict[str, list[str]] = {}
    available_tools: dict[str, BaseTool] = {tool.name: tool for tool in tools}
    for name, config in agent_config.items():
        agent_tools: list[BaseTool] = []
        if len(agent_config) > 1:
            agent_tools.extend(
                [
                    handoff_tool
                    for tool_name, handoff_tool in handoff_tools
                    if tool_name != name
                ]
            )
        if tools:
            agent_tools.extend(
                filter(
                    None,
                    [available_tools.get(tool) for tool in config.get("tools", [])],
                )
            )
        prompt = config.get("prompt", "")
        if prompt:
            prompt = f"{prompt}\n{guidelines}"
            found_routines: dict[str, Any] = {}
            if default_routines:
                found_routines.update(default_routines)
            agent_routines: Any = config.get("routines", "")
            if isinstance(agent_routines, dict) and agent_routines:
                found_routines.update(agent_routines)
            if found_routines:
                prompt += routine_guidelines + "\n# Routines:"
                for routine, specs in found_routines.items():
                    trigger = specs.get("trigger")
                    if isinstance(trigger, str) and trigger:
                        title = f"\n## {routine} ({trigger}):\n"
                        steps = specs.get("steps", "")
                        if isinstance(steps, list) and steps:
                            prompt += title + "\n".join(
                                [f"{i + 1}) {step}" for i, step in enumerate(steps)]
                            )

        agent = create_react_agent(
            model=model,
            pre_model_hook=pre_model_hook,
            name=name,
            prompt=prompt
            or f"Missing system prompt for {name}. Signal it to the user.",
            tools=agent_tools,
        )
        tools_for_agent: list[str] = [tool.name for tool in agent_tools]
        tools_by_agent[name] = tools_for_agent
        if verbose:
            all_tools = ", ".join(tools_for_agent)
            splitted_prompt = prompt.split("\n# Routines:\n")
            prompt = splitted_prompt[0]
            routines = (
                f"\n# Routines:\n[orange3]{splitted_prompt[1]}[/orange3]"
                if len(splitted_prompt) > 1
                else ""
            )
            console.print(
                f"* [bright_cyan][bold]{name}[/bold][/bright_cyan]:\n# Tools: [bright_yellow]{all_tools if all_tools else 'None'}[/bright_yellow]\n# Transfer: [purple]{transfer_instructions.get(name)}[/purple]\n# Prompt:\n[orange3]{prompt}[/orange3]{routines}"
            )
        elif display:
            all_tools = ", ".join(tools_for_agent)
            console.print(
                f"* [bright_cyan][bold]{name}[/bold][/bright_cyan]:\n[orange3]{all_tools if all_tools else 'None'}[/orange3]"
            )
        agents.append(agent)

    active: str = str(list(agent_config.keys())[0])
    if display:
        console.print(
            f"[bold][red]Active agent:[/red] [bright_cyan]{active}[/bright_cyan][/bold]"
        )
    return AgentConfig(
        agents=agents,
        active=active,
        tools_by_agent=tools_by_agent,
        transfer_instructions=transfer_instructions,
    )


async def print_agents() -> None:
    tools = await get_tools(display=False)
    get_agent_config(tools, verbose=True)
