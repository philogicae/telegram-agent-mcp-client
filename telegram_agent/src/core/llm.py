"""LLM provider configuration and management."""

from logging import getLogger
from os import getenv
from typing import Any

from dotenv import load_dotenv
from langchain.chat_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    HarmBlockThreshold,
    HarmCategory,
)
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from ..utils import Singleton

load_dotenv()

LLM_CHOICE = getenv("LLM_CHOICE", "opencode")
LLM_UTILS = getenv("LLM_UTILS") or LLM_CHOICE
SUPPORT_STRUCTURED_OUTPUT = {
    "ollama",
    "gemini",
    "gemini-small",
    "fireworks",
}


class LLM(Singleton):
    """Singleton for managing LLM providers."""

    provider: Any
    llm: dict[str, BaseChatModel]
    extra: dict[str, Any]

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.provider = LLM_CHOICE
        self.llm = {}
        self.extra = {}

    @staticmethod
    def get(provider: str | None = None) -> BaseChatModel:
        """Get the LLM for the specified provider."""
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

            # Google Gemini
            api_key_gemini: Any = getenv("GEMINI_API_KEY")
            model_gemini = getenv("GEMINI_API_MODEL")
            model_gemini_small = getenv("GEMINI_API_MODEL_SMALL")
            if api_key_gemini and model_gemini:
                common: dict[str, Any] = {
                    "disable_streaming": "tool_calling",
                    "safety_settings": {
                        cat: HarmBlockThreshold.OFF
                        for i, cat in enumerate(HarmCategory)
                        if 0 < i < 5
                    },
                }
                specifics: dict[str, Any] = (
                    {
                        "temperature": 0.7,
                        "thinking_budget": 512,
                    }
                    if "3" not in model_gemini
                    else {"temperature": 1, "thinking_level": "low"}
                )
                obj.llm["gemini"] = ChatGoogleGenerativeAI(
                    api_key=api_key_gemini,
                    model=model_gemini,
                    **common,
                    **specifics,
                )
                obj.llm["gemini-small"] = ChatGoogleGenerativeAI(
                    api_key=api_key_gemini,
                    model=model_gemini_small,
                    **common,
                    **specifics,
                )

            # Fire Pass
            api_key_fireworks: Any = getenv("FIREWORKS_API_KEY")
            model_fireworks = getenv("FIREWORKS_API_MODEL")
            if api_key_fireworks and model_fireworks:
                obj.llm["fireworks"] = ChatAnthropic(
                    base_url="https://api.fireworks.ai/inference",
                    api_key=api_key_fireworks,
                    model_name=model_fireworks,
                    thinking={"type": "enabled", "budget_tokens": 1024},
                    disable_streaming="tool_calling",
                )

            # Opencode
            api_key_opencode: Any = getenv("OPENCODE_API_KEY")
            model_opencode = getenv("OPENCODE_API_MODEL")
            if api_key_opencode and model_opencode:
                obj.llm["opencode"] = ChatOpenAI(
                    base_url="https://opencode.ai/zen/go/v1",
                    api_key=api_key_opencode,
                    model=model_opencode,
                    reasoning_effort="low",
                    disable_streaming="tool_calling",
                )

        if not obj.extra:
            # TTS (Text-to-Speech via OpenRouter, OpenAI-compatible audio modality)
            openrouter_api_key: Any = getenv("OPENROUTER_API_KEY")
            if openrouter_api_key:
                obj.extra["tts"] = AsyncOpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_api_key,
                ).audio.speech

        chosen_provider: str = provider or obj.provider
        llm: BaseChatModel | None = obj.llm.get(chosen_provider)
        if llm:
            return llm
        raise ValueError(f"LLM {chosen_provider} not found")

    @staticmethod
    async def tts(text: str) -> bytes | None:
        """Generate speech audio bytes from text using the TTS LLM."""
        try:
            openrouter_tts_model = getenv(
                "OPENROUTER_TTS_MODEL", "x-ai/grok-voice-tts-1.0"
            )
            openrouter_tts_voice = getenv("OPENROUTER_TTS_VOICE", "eve")
            tts = LLM().extra.get("tts")
            if not tts:
                return None
            response = await tts.create(
                input=text,
                model=openrouter_tts_model,
                voice=openrouter_tts_voice,
                response_format="mp3",
            )
            return response.content
        except Exception:
            getLogger(__name__).warning("TTS generation failed", exc_info=True)
        return None
