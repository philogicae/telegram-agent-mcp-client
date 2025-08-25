from os import getenv
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models import LanguageModelLike
from langchain_google_genai import ChatGoogleGenerativeAI as ChatGemini
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from ..utils import Singleton

load_dotenv()


class LLM(Singleton):
    provider: Any
    llm: dict[str, LanguageModelLike]

    def __init__(self) -> None:
        self.provider = getenv("LLM_CHOICE", "gemini")
        self.llm = {}

    @staticmethod
    def get(provider: str | None = None) -> LanguageModelLike:
        obj = LLM()
        if not obj.llm:
            # Ollama
            base_url_ollama = getenv("OLLAMA_API_BASE")
            model_ollama = getenv("OLLAMA_API_MODEL")
            if base_url_ollama and model_ollama:
                obj.llm["ollama"] = ChatOllama(  # Local
                    base_url=base_url_ollama,
                    model=model_ollama,
                    disable_streaming="tool_calling",
                    num_gpu=0,  # CPU Only
                    num_thread=1,
                    temperature=0.5,
                    top_p=0.95,
                    top_k=20,
                    # num_ctx=5000,  # 2048-4096-8192
                    # num_predict=512,  # 512-1024-2048-4096 / -2
                )

            # OpenAI
            api_key_openai: Any = getenv("OPENAI_API_KEY")
            model_openai = getenv("OPENAI_API_MODEL")
            if api_key_openai and model_openai:
                obj.llm["openai"] = ChatOpenAI(
                    api_key=api_key_openai,
                    model=model_openai,
                    disable_streaming="tool_calling",
                    disabled_params={"parallel_tool_calls": False},
                    temperature=0.6 if not model_openai.startswith("gpt-5") else None,
                    reasoning_effort=(
                        "high" if not model_openai.startswith("gpt-5") else None
                    ),
                    output_version="responses/v1",
                )

            # Google Gemini
            api_key_gemini: Any = getenv("GEMINI_API_KEY")
            model_gemini = getenv("GEMINI_API_MODEL")
            if api_key_gemini and model_gemini:
                obj.llm["gemini-openai"] = ChatOpenAI(
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key=api_key_gemini,
                    model=model_gemini,
                    disable_streaming="tool_calling",
                    disabled_params={"parallel_tool_calls": False},
                    temperature=0.6,
                    reasoning_effort="low",  # low=1024, medium=8192, high=24576
                )
                obj.llm["gemini"] = ChatGemini(
                    api_key=api_key_gemini,
                    model=model_gemini,
                    disable_streaming="tool_calling",
                    temperature=0.6,
                    thinking_budget=512,  # -1 for dynamic/unlimited
                    transport="rest",  # Avoid retry bug
                )

        chosen_provider: str = provider or obj.provider
        llm: LanguageModelLike | None = obj.llm.get(chosen_provider)
        if llm:
            return llm
        raise ValueError(f"LLM {chosen_provider} not found")
