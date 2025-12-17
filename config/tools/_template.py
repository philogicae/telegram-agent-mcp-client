from langchain.tools import tool


@tool
def tool_name(query: str) -> str:
    """Tool description/prompt"""
    # Implementation here
    return "result"
