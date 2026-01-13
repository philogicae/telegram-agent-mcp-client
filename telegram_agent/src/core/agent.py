from datetime import datetime
from os import getenv
from typing import Any, AsyncGenerator, Callable, Sequence

from addict import Dict
from dotenv import load_dotenv
from langchain.messages import AnyMessage, HumanMessage
from langchain.tools import BaseTool
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.types import StateSnapshot
from langgraph_swarm import create_swarm
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from telebot.types import Message as TelegramMessage

from ..utils import Timer
from .config import get_agent_config
from .graphiti import GraphRAG
from .tools import get_tools
from .utils import (
    Flag,
    Usage,
    checkpointer,
    filter_relevant_memories,
    format_called_tool,
    pre_agent_hook,
    summarize_and_rephrase,
)

load_dotenv()

# Configuration
CONFIG_DIR = getenv("CONFIG") or "./config"
WHITELIST: set[str] = set(getenv("WHITELIST", "").lower().split(","))


class Agent:
    agents: Dict = Dict()
    tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | ToolNode | None
    graph: GraphRAG | Any
    console: Console
    dev: bool
    debug: bool

    def __init__(
        self,
        tools: (
            Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | ToolNode | None
        ) = None,
        graph: GraphRAG | None = None,
        persist: bool = False,
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
        self.graph = graph
        self.console = Console()
        self.dev = dev
        self.debug = debug

        # Default Agents
        default = self.agents.default = Dict()
        default.config = get_agent_config(all_tools)
        default.active = {}
        default.agent = create_swarm(
            agents=default.config.agents,
            default_active_agent=default.config.active,
        ).compile(checkpointer=checkpointer(dev, persist), debug=debug)
        if generate_png:
            graph_file = CONFIG_DIR + "/default_graph.png"
            default.agent.get_graph().draw_mermaid_png(output_file_path=graph_file)
            print(f"Default Graph saved to {graph_file}")

        # Only Documentalist
        documentalist = self.agents.documentalist = Dict()
        documentalist.config = get_agent_config(
            all_tools, only_agents=["Documentalist"], config_name="Restricted"
        )
        documentalist.agent = create_swarm(
            agents=documentalist.config.agents,
            default_active_agent=documentalist.config.active,
        ).compile(checkpointer=checkpointer(dev, persist), debug=debug)
        if generate_png:
            graph_file = CONFIG_DIR + "/documentalist_graph.png"
            documentalist.agent.get_graph().draw_mermaid_png(
                output_file_path=graph_file
            )
            print(f"Documentalist Graph saved to {graph_file}")

        if generate_png:
            exit()

    def __enter__(self) -> "Agent":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        pass

    @staticmethod
    async def load_graph() -> GraphRAG:
        return await GraphRAG().init()

    @staticmethod
    async def load_tools() -> list[BaseTool]:
        return await get_tools()

    @staticmethod
    async def init(
        dev: bool = False,
        enable_graph: bool = True,
        enable_tools: bool = True,
        enable_persist: bool = False,
        debug: bool = False,
        generate_png: bool = False,
    ) -> "Agent":
        graph = (await Agent.load_graph()) if enable_graph else None
        tools = (await Agent.load_tools()) if enable_tools else None
        return Agent(tools, graph, enable_persist, dev, debug, generate_png)

    def state(self, swarm: Any, thread_id: str) -> StateSnapshot:
        state: StateSnapshot = swarm.agent.get_state(
            {"configurable": {"thread_id": thread_id}}
        )
        return state

    async def chat(
        self, content: str | TelegramMessage | Any
    ) -> AsyncGenerator[tuple[str, str, bool, dict[str, str]], None]:
        thread_id, user = "test", "User"
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(content, str):
            content = content.strip()
        elif isinstance(content, TelegramMessage):
            thread_id = str(content.chat.id)
            if content.from_user:
                user = content.from_user.first_name
            content = (content.text or "").strip()
            self.console.print(
                Panel(escape(content), title="👤 User", border_style="white")
            )

        swarm = (
            self.agents.default
            if not WHITELIST or user.lower() in WHITELIST
            else self.agents.documentalist  # Restricted to Documentalist for public tests
        )
        if thread_id not in swarm.active:
            swarm.active[thread_id] = swarm.config.active

        if not content:
            yield (
                swarm.active[thread_id],
                "...?",
                True,
                {},
            )  # Avoid empty reply
        else:
            content = f"{user}: {content}"
            messages: list[AnyMessage] = []
            filtered_memories: str = ""
            if self.graph:
                mem_timer = Timer()
                recontext = summarize_and_rephrase(
                    self.state(swarm, thread_id), content
                )
                summary = (
                    f"Chat Summary: {recontext.summary}"
                    if recontext.summary and recontext.summary != "None"
                    else ""
                )
                if summary:
                    messages = pre_agent_hook(
                        self.state(swarm, thread_id).values,
                        remove_all=True,
                        max_tokens=2000,
                    ).get("messages", [])
                    messages.append(HumanMessage("# " + summary))
                content = (
                    recontext.user_message
                    if ":" in recontext.user_message
                    else f"{user}: {recontext.user_message}"
                )
                recontext_logs = f"{summary}\n{content}" if summary else content
                self.console.print(
                    Panel(
                        escape(recontext_logs),
                        title=f"💡 ReContext ({mem_timer.done()})",
                        border_style="light_steel_blue1",
                    )
                )
                mem_timer = Timer()
                found_memories = await self.graph.full_search(
                    content, user, thread_id, limit=10
                )
                mem_stats = found_memories["stats"]
                memories = f"{found_memories['nodes']}{found_memories['edges']}".strip()
                if memories:
                    mem_timer = Timer()
                    filtered_memories = filter_relevant_memories(
                        memories, recontext.summary, content
                    )
                    if filtered_memories:
                        messages.append(
                            HumanMessage("# Episodic Memory:\n" + filtered_memories)
                        )
                        # mem_stats["edges"] = filtered_memories.count("EDG<")
                        # mem_stats["nodes"] = filtered_memories.count("NOD<")
                        # del mem_stats["episodes"]
                        self.console.print(
                            Panel(
                                escape(f"{mem_stats}\n{filtered_memories}"),
                                title=f"🧠 Episodic Memory ({mem_timer.done()})",
                                border_style="light_steel_blue1",
                            )
                        )

            messages.append(HumanMessage(f"[{date}] {content}"))
            config: Any = {
                "configurable": {"thread_id": thread_id},
                "max_concurrency": 1,
                "recursion_limit": 100,
            }
            total_agent_calls, total_tool_calls = 0, 0
            calls_by_tool: dict[str, int] = {}
            timers_by_tool: dict[str, Timer] = {}
            called_tool: str | None = None
            called_tool_timer: Timer | None = None
            ignore_tool_result: bool = False
            start_time = end_time = datetime.now().timestamp()
            usage: Usage = Usage()
            forced_messages: list[AnyMessage] = []
            final, retry = False, 0
            while not final:
                async for _, chunk in swarm.agent.astream(
                    {"messages": forced_messages or messages}, config, subgraphs=True
                ):
                    msg_type = "model"
                    msg: Any = None
                    if "model" in chunk:
                        msg = chunk[msg_type]["messages"][-1]
                        if not msg.tool_calls:
                            total_agent_calls += 1
                        called_tool, called_tool_timer = None, None
                    elif "tools" in chunk:
                        msg_type = "tools"
                        msg = chunk[msg_type]["messages"][-1]
                        if hasattr(msg, "name") and msg.name:
                            called_tool = msg.name
                            called_tool_timer = timers_by_tool.get(called_tool)
                    else:
                        continue

                    # Content
                    text: Any = None
                    if isinstance(msg.content, str):
                        text = msg.content.strip()
                    elif isinstance(msg.content, list):
                        for item in msg.content:
                            if isinstance(item, str):
                                text = item.strip()
                            elif isinstance(item, dict) and "text" in item:
                                text = item["text"].strip()

                    """ if "</think>" in text:  # Ollama Qwen3
                        splitted = text.split("<think>", 1)[1].split("</think>", 1)
                        think, text = splitted[0].strip(), splitted[1].strip()
                        self.console.print(
                            Panel(escape(think), title="💭 Think", border_style="white")
                        ) """

                    # Tools
                    tool_calls: Any = None
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        listed = []
                        for tool in msg.tool_calls:
                            total_tool_calls += 1
                            called_tool = tool.get("name")
                            called_tool_timer = timers_by_tool[called_tool] = Timer()
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
                    elif (
                        msg_type == "model"
                        and called_tool
                        and called_tool
                        not in swarm.config.tools_by_agent.get(
                            swarm.active[thread_id], []
                        )
                    ):
                        self.console.print(
                            Panel(
                                escape(
                                    f"{swarm.active[thread_id]}: Invalid tool '{called_tool}'"
                                ),
                                title="❌ Tool Error",
                                border_style="red",
                            )
                        )
                        ignore_tool_result = True
                        continue

                    # Logging
                    step: str = ""
                    done: bool = False
                    extra: dict[str, str] = {}

                    if text:
                        if not text.startswith(
                            "Thread purpose:"
                        ):  # Ignore think tool result
                            self.console.print(
                                Panel(
                                    escape(text),
                                    title=(
                                        "🛠️ Result"
                                        + (
                                            f" ({called_tool_timer.done()})"
                                            if called_tool_timer
                                            else ""
                                        )
                                        if msg_type == "tools"
                                        else f"🤖 {swarm.active[thread_id]}"
                                    ),
                                    border_style=(
                                        "green3"
                                        if msg_type == "tools"
                                        else "bright_cyan"
                                    ),
                                )
                            )
                        if msg_type == "tools":  # Yield tool result
                            if (
                                called_tool
                                and called_tool not in ["think"]
                                and not str(called_tool).startswith("transfer_to_")
                            ):
                                step = "✅"
                                sample = text.lower()[:50]
                                for flag in Flag:
                                    if flag.value in sample:
                                        step = "❌"
                                        break
                                if called_tool_timer:
                                    step += f" {called_tool_timer.done()}"
                                extra = {"tool": called_tool, "output": text}
                        else:  # Final result
                            step, done = text, True

                    if tool_calls:
                        if str(called_tool).startswith(
                            "transfer_to_"
                        ):  # Call transfer tools
                            self.console.print(
                                Panel(
                                    escape(tool_calls),
                                    title="🔁 Transfer",
                                    border_style="purple",
                                )
                            )
                            step, done = (
                                f"🔁 {format_called_tool(called_tool)}",
                                False,
                            )
                            swarm.active[thread_id] = (
                                str(called_tool)[12:].replace("_", " ").title().strip()
                            )
                        elif called_tool in ["think"]:  # Call think tool
                            self.console.print(
                                Panel(
                                    escape(tool_calls),
                                    title=(
                                        "💭 Think"
                                        if called_tool == "think"
                                        else "📝 Todos"
                                    ),
                                    border_style="hot_pink",
                                )
                            )
                        else:  # Call regular tools
                            self.console.print(
                                Panel(
                                    escape(tool_calls),
                                    title="🛠️ Tool",
                                    border_style="red",
                                )
                            )
                            step = f"🛠️ {format_called_tool(called_tool)}..."

                    # Usage
                    if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                        timer = datetime.now().timestamp() - end_time
                        end_time += timer
                        usage.add_usage(msg.usage_metadata)
                        self.console.print(
                            Panel(
                                escape(
                                    " | ".join(
                                        [
                                            f"{k}: {v}"
                                            for k, v in msg.usage_metadata.items()
                                        ]
                                    )
                                ),
                                title=f"📊 Usage ({timer:.2f} sec)",
                                border_style="yellow",
                            )
                        )

                    # Intermediate step
                    if step and not done:
                        if self.dev:
                            step_text, step_timer = step, ""
                            if step and step[0] in "✅❌":
                                step_text, step_timer = step.split(" ", 1)
                            intermediate_step = (
                                f"{swarm.active[thread_id]} -> YIELD: {step_text}"
                            )
                            if extra:
                                intermediate_step += f" {extra['tool']} {step_timer}"
                            self.console.print(intermediate_step)
                        yield swarm.active[thread_id], step, False, extra

                # Usage Summary
                self.console.print(
                    Panel(
                        escape(
                            f"{usage}\ntotal_calls: {total_agent_calls + total_tool_calls} | agent_calls: {total_agent_calls} | tool_calls: {total_tool_calls}{(' (' + ', '.join([k + ': ' + str(v) for k, v in calls_by_tool.items()]) + ')') if calls_by_tool else ''}"
                        ),
                        title=f"📊 Usage Summary ({end_time - start_time:.2f} sec)",
                        border_style="bright_yellow",
                    )
                )

                # Avoid interruptions
                if retry < 3:
                    retry += 1
                    forced_messages = []
                    end_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    state_values = self.state(swarm, thread_id).values
                    if not state_values.get("messages"):
                        state_values["messages"] = []
                    last_messages = state_values["messages"]
                    before_last_msg = last_messages[-2]
                    if (
                        before_last_msg.type == "tool"
                        and before_last_msg.name.startswith("transfer_to_")
                        and (not step or len(step) < 50)
                    ):  # Avoid stop after transfer
                        last_messages.pop()
                        forced_messages.append(
                            HumanMessage(
                                f"[{end_date}] SYSTEM ALERT: It seems you interrupted in the middle of your process after BECOMING the new agent. Agent delegation doesn't exist, you have to continue by yourself. Resume your process, without mentioning this alert message."
                            )
                        )
                        self.console.print(
                            Panel(
                                escape("ALERT: Stopped after transfer"),
                                title="↩ Back on Track",
                                border_style="medium_violet_red",
                            )
                        )
                        continue
                    if not step or step[0] in "✅❌":  # Avoid empty reply
                        last_messages.pop()
                        forced_messages.append(
                            HumanMessage(
                                f"[{end_date}] SYSTEM ALERT: It seems you interrupted in the middle of your process without providing a final reply to the user. Resume your process and reply, without mentioning this alert message."
                            )
                        )
                        self.console.print(
                            Panel(
                                escape("ALERT: Empty reply"),
                                title="↩ Back on Track",
                                border_style="medium_violet_red",
                            )
                        )
                        continue
                if not step or step[0] in "✅❌":  # Avoid empty reply when retry >= 3
                    step = "The same internal error occurred 3 times in a row... Please try again."

                # Final step
                if self.dev:
                    self.console.print(
                        f"{swarm.active[thread_id]} -> FINAL: "
                        + (
                            f"{step[:21]}...{step[-21:]}"
                            if step and len(step) > 45
                            else step
                        )
                    )

                # Exit safe loop
                final = True
                yield swarm.active[thread_id], step, True, extra

                # Add memories to graph
                if self.graph and step:
                    mem_timer = Timer()
                    results = await self.graph.add(
                        content=[
                            (
                                user,
                                content[len(user) + 2 :].strip(),  # Remove '<user>: '
                            ),
                            (swarm.active[thread_id], step),
                        ],
                        chat_id=thread_id,
                    )
                    self.console.print(
                        Panel(
                            escape(
                                f"{results['stats']}"
                                + results["nodes"]
                                + results["edges"]
                            ),
                            title=f"💾 Added Memories ({mem_timer.done()})",
                            border_style="light_steel_blue1",
                        )
                    )


async def run_agent(dev: bool = False, generate_png: bool = False) -> None:
    content = ""
    with await Agent.init(dev=True, generate_png=generate_png) as agent:
        if content:
            print(f"> {content}")
        while True:
            try:
                content = (content or input("> ")).strip()
                if not content:
                    break
                async for _, step, done, _ in agent.chat(content):
                    if dev and step and not done:
                        input("Press enter to continue...")
                content = ""
            except KeyboardInterrupt:
                break
