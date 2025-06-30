from datetime import datetime
from os import makedirs
from re import sub
from typing import Any, AsyncGenerator

from aiosqlite import connect
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.prebuilt import create_react_agent
from langgraph.store.memory import InMemoryStore
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from telebot.types import Message as TelegramMessage

from .config import ThinkTag
from .llm import get_llm
from .prompts import SYSTEM_PROMPT
from .tools import get_tools


def create_short_term_memory() -> AsyncSqliteSaver:
    makedirs("tmp", exist_ok=True)
    return AsyncSqliteSaver(connect("tmp/mem.sqlite"))


def create_long_term_memory() -> InMemoryStore:
    return InMemoryStore()


class Agent:
    def __init__(self) -> None:
        self.agent = create_react_agent(  # TODO: Swarm agents
            name="Root Agent",
            model=get_llm(),
            tools=get_tools(),
            prompt=SYSTEM_PROMPT,
            checkpointer=create_short_term_memory(),
            store=create_long_term_memory(),
            debug=False,
        )

    async def chat(
        self, content: str | TelegramMessage | Any
    ) -> AsyncGenerator[tuple[str, bool], None]:
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
            yield "", True
        else:
            config = {"configurable": {"thread_id": thread_id}}
            total_calls, total_tokens = 0, 0
            total_agent_calls, total_tool_calls = 0, 0
            calls_by_tool: dict[str, int] = {}
            called_tool: str | None = None
            start_time, end_time = (
                datetime.now().timestamp(),
                datetime.now().timestamp(),
            )
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

                # Think and Text
                think, text = None, None
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

                if text:
                    text = text.replace("\n* ", "\n- ").replace(
                        "**", "*"
                    )  # Fix for Telegram Markdown

                # Tools
                tool_calls: str | None = None
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    listed = []
                    for tool in msg.tool_calls:
                        called_tool = tool.get("name")
                        calls_by_tool[called_tool] = (
                            calls_by_tool.get(called_tool, 0) + 1
                        )
                        listed.append(f"-> {called_tool}: {tool.get('args')}")
                    tool_calls = "\n".join(listed)

                # Logging
                log, status = "", False

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
                        if called_tool != "think":
                            log = "✅"
                        called_tool = None
                    else:
                        log, status = text, True

                if tool_calls:
                    console.print(
                        Panel(escape(tool_calls), title="Tools", border_style="red")
                    )
                    if called_tool != "think":
                        log = f"🛠️ *{sub('_|-', ' ', str(called_tool)).title()}*..."

                if not status:
                    print(f"-> YIELD: {log if log else 'EMPTY'}")
                    yield log, status

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
            nicer_log = f"{log[:21]}...{log[-21:]}" if log and len(log) > 45 else log
            print(f"-> FINAL: {nicer_log}")
            yield log, status

    async def cli_chat(self, content: str, debug: bool = False) -> None:
        async for step, done in self.chat(content):
            if debug and step:
                text = f"{step[:21]}...{step[-21:]}" if len(step) > 45 else step
                print(f'Done: {done} | Step: "{text}"')
                input("continue...")


async def run_agent(dev: bool = False) -> None:
    agent = Agent()
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
            await agent.cli_chat(content, debug=dev)
            content = ""
        except KeyboardInterrupt:
            exit()
