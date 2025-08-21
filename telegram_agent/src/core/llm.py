from os import getenv

from dotenv import load_dotenv
from langchain_core.language_models import LanguageModelLike
from langchain_google_genai import ChatGoogleGenerativeAI as ChatGemini
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm() -> LanguageModelLike:
    llm_choice = getenv("LLM_CHOICE")
    llm_model: str = str(getenv("GEMINI_API_MODEL"))

    if llm_choice == "ollama":
        llm_model = str(getenv("OLLAMA_API_MODEL"))
        return ChatOllama(  # Local
            base_url=getenv("OLLAMA_API_BASE"),
            model=llm_model,
            disable_streaming="tool_calling",
            num_gpu=0,  # CPU Only
            num_thread=1,
            temperature=0.5,
            top_p=0.95,
            top_k=20,
            num_ctx=5000,  # 2048-4096-8192
            num_predict=512,  # 512-1024-2048-4096 / -2
        )

    if llm_choice == "openai":
        llm_model = str(getenv("OPENAI_API_MODEL"))
        return ChatOpenAI(
            api_key=getenv("OPENAI_API_KEY"),  # type: ignore
            model=llm_model,
            disable_streaming="tool_calling",
            disabled_params={"parallel_tool_calls": False},
            temperature=0.6 if not llm_model.startswith("gpt-5") else None,
            reasoning_effort="high" if not llm_model.startswith("gpt-5") else None,
            output_version="responses/v1",
        )

    if llm_choice == "gemini-openai":
        return ChatOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=getenv("GEMINI_API_KEY"),  # type: ignore
            model=llm_model,
            disable_streaming="tool_calling",
            disabled_params={"parallel_tool_calls": False},
            temperature=0.6,
            reasoning_effort="low",  # low=1024, medium=8192, high=24576
        )

    return ChatGemini(
        api_key=getenv("GEMINI_API_KEY"),
        model=llm_model,
        disable_streaming="tool_calling",
        temperature=0.6,
        thinking_budget=512,  # -1 for dynamic/unlimited
        transport="rest",  # Avoid retry bug
    )
