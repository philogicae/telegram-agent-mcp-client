from time import time
from typing import Any, AsyncGenerator

from aiosqlite import connect
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.prebuilt import create_react_agent
from langgraph.store.memory import InMemoryStore
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from .config import ThinkTag
from .llm import get_llm
from .prompts import SYSTEM_PROMPT
from .tools import get_tools


async def create_short_term_memory():
    return AsyncSqliteSaver(connect("mem.sqlite"))


def create_long_term_memory():
    return InMemoryStore()


class Agent:
    agent: Any

    def __init__(self):
        """Must call initialize() after"""  # TODO: Refactor and add Langchain Swarm
        pass

    async def initialize(self) -> "Agent":
        self.agent = create_react_agent(
            name="Root Agent",
            model=get_llm(),
            tools=await get_tools(),
            prompt=SYSTEM_PROMPT,
            checkpointer=await create_short_term_memory(),
            # store=create_long_term_memory(),
            debug=False,
        )
        return self

    async def chat(self, content: Any) -> AsyncGenerator[tuple[str, bool], None]:
        console, thread_id, user = Console(), "test", None
        if isinstance(content, str):
            content = content.strip()
        elif content:  # Telegram Message
            thread_id = str(content.chat.id)
            user = content.from_user.first_name
            content = f"{user}: {content.text}".strip()
            console.print(Panel(escape(content), title="User", border_style="white"))

        if not content:
            yield "", True
        else:
            config = {"configurable": {"thread_id": thread_id}}
            total_calls, total_tokens = 0, 0
            total_agent_calls, total_tool_calls = 0, 0
            calls_by_tool = {}
            called_tool: str | None = None
            start_time, end_time = time(), time()
            async for chunk in self.agent.astream(
                {"messages": [HumanMessage(content)]},
                config,  # type: ignore
            ):
                total_calls += 1
                msg_type = "agent"
                if "tools" in chunk:
                    msg_type = "tools"
                    total_tool_calls += 1
                else:
                    total_agent_calls += 1

                msg = chunk[msg_type]["messages"][0]
                think, text, log, status = None, None, None, False
                if ThinkTag.start and ThinkTag.end and ThinkTag.start in msg.content:
                    splitted = msg.content.split(ThinkTag.start, 1)[1].split(
                        ThinkTag.end, 1
                    )
                    think, text = (
                        splitted[0].strip(),
                        splitted[1].strip() if len(splitted) > 1 else None,
                    )
                elif isinstance(msg.content, str):
                    text = msg.content.strip()

                tool_calls: str | None = None
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_calls = "\n".join(
                        [
                            f"-> {tool.get('name')}: {tool.get('args')}"
                            for tool in msg.tool_calls
                        ]
                    )
                    for tool in msg.tool_calls:
                        called_tool = tool.get("name")
                        if called_tool not in calls_by_tool:
                            calls_by_tool[called_tool] = 1
                        else:
                            calls_by_tool[called_tool] += 1

                if think:
                    console.print(
                        Panel(escape(think), title="Think", border_style="blue3")
                    )

                if text:
                    console.print(
                        Panel(
                            escape(text),
                            title="Result" if called_tool else "Agent",
                            border_style=("green3" if called_tool else "bright_cyan"),
                        )
                    )
                    if called_tool:
                        called_tool = None
                        log, status = (
                            ("✅" if called_tool != "think" else None),
                            False,
                        )
                    else:
                        log, status = text, True

                if tool_calls:
                    console.print(
                        Panel(escape(tool_calls), title="Tools", border_style="red")
                    )
                    log, status = (
                        (
                            f"🛠️ **{called_tool}** invoked..."
                            if called_tool != "think"
                            else "🔍 Analyzing..."
                        ),
                        False,
                    )

                if log:
                    yield log.replace("`", "'"), status

                if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                    timer = time() - end_time
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
            console.print(
                Panel(
                    escape(
                        f"total_calls: {total_calls} | agent_calls: {total_agent_calls} | tool_calls: {total_tool_calls}{(' (' + ', '.join([k + ': ' + str(v) for k, v in calls_by_tool.items()]) + ')') if calls_by_tool else ''} | total_tokens: {total_tokens} | took: {end_time - start_time:.2f} sec."
                    ),
                    title="Usage Summary",
                    border_style="yellow",
                )
            )

    async def cli_chat(self, content: str) -> None:
        async for _ in self.chat(content):
            pass


async def run_agent() -> None:
    agent = await Agent().initialize()
    content = ""

    # content = "Find magnet link of the last adaptation of Berserk"
    # content = "Check torrent list and get statuses"
    # content = "trouve le premier film gladiator"

    if content:
        print(f"> {content}")
    while True:
        try:
            content = (content or input("> ")).strip()
            if not content:
                exit()
            await agent.cli_chat(content)
            content = ""
        except KeyboardInterrupt:
            exit()
