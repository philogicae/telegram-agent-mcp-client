from langchain.tools import tool


@tool
def think(
    thread_purpose: str,
    thought: str,  #  pylint: disable=unused-argument
    thought_index: int,
    tool_recommendation: str | None = "None",
    left_to_be_done: str | None = "None",  #  pylint: disable=unused-argument
) -> str:
    """Logs a thought step for agentic problem-solving, tracking reasoning, tools, and future plans.
    Start a new thread for each user message.

    # Capabilities
    - Workflow Orchestration: Breaks complex tasks into manageable steps.
    - Iterative Refinement: Self-corrects based on new info or errors.
    - Tool Recommendation: Suggests specific tools for the next action.
    - Forward Planning: Tracks remaining tasks via `left_to_be_done`.

    Args:
        thread_purpose: Short objective/topic for the thread.
        thought: Current reasoning or action description.
        thought_index: Monotonically increasing step number (1, 2, 3...).
        tool_recommendation: Tool to call next, or 'None'.
        left_to_be_done: Remaining steps/sub-goals, or 'None'.
    Returns: Confirmation of log.

    # Example
    1) User: "I keep hearing about central banks, but I don't understand what they are and how they work."
    2) think(
        thread_purpose="Explain Central Banks",
        thought="The user needs a comprehensive explanation of central banks. I need to identify their core definition, key roles (monetary policy, financial stability, currency issuance), and operational mechanisms (interest rates, reserves). I should search for a structured overview to ensure I don't miss major aspects like the Federal Reserve or ECB as examples.",
        thought_index=1,
        tool_recommendation="search_web",
        left_to_be_done="1. Search for 'how central banks work' and key functions. 2. Synthesize findings into a clear explanation. 3. Create a visual graph of the banking system structure if possible. 4. Present final answer."
    )
    3) call search_web(query="how central banks work and their main functions")
    4) think(
        thread_purpose="Explain Central Banks",
        thought="Search results clarify that central banks manage currency stability, control inflation via interest rates, and act as lenders of last resort. I have enough textual information. Now, to make this easier to understand, I should create a graph representing the flow of money and influence between the central bank, commercial banks, and the economy.",
        thought_index=2,
        tool_recommendation="create_graph",
        left_to_be_done="Create a graph showing Central Bank -> Commercial Banks -> Public/Economy relations."
    )
    5) call create_graph(data=...)
    6) Final Response: "Here is an explanation of central banks..." (Task complete, no further think call needed).
    """
    log = f"Thread purpose: {thread_purpose}\nThought {thought_index} logged."
    if tool_recommendation and tool_recommendation.lower() != "none":
        log += f" Recommended tool: {tool_recommendation}."
    return log
