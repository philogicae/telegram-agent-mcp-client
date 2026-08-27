"""Agent implementation for orchestrating LLM interactions."""

import sys
from base64 import b64encode
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from json import JSONDecodeError, loads
from os import getenv
from pathlib import Path
from typing import Any, ClassVar, Self
from uuid import uuid4

from addict import Dict
from dotenv import load_dotenv
from langchain.messages import AnyMessage, HumanMessage
from langchain.tools import BaseTool
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.types import StateSnapshot
from langgraph_swarm import create_swarm
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from telebot.types import Message as TelegramMessage

from ..utils import Timer, extract_response
from .config import get_agent_config
from .tools import get_tools
from .utils import (
    Flag,
    Usage,
    checkpointer,
    format_called_tool,
    pre_agent_hook,
    summarize_and_rephrase,
)

load_dotenv()

CONFIG_DIR = getenv("CONFIG") or "./config"


def _media_blocks(media: list[dict]) -> list[dict]:
    """Convert internal media dicts into multimodal content blocks.

    Internal format is {'type': 'media', 'data': bytes, 'mime_type': ...};
    raw bytes are not JSON-serializable and every chat integration expects
    its own block shape, so encode to base64 here — the single choke point
    before HumanMessage construction. Images use image_url data URLs
    (spoken by both langchain-openai and langchain-google-genai).
    """
    blocks: list[dict] = []
    for m in media:
        data = m.get("data")
        mime = m.get("mime_type", "")
        if not isinstance(data, bytes):
            blocks.append(m)
            continue
        b64 = b64encode(data).decode()
        # ponytail: audio uses OpenAI input_audio (ogg unsupported there);
        # google wants inline_data — split when an stt main model lands
        if mime.startswith("audio/"):
            fmt = mime.split("/", 1)[1].split(";")[0]
            blocks.append(
                {"type": "input_audio", "input_audio": {"data": b64, "format": fmt}}
            )
        else:
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            )
    return blocks


