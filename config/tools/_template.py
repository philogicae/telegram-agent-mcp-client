from langchain.tools import tool


@tool
def tool_name(_query: str) -> str:
    """Tool description/prompt."""
    # Implementation here
    return "result"
