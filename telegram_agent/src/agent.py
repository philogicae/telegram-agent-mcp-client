from datetime import datetime

from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from .config import ThinkTag, get_config
from .llm import get_llm


async def run_agent() -> None:
    console = Console()
    tools = await MultiServerMCPClient(get_config()).get_tools()
    agent = create_react_agent(
        name="General Agent",
        model=get_llm(),
        tools=tools,
        prompt="You are a helpful agent, ready to have casual and funny conversations with the user. During your interactions, you are empowered with some tools. For example, you can find torrents. If someone asks you to do something you can't do with your available tools, joke about it. Have fun chatting!",
        checkpointer=MemorySaver(),
        store=None,
        debug=False,
    )
    config = {"configurable": {"thread_id": "abc123"}}
    while True:
        try:
            print("------------ USERS ------------")
            user_input = input("> ")
            start_time, end_time = datetime.now(), datetime.now()
            if user_input.lower() == "exit":
                break
            async for chunk in agent.astream(
                {"messages": [HumanMessage(content=user_input)]},
                config,  # type: ignore
            ):
                msg_type = "agent"
                if "tools" in chunk:
                    msg_type = "tools"

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

                print(f"------------ {msg_type.upper()} ------------")
                if think:
                    console.print(
                        Panel(escape(think), title="Think", border_style="blue")
                    )
                if text:
                    console.print(
                        Panel(escape(text), title="Text", border_style="green")
                    )
                if tool_calls:
                    console.print(
                        Panel(escape(tool_calls), title="Tools", border_style="red")
                    )
                if hasattr(msg, "usage_metadata"):
                    timer = datetime.now() - end_time
                    end_time += timer
                    console.print(
                        Panel(
                            "\n".join(
                                [f"{k}: {v}" for k, v in msg.usage_metadata.items()]
                                + [f"Time: {timer.total_seconds()} seconds"]
                            ),
                            title="Usage",
                            border_style="purple",
                        )
                    )
            print(f"Total time: {(end_time - start_time).total_seconds()} seconds")
        except KeyboardInterrupt:
            exit(0)
