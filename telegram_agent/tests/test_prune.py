"""Regression check for the TAM-18 memory leak fix (prune + media tokens).

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

    check(token_counter([media_msg]) > 7500, "media payload size not counted")

    msgs = pre_agent_hook(
        {"messages": plain * 5 + [media_msg, HumanMessage("last")]},
        remove_all=True,
        max_tokens=1000,
    )["messages"]
    check(msgs[0].id == REMOVE_ALL_MESSAGES, "remove_all must emit RemoveMessage first")
    check("last" in str(msgs[-1].content), "prune must keep the recent messages")
    check(
        all("AAA" not in str(getattr(m, "content", "")) for m in msgs),
        "huge media survived trim",
    )
    check(token_counter(msgs) <= 1000, "history not bounded to the cap")

    pruned_out = PruneHistory().before_agent({"messages": plain * 5}, None)
    check(pruned_out is not None, "PruneHistory returned no state update")
    pruned = cast("dict[str, Any]", pruned_out)["messages"]
    check(pruned[0].id == REMOVE_ALL_MESSAGES, "PruneHistory must remove_all")

    print("OK: media-aware counting, remove_all prune, bounded cap")


if __name__ == "__main__":
    main()
