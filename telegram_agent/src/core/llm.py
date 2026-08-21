"""LLM provider configuration and management."""

import re
from logging import getLogger
from os import getenv
from typing import Any

from dotenv import load_dotenv
from langchain.chat_models import BaseChatModel
from langchain.messages import HumanMessage
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
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
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

            model_opencode_alt = getenv("OPENCODE_API_MODEL_ALT")
            if api_key_opencode and model_opencode_alt:
                obj.llm["opencode-alt"] = ChatOpenAI(
                    base_url="https://opencode.ai/zen/go/v1",
                    api_key=api_key_opencode,
                    model=model_opencode_alt,
                    reasoning_effort="low",
                    disable_streaming="tool_calling",
                )

            # Opencode Zen (free models)
            model_opencode_free = getenv("OPENCODE_FREE_API_MODEL")
            if api_key_opencode and model_opencode_free:
                obj.llm["opencode-free"] = ChatOpenAI(
                    base_url="https://opencode.ai/zen/v1",
                    api_key=api_key_opencode,
                    model=model_opencode_free,
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
    async def tts_adapt(text: str) -> str:
        """Adapt a formatted text message into a voice-friendly version.

        Uses the utils LLM to strip markdown, remove code blocks and links,
        and rephrase the content so it sounds natural when spoken aloud.
        Preserves the full message content — only reformats for speech,
        does not summarize. Falls back to the original text if the LLM
        call fails.
        """
        prompt = (
            "You are reading a message aloud to a friend over voice chat. "
            "Convert the following chat message into spoken language that "
            "sounds natural when read aloud — faithful to the original "
            "content, not a summary.\n\n"
            "Rules:\n"
            "- Keep all important information from the original message. "
            "If the message is long, you may lightly condense verbose or "
            "repetitive parts — but never drop key facts, results, names, "
            "dates, or actionable details. The goal is to make it "
            "speakable, not shorter.\n"
            "- Talk like you're reading a message to someone: conversational, "
            "natural, flowing. No bullet points, no lists, no headers.\n"
            "- Strip all markdown (bold, italic, code blocks, links, "
            "headers, tables, list markers).\n"
            "- Replace URLs with a short verbal description (e.g. 'a link "
            "to the docs' instead of the full URL).\n"
            "- Convert emojis into emotion tags like [laughs], [smiles], "
            "[sadly], [excited] — never read emoji names literally.\n"
            "- If the message contains code or technical commands, read "
            "them out naturally (e.g. 'the command pip install' not "
            "'pip space install').\n"
            "- Keep the original language, tone, and intention — if the "
            "message is excited, sarcastic, apologetic, or playful, the "
            "spoken version should feel the same way.\n"
            "- Return ONLY the spoken text, no preamble, no quotes.\n\n"
            "Message:\n"
            f"{text}"
        )
        try:
            llm = LLM.get(LLM_UTILS)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            content = response.content
            if isinstance(content, list):
                content = " ".join(
                    part["text"]
                    for part in content
                    if isinstance(part, dict) and "text" in part
                )
            adapted = content.strip()
            return adapted or text
        except Exception:
            getLogger(__name__).warning("TTS adaptation failed", exc_info=True)
            return text

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
            # Strip emotion tags (e.g. [excited], [smiles]) from the text
            # so the TTS model never reads them aloud. The detected emotions
            # are passed through the instructions parameter instead.
            emotions = re.findall(r"\[([a-zA-Z]+)\]", text)
            clean_text = re.sub(r"\s*\[([a-zA-Z]+)\]\s*", " ", text).strip()
            emotion_hint = ""
            if emotions:
                unique = list(dict.fromkeys(emotions))
                emotion_hint = (
                    f" The speaker is feeling {', '.join(unique)} at various "
                    "points — reflect this in your delivery."
                )
            speed_str = getenv("OPENROUTER_TTS_SPEED", "1.15")
            try:
                openrouter_tts_speed = float(speed_str)
            except ValueError:
                getLogger(__name__).error(
                    "Invalid OPENROUTER_TTS_SPEED=%r — expected a number, "
                    "falling back to 1.15",
                    speed_str,
                )
                openrouter_tts_speed = 1.15
            # OpenAI TTS API requires 0.25 <= speed <= 4.0; clamp out-of-range
            # values instead of failing at call time.
            if not 0.25 <= openrouter_tts_speed <= 4.0:
                getLogger(__name__).warning(
                    "OPENROUTER_TTS_SPEED=%s out of range [0.25, 4.0] — clamping.",
                    openrouter_tts_speed,
                )
                openrouter_tts_speed = max(0.25, min(4.0, openrouter_tts_speed))
            response = await tts.create(
                input=clean_text,
                model=openrouter_tts_model,
                voice=openrouter_tts_voice,
                response_format="mp3",
                speed=openrouter_tts_speed,
                instructions=(
                    "You are a warm, expressive voice assistant. Speak clearly "
                    "and naturally with a friendly, engaging tone. Vary your "
                    "pace — slower for important information, faster for casual "
                    "parts. Always match the emotion of the text: upset, sad, "
                    "excited, amused, etc. Avoid monotone delivery."
                    f"{emotion_hint}"
                ),
            )
            return response.content
        except Exception:
            getLogger(__name__).warning("TTS generation failed", exc_info=True)
        return None
