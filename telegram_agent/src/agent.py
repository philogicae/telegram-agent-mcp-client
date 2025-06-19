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

    # user_input = "Using think tool, give me a smart strategy to get rich in 10 years"
    user_input = "Find torrent for berserk"
    while True:
        try:
            print("------------ USERS ------------")
            if user_input:
                print(f"> {user_input}")
            user_input = user_input or input("> ")
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
                    think, text = msg.content.split(ThinkTag.start, 1)[1].split(
                        ThinkTag.end, 1
                    )
                    think, text = think.strip() or None, text.strip() or None
                elif isinstance(msg.content, str):
                    text = msg.content.strip() or None

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
                    console.print(
                        Panel(
                            "\n".join(
                                [f"{k}: {v}" for k, v in msg.usage_metadata.items()]
                            ),
                            title="Usage",
                            border_style="purple",
                        )
                    )
                user_input = ""
        except KeyboardInterrupt:
            exit(0)
