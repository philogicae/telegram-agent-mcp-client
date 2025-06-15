from os import getenv, path
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models import LanguageModelLike
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pyjson5 import load  # pylint: disable=no-name-in-module
from rich import print as pr

load_dotenv()


def get_config() -> Any:
    config_file = path.join(  # TODO: Change config structure
        path.dirname(path.dirname(path.dirname(__file__))), "mcp_config.json"
    )
    if not path.exists(config_file):
        print("mcp_config.json file not found: creating a empty one")
        with open(config_file, "w", encoding="utf-8") as f:
            f.write("{}")
    return load(open(config_file, "r", encoding="utf-8"))


def get_llm() -> LanguageModelLike:
    return (
        ChatOllama(
            base_url=getenv("OLLAMA_API_BASE"),
            model=getenv("OLLAMA_API_MODEL"),  # type: ignore
            disable_streaming=True,
            num_thread=1,
            temperature=0.6,
            top_p=0.95,
            top_k=20,
            num_ctx=6144,  # 2Go VRAM APU
            num_predict=2048,
        )
        if getenv("LLM_CHOICE") == "ollama"
        else ChatOpenAI(
            base_url=getenv("OPENAI_API_BASE"),
            api_key=getenv("OPENAI_API_KEY"),  # type: ignore
            model=getenv("OPENAI_API_MODEL"),  # type: ignore
            disable_streaming=True,
        )
    )


class ThinkTag:
    start = getenv("THINK_TAG_START")
    end = getenv("THINK_TAG_END")


async def run_agent() -> None:
    tools = await MultiServerMCPClient(get_config()).get_tools()
    agent = create_react_agent(
        name="General Agent",
        model=get_llm(),
        tools=tools,
        prompt=None,  # TODO: Change system prompts
        checkpointer=None,
        store=None,
        debug=False,
    )

    # user_input = "Using think tool, give me a smart strategy to get rich in 10 years"
    user_input = "Find torrent for: berserk"
    while True:
        try:
            print("------------ USERS ------------")
            if user_input:
                print(f"> {user_input}")
            user_input = user_input or input("> ")
            if user_input.lower() == "exit":
                break
            async for chunk in agent.astream(
                {"messages": [HumanMessage(content=user_input)]}
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
                else:
                    text = msg.content.strip() or None

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
