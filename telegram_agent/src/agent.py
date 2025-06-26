from datetime import datetime

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from .config import ThinkTag
from .llm import get_llm
from .tools import get_tools


async def run_agent() -> None:
    console = Console()
    agent = create_react_agent(
        name="General Agent",
        model=get_llm(),
        tools=await get_tools(),
        prompt="You are an ultra smart helpful agent. You are empowered with a set of useful tools, but you can only call one at a time. Always use think tool to fulfill user's request step by step. Don't assume you know something when you actually don't know, don't hesitate to check the web to confirm information, and don't ask obvious questions to user.",
        checkpointer=MemorySaver(),
        store=None,
        debug=False,
    )

    user_input = ""
    # user_input = "Find magnet link of the last adaptation of Berserk"
    # user_input = "Check torrent list"
    config = {"configurable": {"thread_id": "test"}}
    called_tools = False
    while True:
        try:
            user_input = user_input or input("> ")
            if not user_input or user_input.lower() == "exit":
                exit(0)
            total_calls, total_tokens = 0, 0
            total_agent_calls, total_tool_calls = 0, 0
            named_tool_calls = {}
            start_time, end_time = datetime.now(), datetime.now()
            async for chunk in agent.astream(
                {"messages": [HumanMessage(content=user_input)]},
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

                tool_calls: str | None = None
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_calls = "\n".join(
                        [
                            f"-> {tool.get('name')}: {tool.get('args')}"
                            for tool in msg.tool_calls
                        ]
                    )
                    for tool in msg.tool_calls:
                        called_tools = True
                        tool_name = tool.get("name")
                        if tool_name not in named_tool_calls:
                            named_tool_calls[tool_name] = 1
                        else:
                            named_tool_calls[tool_name] += 1

                if think:
                    console.print(
                        Panel(escape(think), title="Think", border_style="blue3")
                    )
                if text:
                    console.print(
                        Panel(
                            escape(text),
                            title="Result" if called_tools else "Agent",
                            border_style=("green3" if called_tools else "bright_cyan"),
                        )
                    )
                    if called_tools:
                        called_tools = False
                if tool_calls:
                    console.print(
                        Panel(escape(tool_calls), title="Tools", border_style="red")
                    )
                if hasattr(msg, "usage_metadata"):
                    timer = datetime.now() - end_time
                    end_time += timer
                    total_tokens += msg.usage_metadata.get("total_tokens", 0)
                    console.print(
                        Panel(
                            escape(
                                " | ".join(
                                    [f"{k}: {v}" for k, v in msg.usage_metadata.items()]
                                    + [f"took: {timer.total_seconds()} sec."]
                                )
                            ),
                            title="Usage",
                            border_style="purple",
                        )
                    )
            console.print(
                Panel(
                    escape(
                        f"total_calls: {total_calls} | agent_calls: {total_agent_calls} | tool_calls: {total_tool_calls}{(' (' + ', '.join([k + ': ' + str(v) for k, v in named_tool_calls.items()]) + ')') if named_tool_calls else ''} | total_tokens: {total_tokens} | took: {(end_time - start_time).total_seconds()} sec."
                    ),
                    title="Usage Summary",
                    border_style="yellow",
                )
            )
            user_input = ""
        except KeyboardInterrupt:
            exit(0)
