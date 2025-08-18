from os import getenv

from dotenv import load_dotenv
from langchain_core.language_models import LanguageModelLike
from langchain_google_genai import ChatGoogleGenerativeAI as ChatGemini
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm() -> LanguageModelLike:
    llm_choice = getenv("LLM_CHOICE")
    if llm_choice == "openai":
        model = str(getenv("OPENAI_API_MODEL"))
        return ChatOpenAI(
            api_key=getenv("OPENAI_API_KEY"),  # type: ignore
            model=model,
            disable_streaming="tool_calling",
            disabled_params={"parallel_tool_calls": False},
            temperature=0.6 if not model.startswith("gpt-5") else None,
            reasoning_effort="high" if not model.startswith("gpt-5") else None,
            output_version="responses/v1",
        )
    if llm_choice == "gemini-openai":
        return ChatOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=getenv("GEMINI_API_KEY"),  # type: ignore
            model=getenv("GEMINI_API_MODEL"),  # type: ignore
            disable_streaming="tool_calling",
            disabled_params={"parallel_tool_calls": False},
            temperature=0.6,
            reasoning_effort="low",  # low=1024, medium=8192, high=24576
        )
    return ChatGemini(
        api_key=getenv("GEMINI_API_KEY"),
        model=getenv("GEMINI_API_MODEL"),
        disable_streaming="tool_calling",
        temperature=0.6,
        thinking_budget=512,  # -1 for dynamic/unlimited
        transport="rest",  # Avoid retry bug
    )
