"""Regression check for the TAM-18 prune fix and voice-message passthrough.

No pytest in this repo: run with `uv run python -m telegram_agent.tests.test_prune`.
"""

from typing import Any, cast

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from ..src.core.config import PruneHistory
from ..src.core.utils import pre_agent_hook, token_counter


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    media_msg = HumanMessage(
        content=[
            {"type": "text", "text": "img"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64," + "A" * 40000},
            },
        ]
    )
    plain = [HumanMessage("hello"), AIMessage("hi")]

    # Media payload counted once at ~chars/4: ignored would keep the TAM-18
    # leak alive, double counting would evict even short voice turns.
    count = token_counter([media_msg])
    check(count > 7500, "media payload size not counted")
    check(count < 15000, "media payload counted more than once")

    # History prune: huge OLD media evicted, recent text kept, bounded to cap.
    msgs = pre_agent_hook(
        {"messages": plain * 5 + [media_msg, HumanMessage("last")]},
        remove_all=True,
        max_tokens=1000,
    )["messages"]
    check(msgs[0].id == REMOVE_ALL_MESSAGES, "remove_all must emit RemoveMessage first")
    check("last" in str(msgs[-1].content), "prune must keep the recent messages")
    check(
        all("AAA" not in str(getattr(m, "content", "")) for m in msgs),
        "huge old media survived trim",
    )
    check(token_counter(msgs[1:]) <= 1000, "history not bounded to the cap")

    # The incoming oversized voice turn must reach the model INTACT: it is
    # exempt from the cap (only history is pruned), otherwise trim_messages'
    # partial logic strips the audio payload and the model answers to a stub.
    big_voice = HumanMessage(
        content=[
            {"type": "text", "text": "voice"},
            {"type": "audio", "mime_type": "audio/ogg", "base64": "A" * 600000},
        ]
    )
    rescued = pre_agent_hook(
        {"messages": plain * 5 + [big_voice]}, remove_all=True, max_tokens=1000
    )["messages"]
    check(
        rescued[0].id == REMOVE_ALL_MESSAGES, "remove_all must emit RemoveMessage first"
    )
    check(len(rescued) > 2, "current turn must be kept alongside trimmed history")
    check(
        "AAAA" in str(getattr(rescued[-1], "content", "")),
        "incoming voice payload must reach the model intact",
    )
    check(token_counter(rescued[1:-1]) <= 1000, "history must stay bounded to the cap")

    # No history at all: the voice turn alone is still delivered.
    solo = pre_agent_hook({"messages": [big_voice]}, remove_all=True, max_tokens=1000)[
        "messages"
    ]
    check(len(solo) == 2, "current turn must not empty the message list")
    check(
        "AAAA" in str(getattr(solo[-1], "content", "")),
        "solo voice payload must reach the model intact",
    )

    # Non-human current turn (handoff/retry edge): still never empties the list.
    rescued = pre_agent_hook(
        {"messages": [AIMessage("A" * 600000)]}, remove_all=True, max_tokens=1000
    )["messages"]
    check(len(rescued) == 2, "current non-human turn must not empty the message list")

    pruned_out = PruneHistory().before_agent({"messages": plain * 5}, None)
    check(pruned_out is not None, "PruneHistory returned no state update")
    pruned = cast("dict[str, Any]", pruned_out)["messages"]
    check(pruned[0].id == REMOVE_ALL_MESSAGES, "PruneHistory must remove_all")
    check(len(pruned) > 1, "PruneHistory must keep messages after remove_all")

    print("OK: media-aware counting (single count), bounded prune, voice passthrough")


if __name__ == "__main__":
    main()
