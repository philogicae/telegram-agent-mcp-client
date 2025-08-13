from os import getenv

from dotenv import load_dotenv
from langchain_cerebras import ChatCerebras
from langchain_core.language_models import LanguageModelLike
from langchain_google_genai import ChatGoogleGenerativeAI as ChatGemini
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm() -> LanguageModelLike:
    llm_choice = getenv("LLM_CHOICE")
    if llm_choice == "ollama":
        return ChatOllama(  # Local
            base_url=getenv("OLLAMA_API_BASE"),
            model=getenv("OLLAMA_API_MODEL"),  # type: ignore
            disable_streaming="tool_calling",
            num_gpu=0,  # CPU only
            num_thread=1,
            temperature=0.5,
            top_p=0.95,
            top_k=20,
            num_ctx=8192,  # 2048-4096-8192
            num_predict=512,  # 512-1024-2048-4096 / -2
        )
    if llm_choice == "groq":
        return ChatGroq(
            api_key=getenv("GROQ_API_KEY"),  # type: ignore
            model=getenv("GROQ_API_MODEL"),  # type: ignore
            disable_streaming="tool_calling",
            temperature=0.5,
        )
    if llm_choice == "cerebras":
        return ChatCerebras(
            api_key=getenv("CEREBRAS_API_KEY"),  # type: ignore
            model=getenv("CEREBRAS_API_MODEL"),  # type: ignore
            disable_streaming="tool_calling",
            disabled_params={"parallel_tool_calls": False},
            temperature=0.5,
        )
    if llm_choice == "gemini":
        return ChatGemini(
            api_key=getenv("GEMINI_API_KEY"),
            model=getenv("GEMINI_API_MODEL"),
            disable_streaming="tool_calling",
            temperature=0.5,
            thinking_budget=1024,  # -1 for dynamic/unlimited
            # include_thoughts=True,
        )

    model = getenv("OPENAI_API_MODEL")
    return ChatOpenAI(
        api_key=getenv("OPENAI_API_KEY"),  # type: ignore
        model=model,  # type: ignore
        disable_streaming="tool_calling",
        disabled_params={"parallel_tool_calls": False},
        temperature=0.5 if not str(model).startswith("gpt-5") else None,
        reasoning_effort="high" if not str(model).startswith("gpt-5") else None,
        output_version="responses/v1",
    )
