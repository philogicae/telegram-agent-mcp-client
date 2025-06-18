from typing import Any

from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from rich import print as pr

from .config import ThinkTag, get_config
from .llm import get_llm


async def run_agent() -> None:
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
                elif isinstance(msg.content, list):
                    for content in msg.content:
                        if "thinking" in content:
                            think = content["thinking"].strip() or None
                        else:
                            pr(content)
                            pr("-> Unknown content")
                            exit()

                tool_calls: list[tuple[str, Any]] | None = None
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_calls = [
                        (tool.get("name"), tool.get("args")) for tool in msg.tool_calls
                    ]

                pr(
                    f"------------ {msg_type.upper()} ------------"
                    + "\n> think:"
                    + ("\n" if think else " ")
                    + f"{think}"
                    + "\n> text:"
                    + ("\n" if text else " ")
                    + f"{text}"
                    + "\n> tools:"
                    + ("\n" if tool_calls else " ")
                    + f"{tool_calls}"
                )
                user_input = ""
        except KeyboardInterrupt:
            exit(0)
