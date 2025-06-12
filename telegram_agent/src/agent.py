from json import load
from os import getenv, path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

load_dotenv()
BASE_URL = getenv("OPENAI_API_BASE")
API_KEY: Any = getenv("OPENAI_API_KEY")
MODEL = getenv("OPENAI_API_MODEL")
if not BASE_URL:
    raise ValueError("OPENAI_API_BASE environment variable is not set")
if not API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")
if not MODEL:
    raise ValueError("OPENAI_API_MODEL environment variable is not set")

llm = ChatOpenAI(
    base_url=BASE_URL, api_key=API_KEY, model=MODEL, disable_streaming="tool_calling"
)

config = load(
    open(
        path.join(
            path.dirname(path.dirname(path.dirname(__file__))), "mcp_config.json"
        ),
        "r",
        encoding="utf-8",
    )
)


async def run_agent() -> None:
    client = MultiServerMCPClient(config)
    tools = await client.get_tools()
    agent = create_react_agent(llm, tools)
    while True:
        try:
            user_input = input("Prompt: ")
            print("-------------------")
            if user_input.lower() == "exit":
                break
            async for chunk in agent.astream(
                {"messages": [HumanMessage(content=user_input)]}, config
            ):
                if "agent" in chunk:
                    msg = chunk["agent"]["messages"][0].content.strip()
                    if msg:
                        print(f"------ AGENT ------\n{msg}\n-------------------")
                elif "tools" in chunk:
                    msg = chunk["tools"]["messages"][0].content.strip()
                    if msg:
                        print(f"------ TOOLS ------\n{msg}\n-------------------")
        except KeyboardInterrupt:
            exit(0)
