from datetime import datetime
from os import makedirs
from re import sub
from typing import Any, AsyncGenerator, Callable, Sequence

from aiosqlite import connect
from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.store.memory import InMemoryStore
from langgraph_swarm import create_handoff_tool, create_swarm
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from telebot.types import Message as TelegramMessage

from .config import Flag  # , ThinkTag
from .llm import get_llm
from .prompts import BOT_NAME, SYSTEM_PROMPT
from .tools import get_tools


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


def checkpointer(dev: bool = False) -> BaseCheckpointSaver:  # type: ignore
    if dev:
        return InMemorySaver()
    data_folder = "/app/data"
    makedirs(data_folder, exist_ok=True)
    return AsyncSqliteSaver(connect(f"{data_folder}/checkpointer.sqlite"))


def store() -> InMemoryStore:
    return InMemoryStore()


class Agent:
    agent: CompiledStateGraph[Any]
    dev: bool
    debug: bool
    tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | ToolNode | None

    def __init__(
        self,
        tools: (
            Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | ToolNode | None
        ) = None,
        dev: bool = False,
        debug: bool = False,
    ) -> None:
        jesus = create_react_agent(
            name="Jesus",
            model=get_llm(),
            tools=[
                create_handoff_tool(
                    agent_name=BOT_NAME,
                    description=f"Transfer to {BOT_NAME} for any request not related to religion.",
                )
            ],
            prompt="You are Jesus Christ, the Savior of the world. You can only answer questions related to religion.",
            pre_model_hook=pre_model_hook,
        )
        handoff = create_handoff_tool(
            agent_name="Jesus",
            description="Transfer to Jesus for any request related to religion.",
        )
        agent_tools: list[Any] = [handoff]
        if tools:
            if isinstance(tools, list):
                agent_tools.extend(tools)
            else:
                agent_tools.append(tools)
        agent = create_react_agent(
            name=BOT_NAME,
            model=get_llm(),
            tools=agent_tools,
            prompt=SYSTEM_PROMPT,
            pre_model_hook=pre_model_hook,
        )
        self.agent = create_swarm(
            [agent, jesus], default_active_agent=BOT_NAME
        ).compile(checkpointer=checkpointer(dev), debug=debug)
        self.tools = tools
        self.dev = dev
        self.debug = debug

    def __enter__(self) -> "Agent":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        pass

    @staticmethod
    async def load_tools() -> list[BaseTool]:
        return await get_tools()

    @staticmethod
    async def init_with_tools(dev: bool = False, debug: bool = False) -> "Agent":
        tools = await Agent.load_tools()
        return Agent(tools, dev, debug)

    async def chat(
        self, content: str | TelegramMessage | Any
    ) -> AsyncGenerator[tuple[str, bool, dict[str, str]], None]:
        console, thread_id, user = Console(), "test", None
        if isinstance(content, str):
            content = content.strip()
        elif isinstance(content, TelegramMessage):
            thread_id = str(content.chat.id)
            user = content.from_user.first_name if content.from_user else "User"
            date = datetime.fromtimestamp(content.date).strftime("%Y-%m-%d %H:%M:%S")
            content = f"[{date}] {user}: {content.text}".strip()
            console.print(Panel(escape(content), title="User", border_style="white"))

        if not content:
            yield "...", True, {}  # Avoid empty reply
        else:
            config = {
                "configurable": {"thread_id": thread_id},
                "max_concurrency": 1,
                "recursion_limit": 100,
            }
            total_calls, total_tokens = 0, 0
            total_agent_calls, total_tool_calls = 0, 0
            calls_by_tool: dict[str, int] = {}
            called_tool: str | None = None
            start_time, end_time = (
                datetime.now().timestamp(),
                datetime.now().timestamp(),
            )
            async for namespace, chunk in self.agent.astream(
                {"messages": [HumanMessage(content)]},
                config,  # type: ignore
                subgraphs=True,
            ):
                total_calls += 1
                msg_type = "agent"
                if "agent" in chunk:
                    total_agent_calls += 1
                    called_tool = None
                elif "tools" in chunk:
                    msg_type = "tools"
                    total_tool_calls += 1
                else:
                    continue
                msg = chunk[msg_type]["messages"][0]

                # Think and Text
                text = None
                # think = None
                """ if ThinkTag.start and ThinkTag.end and ThinkTag.start in msg.content:
                    splitted = msg.content.split(ThinkTag.start, 1)[1].split(
                        ThinkTag.end, 1
                    )
                    think, text = (
                        splitted[0].strip(),
                        splitted[1].strip() if len(splitted) > 1 else None,
                    ) """
                if isinstance(msg.content, list):
                    for item in msg.content:
                        if isinstance(item, str):
                            text = item.strip()
                        elif isinstance(item, dict) and "text" in item:
                            text = item["text"].strip()
                elif isinstance(msg.content, str):
                    text = msg.content.strip()

                # Tools
                tool_calls: str | None = None
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    listed = []
                    for tool in msg.tool_calls:
                        called_tool = tool.get("name")
                        calls_by_tool[called_tool] = (
                            calls_by_tool.get(called_tool, 0) + 1
                        )
                        tool_args = tool.get("args")
                        tool_details = f": {tool_args}" if tool_args else ""
                        listed.append(f"-> {called_tool}{tool_details}")
                    tool_calls = "\n".join(listed)

                # Logging
                step: str = ""
                done: bool = False
                extra: dict[str, str] = {}

                """ if think:
                    console.print(
                        Panel(escape(think), title="Think", border_style="blue3")
                    ) """

                if text:
                    console.print(
                        Panel(
                            escape(text),
                            title="Result" if msg_type == "tools" else msg_type.title(),
                            border_style=(
                                "green3" if msg_type == "tools" else "bright_cyan"
                            ),
                        )
                    )
                    if msg_type == "tools":
                        if called_tool and called_tool != "think":
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
                    console.print(
                        Panel(escape(tool_calls), title="Tools", border_style="red")
                    )
                    if called_tool and called_tool != "think":
                        step = f"🛠️  **{sub('_|-', ' ', str(called_tool)).title()}**..."

                # Usage
                if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                    timer = datetime.now().timestamp() - end_time
                    end_time += timer
                    total_tokens += msg.usage_metadata.get("total_tokens", 0)
                    console.print(
                        Panel(
                            escape(
                                " | ".join(
                                    [f"{k}: {v}" for k, v in msg.usage_metadata.items()]
                                    + [f"took: {timer:.2f} sec."]
                                )
                            ),
                            title="Usage",
                            border_style="purple",
                        )
                    )

                # Intermediate step
                if step and not done:
                    if self.dev:
                        intermediate_step = f"-> YIELD: {step}"
                        if extra:
                            intermediate_step += f" {extra['tool']}"
                        console.print(intermediate_step)
                    yield step, False, extra

            # Usage Summary
            console.print(
                Panel(
                    escape(
                        f"total_calls: {total_calls} | agent_calls: {total_agent_calls} | tool_calls: {total_tool_calls}{(' (' + ', '.join([k + ': ' + str(v) for k, v in calls_by_tool.items()]) + ')') if calls_by_tool else ''} | total_tokens: {total_tokens} | took: {end_time - start_time:.2f} sec."
                    ),
                    title="Usage Summary",
                    border_style="yellow",
                )
            )

            # Final step
            if not step:
                step = "..."  # Avoid empty reply
            elif step in "✅❌" and text:
                step = str(text)
            if self.dev:
                console.print(
                    "-> FINAL: "
                    + (
                        f"{step[:21]}...{step[-21:]}"
                        if step and len(step) > 45
                        else step
                    )
                )
            yield step, True, extra


async def run_agent(dev: bool = False) -> None:
    content = ""
    with await Agent.init_with_tools(dev=True) as agent:
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