class Agent:
    """Agent class for managing LLM interactions and tool execution."""

    agents: Dict = Dict()
    tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | ToolNode | None
    console: Console
    dev: bool
    debug: bool
    user_config: dict[str, Any]
    thread_mappings: ClassVar[dict[str, str]] = {}

    def __init__(
        self,
        tools: (
            Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | ToolNode | None
        ) = None,
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
        self.console = Console()
        self.dev = dev
        self.debug = debug

        # Load user config
        user_config_path = Path(CONFIG_DIR) / "user_config.json"
        self.user_config = {}
        if user_config_path.exists():
            with user_config_path.open() as f:
                self.user_config = loads(f.read())

        # Create swarm per group from user config
        for group_name, group_config in self.user_config.items():
            if group_name in self.agents:
                continue
            group_agents = group_config.get("agents") or []
            config = get_agent_config(
                all_tools,
                only_agents=group_agents or None,
                config_name=group_name.title(),
            )
            if not config:
                continue
            swarm = self.agents[group_name] = Dict()
            swarm.config = config
            swarm.active = {}
            swarm.agent = create_swarm(
                agents=swarm.config.agents,
                default_active_agent=swarm.config.active,
            ).compile(checkpointer=checkpointer(dev, persist), debug=debug)
            if generate_png:
                graph_file = f"{CONFIG_DIR}/{group_name}_graph.png"
                swarm.agent.get_graph().draw_mermaid_png(output_file_path=graph_file)
                print(f"{group_name} Graph saved to {graph_file}")

        if generate_png:
            sys.exit()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        pass

    @staticmethod
    async def load_tools() -> list[BaseTool]:
        return await get_tools()

    @staticmethod
    async def init(
        dev: bool = False,
        enable_tools: bool = True,
        enable_persist: bool = False,
        debug: bool = False,
        generate_png: bool = False,
    ) -> Agent:
        tools = (await Agent.load_tools()) if enable_tools else None
        return Agent(tools, enable_persist, dev, debug, generate_png)

    def state(self, swarm: Any, thread_id: str) -> StateSnapshot:
        state: StateSnapshot = swarm.agent.get_state(
            {"configurable": {"thread_id": thread_id}}
        )
        return state

    def is_allowed(self, user: str) -> bool:
        """Check if a user is listed in any group (admin or allowed)."""
        user_lower = user.lower()
        for group_cfg in self.user_config.values():
            for u in group_cfg.get("users", []):
                if u.lower() == user_lower:
                    return True
        return False

    async def chat(
        self, content: str | TelegramMessage | Any
    ) -> AsyncGenerator[tuple[str, str, bool, dict[str, Any]]]:
        thread_id, user = "test", "Developer"
        chat_prefix = ""
        date = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        media: list[dict] = []
        if isinstance(content, str):
            content = content.strip()
        elif isinstance(content, TelegramMessage):
            thread_id = str(content.chat.id)
            chat_prefix = f"[chat_id:{thread_id}]"
            if content.from_user:
                user = content.from_user.first_name
            media = getattr(content, "media", [])
            content = (content.text or "").strip()
            self.console.print(
                Panel(escape(content), title="👤 User", border_style="white")
            )

        # Resolve thread_id mapping (for checkpoint jumps after ReContext)
        base_thread_id = thread_id
        thread_id = self.thread_mappings.get(base_thread_id, base_thread_id)

        # Determine user group from config; reject unknown users silently
        user_lower = user.lower()
        group: str | None = None
        for name, group_cfg in self.user_config.items():
            for u in group_cfg.get("users", []):
                if u.lower() == user_lower:
                    group = name
                    break
            if group:
                break
        if group is None:
            # Relay-injected messages (message_id 0, token-authed) don't carry a
            # configured sender: route to the group already handling this chat's
            # thread, falling back to the first configured group.
            if isinstance(content, TelegramMessage) and content.message_id == 0:
                group = next(
                    (
                        g
                        for g, s in self.agents.items()
                        if thread_id in getattr(s, "active", {})
                    ),
                    next(iter(self.user_config), None),
                )
            if group is None:
                return  # Unknown user: no reply

        swarm = getattr(self.agents, group, None)
        if swarm is None or not getattr(swarm, "agent", None):
            return  # Group has no valid config: no reply
        if thread_id not in swarm.active:
            swarm.active[thread_id] = swarm.config.active

        if not content and not media:
            yield (
                swarm.active[thread_id],
                "...?",
                True,
                {},
            )  # Avoid empty reply
        else:
            content = f"{user}: {content}" if content else f"{user}: [media]"
            messages: list[AnyMessage] = []

            # ReContext — skip for media-only messages or short conversations
            # Threshold 200k: Gemini 3.x has 1M context, implicit caching makes
            # old tokens 75-90% cheaper, so keep history intact as long as possible
            state = self.state(swarm, thread_id)
            history_msgs = state.values.get("messages", [])
            history_tokens = count_tokens_approximately(history_msgs)
            is_media_only = content.endswith(("[media]", "[voice message]"))
            if is_media_only or history_tokens < 100000:
                recontext_logs = content
            else:
                mem_timer = Timer()
                recontext = await summarize_and_rephrase(state, content)
                summary = (
                    f"Chat Summary: {recontext.summary}"
                    if recontext.summary and recontext.summary != "None"
                    else ""
                )
                if summary:
                    # Jump to new thread_id for clean checkpoint + fresh LLM cache prefix
                    messages = pre_agent_hook(
                        state.values,
                        max_tokens=2000,
                    ).get("messages", [])
                    messages.append(HumanMessage("# " + summary))
                    new_thread_id = f"{base_thread_id}:{uuid4().hex[:8]}"
                    self.thread_mappings[base_thread_id] = new_thread_id
                    swarm.active[new_thread_id] = swarm.active.pop(thread_id)
                    thread_id = new_thread_id
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
            if media:
                messages.append(
                    HumanMessage(
                        content=[
                            {
                                "type": "text",
                                "text": f"{chat_prefix}[{date}] {content}",
                            },
                            *_media_blocks(media),
                        ]
                    )
                )
            else:
                messages.append(HumanMessage(f"{chat_prefix}[{date}] {content}"))
            config: Any = {
                "configurable": {"thread_id": thread_id},
                "max_concurrency": 4,
                "recursion_limit": 100,
            }
            total_agent_calls, total_tool_calls = 0, 0
            calls_by_tool: dict[str, int] = {}
            timers_by_tool: dict[str, Timer] = {}
            called_tool: str | None = None
            called_tool_timer: Timer | None = None
            ignore_tool_result: bool = False
            tool_block: dict[str, str] = {}  # tool name -> live status line
            start_time = end_time = datetime.now(UTC).timestamp()
            usage: Usage = Usage()
            forced_messages: list[AnyMessage] = []
            pending_images: list[str] = []
            extra: dict[str, Any] = {}
            final, retry = False, 0
            while not final:
                pending_images.clear()
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
                    text, reasoning = extract_response(msg)
                    if reasoning:
                        self.console.print(
                            Panel(
                                escape(reasoning),
                                title=f"🧠 {swarm.active[thread_id]} Reasoning",
                                border_style="grey50",
                            )
                        )

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
                    extra: dict[str, Any] = {}

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
                                and called_tool != "think"
                                and not str(called_tool).startswith("transfer_to_")
                            ):
                                result: Any = None
                                with suppress(JSONDecodeError, TypeError):
                                    result = loads(text)
                                if isinstance(result, dict):
                                    pending_images.extend(
                                        result[key]
                                        for key in ("graph_path", "image_path")
                                        if result.get(key)
                                    )
                                if isinstance(result, dict) and result.get("timeout"):
                                    elapsed = (
                                        called_tool_timer.done()
                                        if called_tool_timer
                                        else result.get("timeout_at", "?")
                                    )
                                    step = f"🔸 {format_called_tool(called_tool)}: Timeout after {elapsed}"
                                    extra["tool_ok"] = None  # Timeout: not an error
                                else:
                                    step = "✅"
                                    sample = text.lower()[:50]
                                    for flag in Flag:
                                        if flag.value in sample:
                                            step = "❌"
                                            break
                                    step += f" {format_called_tool(called_tool)}"
                                    if called_tool_timer:
                                        step += f": {called_tool_timer.done()}"
                                    extra["tool_ok"] = step.startswith("✅")
                                if called_tool in tool_block:
                                    tool_block[called_tool] = step
                                    step = "\n".join(tool_block.values())
                                    extra["tool_block"] = True
                                extra["tool"] = called_tool
                                extra["output"] = text
                        elif not tool_calls:  # Final result
                            step, done = text, True
                        elif (
                            msg_type == "model"
                        ):  # Explanatory text alongside tool calls
                            yield (
                                swarm.active[thread_id],
                                text,
                                False,
                                {"model_text": True},
                            )

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
                        elif called_tool == "think":  # Call think tool
                            self.console.print(
                                Panel(
                                    escape(tool_calls),
                                    title="💭 Think",
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
                            for t in msg.tool_calls:
                                name = t.get("name")
                                if name and not str(name).startswith("transfer_to_"):
                                    prev = tool_block.get(name, "")
                                    if not prev or prev[0] in "✅❌🔸":
                                        tool_block[name] = (
                                            f"🛠️ {format_called_tool(name)}..."
                                        )
                            fallback = next(
                                (
                                    format_called_tool(t.get("name"))
                                    for t in msg.tool_calls
                                    if t.get("name")
                                    and not str(t.get("name")).startswith(
                                        "transfer_to_"
                                    )
                                ),
                                format_called_tool(called_tool or "tool"),
                            )
                            step = "\n".join(tool_block.values()) or f"🛠️ {fallback}..."
                            extra["tool_block"] = True

                    # Usage
                    if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                        timer = datetime.now(UTC).timestamp() - end_time
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
                                intermediate_step += (
                                    f" {extra.get('tool', '')} {step_timer}"
                                )
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
                    end_date = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
                    last_messages = self.state(swarm, thread_id).values.get(
                        "messages", []
                    )
                    # Guard: state may hold <2 messages on early failure
                    before_last_msg = (
                        last_messages[-2] if len(last_messages) >= 2 else None
                    )
                    if (
                        before_last_msg is not None
                        and before_last_msg.type == "tool"
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
                    if not step or not done:  # Avoid empty reply
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
                if not step or not done:  # Avoid empty reply when retry >= 3
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
                if pending_images:
                    extra["images"] = list(pending_images)
                yield swarm.active[thread_id], step, True, extra


async def run_agent(dev: bool = False, generate_png: bool = False) -> None:
    """Run the agent in CLI mode."""
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
