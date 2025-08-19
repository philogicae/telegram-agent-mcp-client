from datetime import datetime
from os import getenv, makedirs
from re import sub
from typing import Any, AsyncGenerator, Callable, Sequence

from aiosqlite import connect
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt.tool_node import ToolNode
from langgraph_swarm import create_swarm
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from telebot.types import Message as TelegramMessage

from .config import AgentConfig, get_agent_config
from .tools import get_tools
from .utils import Flag, Usage

load_dotenv()


def checkpointer(dev: bool = False) -> BaseCheckpointSaver:  # type: ignore
    if dev:
        return InMemorySaver()
    data_folder = "/app/data"
    makedirs(data_folder, exist_ok=True)
    return AsyncSqliteSaver(connect(f"{data_folder}/checkpointer.sqlite"))


class Agent:
    agent_config: AgentConfig
    agent: CompiledStateGraph[Any]
    tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | ToolNode | None
    tools_by_agent: dict[str, list[str]]
    console: Console
    dev: bool
    debug: bool

    def __init__(
        self,
        tools: (
            Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | ToolNode | None
        ) = None,
        dev: bool = False,
        debug: bool = False,
        generate_png: bool = False,
    ) -> None:
        all_tools: list[Any] = []
        if tools:
            if isinstance(tools, list):
                all_tools.extend(tools)
            else:
                all_tools.append(tools)
        self.tools = all_tools
        self.console = Console()
        self.dev = dev
        self.debug = debug
        self.agent_config = get_agent_config(all_tools)
        self.tools_by_agent = self.agent_config.tools_by_agent
        self.agent = create_swarm(
            agents=self.agent_config.agents,
            default_active_agent=self.agent_config.active,
        ).compile(checkpointer=checkpointer(dev), debug=debug)
        if generate_png:
            graph_file = getenv("MCP_CONFIG", "./config") + "/graph.png"
            self.agent.get_graph().draw_mermaid_png(output_file_path=graph_file)
            print(f"Graph saved to {graph_file}")
            exit()

    def __enter__(self) -> "Agent":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        pass

    @staticmethod
    async def load_tools() -> list[BaseTool]:
        return await get_tools()

    @staticmethod
    async def init_with_tools(
        dev: bool = False, debug: bool = False, generate_png: bool = False
    ) -> "Agent":
        tools = await Agent.load_tools()
        return Agent(tools, dev, debug, generate_png)

    async def chat(
        self, content: str | TelegramMessage | Any
    ) -> AsyncGenerator[tuple[str, bool, dict[str, str]], None]:
        thread_id, user = "test", None
        if isinstance(content, str):
            content = content.strip()
        elif isinstance(content, TelegramMessage):
            thread_id = str(content.chat.id)
            user = content.from_user.first_name if content.from_user else "User"
            date = datetime.fromtimestamp(content.date).strftime("%Y-%m-%d %H:%M:%S")
            content = f"[{date}] {user}: {content.text}".strip()
            self.console.print(
                Panel(escape(content), title="User", border_style="white")
            )

        if not content:
            yield "...", True, {}  # Avoid empty reply
        else:
            config = {
                "configurable": {"thread_id": thread_id},
                "max_concurrency": 1,
                "recursion_limit": 100,
            }
            current_agent: Any = None
            total_agent_calls, total_tool_calls = 0, 0
            calls_by_tool: dict[str, int] = {}
            called_tool: str | None = None
            ignore_tool_result: bool = False
            start_time = end_time = datetime.now().timestamp()
            usage: Usage = Usage()
            async for _, chunk in self.agent.astream(
                {"messages": [HumanMessage(content)]},
                config,  # type: ignore
                subgraphs=True,
            ):
                msg_type = "agent"
                msg: Any = None
                if "agent" in chunk:
                    msg = chunk[msg_type]["messages"][0]  # type: ignore
                    current_agent = msg.name.title() if msg.name else "Agent"
                    if not msg.tool_calls:
                        total_agent_calls += 1
                    called_tool = None
                elif "tools" in chunk:
                    msg_type = "tools"
                    msg = chunk[msg_type]["messages"][0]  # type: ignore
                else:
                    continue

                # Content
                text = None
                if isinstance(msg.content, list):
                    for item in msg.content:
                        if isinstance(item, str):
                            text = item.strip()
                        elif isinstance(item, dict) and "text" in item:
                            text = item["text"].strip()
                elif isinstance(msg.content, str):
                    text = msg.content.strip()

                # Tools
                tool_calls: Any = None
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    listed = []
                    for tool in msg.tool_calls:
                        total_tool_calls += 1
                        called_tool = tool.get("name")
                        calls_by_tool[called_tool] = (
                            calls_by_tool.get(called_tool, 0) + 1
                        )
                        tool_args = tool.get("args")
                        tool_details = f": {tool_args}" if tool_args else ""
                        listed.append(f"-> {called_tool}{tool_details}")
                    tool_calls = "\n".join(listed)

                # Ignore invalid tools
                if ignore_tool_result:
                    ignore_tool_result = False
                    continue
                elif called_tool and called_tool not in self.tools_by_agent.get(
                    current_agent, []
                ):
                    ignore_tool_result = True
                    continue

                # Logging
                step: str = ""
                done: bool = False
                extra: dict[str, str] = {}

                if text:
                    self.console.print(
                        Panel(
                            escape(text),
                            title="Result" if msg_type == "tools" else current_agent,
                            border_style=(
                                "green3" if msg_type == "tools" else "bright_cyan"
                            ),
                        )
                    )
                    if msg_type == "tools":  # Yield Tool result
                        if (
                            called_tool
                            and called_tool != "think"
                            and not str(called_tool).startswith("transfer_to_")
                        ):
                            step = "✅"
                            sample = text.lower()[:50]
                            for flag in Flag:
                                if flag.value in sample:
                                    step = "❌"
                                    break
                            extra = {"tool": called_tool, "output": text}
                    else:
                        step, done = text, True

                if tool_calls:
                    if str(called_tool).startswith(
                        "transfer_to_"
                    ):  # Call transfer tools
                        self.console.print(
                            Panel(
                                escape(tool_calls),
                                title="Transfer",
                                border_style="purple",
                            )
                        )
                        step, done = (
                            f"🔁  _{sub('_|-', ' ', str(called_tool)).title()}_",
                            False,
                        )
                    else:  # Call regular tools
                        self.console.print(
                            Panel(escape(tool_calls), title="Tools", border_style="red")
                        )
                        if called_tool and called_tool != "think":
                            step = (
                                f"🛠️  _{sub('_|-', ' ', str(called_tool)).title()}_..."
                            )

                # Usage
                if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                    timer = datetime.now().timestamp() - end_time
                    end_time += timer
                    usage.add_usage(msg.usage_metadata)
                    self.console.print(
                        Panel(
                            escape(
                                " | ".join(
                                    [f"{k}: {v}" for k, v in msg.usage_metadata.items()]
                                    + [f"took: {timer:.2f} sec."]
                                )
                            ),
                            title="Usage",
                            border_style="yellow",
                        )
                    )

                # Intermediate step
                if step and not done:
                    if self.dev:
                        intermediate_step = f"-> YIELD: {step}"
                        if extra:
                            intermediate_step += f" {extra['tool']}"
                        self.console.print(intermediate_step)
                    yield step, False, extra

            # Usage Summary
            self.console.print(
                Panel(
                    escape(
                        f"{usage}\ntotal_calls: {total_agent_calls + total_tool_calls} | agent_calls: {total_agent_calls} | tool_calls: {total_tool_calls}{(' (' + ', '.join([k + ': ' + str(v) for k, v in calls_by_tool.items()]) + ')') if calls_by_tool else ''} | took: {end_time - start_time:.2f} sec."
                    ),
                    title="Usage Summary",
                    border_style="bright_yellow",
                )
            )

            # Final step
            if not step:
                step = "..."  # Avoid empty reply
            elif step in "✅❌" and text:
                step = str(text)
            if self.dev:
                self.console.print(
                    "-> FINAL: "
                    + (
                        f"{step[:21]}...{step[-21:]}"
                        if step and len(step) > 45
                        else step
                    )
                )
            yield step, True, extra


async def run_agent(dev: bool = False, generate_png: bool = False) -> None:
    content = ""
    with await Agent.init_with_tools(dev=True, generate_png=generate_png) as agent:
        if content:
            print(f"> {content}")
        while True:
            try:
                content = (content or input("> ")).strip()
                if not content:
                    break
                async for step, done, _ in agent.chat(content):
                    if dev and step and not done:
                        input("Press enter to continue...")
                content = ""
            except KeyboardInterrupt:
                break
