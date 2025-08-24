from os import getenv
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models import LanguageModelLike
from langchain_google_genai import ChatGoogleGenerativeAI as ChatGemini
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from .utils import Singleton

load_dotenv()


class LLM(Singleton):
    provider: Any
    model: Any
    llm: LanguageModelLike

    @staticmethod
    def get() -> LanguageModelLike:
        obj = LLM()
        if not hasattr(obj, "llm"):
            obj.provider = getenv("LLM_CHOICE")
            obj.model = str(getenv("GEMINI_API_MODEL"))
            if obj.provider == "ollama":
                obj.model = str(getenv("OLLAMA_API_MODEL"))
                obj.llm = ChatOllama(  # Local
                    base_url=getenv("OLLAMA_API_BASE"),
                    model=obj.model,
                    disable_streaming="tool_calling",
                    num_gpu=0,  # CPU Only
                    num_thread=1,
                    temperature=0.5,
                    top_p=0.95,
                    top_k=20,
                    num_ctx=5000,  # 2048-4096-8192
                    num_predict=512,  # 512-1024-2048-4096 / -2
                )
            if obj.provider == "openai":
                obj.model = str(getenv("OPENAI_API_MODEL"))
                obj.llm = ChatOpenAI(
                    api_key=getenv("OPENAI_API_KEY"),  # type: ignore
                    model=obj.model,
                    disable_streaming="tool_calling",
                    disabled_params={"parallel_tool_calls": False},
                    temperature=0.6 if not obj.model.startswith("gpt-5") else None,
                    reasoning_effort=(
                        "high" if not obj.model.startswith("gpt-5") else None
                    ),
                    output_version="responses/v1",
                )
            if obj.provider == "gemini-openai":
                obj.llm = ChatOpenAI(
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key=getenv("GEMINI_API_KEY"),  # type: ignore
                    model=obj.model,
                    disable_streaming="tool_calling",
                    disabled_params={"parallel_tool_calls": False},
                    temperature=0.6,
                    reasoning_effort="low",  # low=1024, medium=8192, high=24576
                )
            obj.llm = ChatGemini(
                api_key=getenv("GEMINI_API_KEY"),
                model=obj.model,
                disable_streaming="tool_calling",
                temperature=0.6,
                thinking_budget=512,  # -1 for dynamic/unlimited
                transport="rest",  # Avoid retry bug
            )
        return obj.llm
