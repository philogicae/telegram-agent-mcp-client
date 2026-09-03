"""LLM provider configuration and management."""

import contextvars
import re
from logging import getLogger
from os import getenv
from time import monotonic
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain.chat_models import BaseChatModel
from langchain.messages import HumanMessage
from langchain_anthropic import ChatAnthropic
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    HarmBlockThreshold,
    HarmCategory,
)
from langchain_ollama import ChatOllama
from openai import AsyncOpenAI

from ..utils import Singleton, extract_response

load_dotenv()

# OpenCode wants a stable session id per conversation in the x-opencode-session
# header. We inject it dynamically via an httpx client hook so the same cached
# model instance can be reused across chats.
_OPENCODE_SESSION: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "opencode_session", default=None
)


def _set_opencode_session_header(request: httpx.Request) -> None:
    session_id = _OPENCODE_SESSION.get()
    if session_id:
        request.headers["x-opencode-session"] = session_id


async def _aset_opencode_session_header(request: httpx.Request) -> None:
    _set_opencode_session_header(request)


_OPENCODE_HTTP_CLIENT = httpx.Client(
    event_hooks={"request": [_set_opencode_session_header]}
)
_OPENCODE_HTTP_ASYNC_CLIENT = httpx.AsyncClient(
    event_hooks={"request": [_aset_opencode_session_header]}
)


def _order(key: str, default: str) -> list[str]:
    """Parse a comma-separated provider run order from env."""
    return [p.strip() for p in getenv(key, default).split(",") if p.strip()]


LLM_ORDER = _order("LLM_ORDER", "opencode-alt,opencode,gemini,gemini-small")
LLM_ORDER_FAST = _order("LLM_ORDER_FAST", "opencode-alt,opencode,gemini-small")


# ponytail: static capability table parsed from env at import; no runtime probing
def _split(spec: str | None) -> tuple[str, frozenset[str]]:
    """Split '<model>|<cap1>+<cap2>' into model name and capability set."""
    if not spec:
        return "", frozenset()
    model, _, caps = spec.partition("|")
    return model, frozenset(caps.split("+")) - {""}


_MODEL_ENVS: dict[str, str] = {
    "OLLAMA_API_MODEL": "ollama",
    "GEMINI_API_MODEL": "gemini",
    "GEMINI_API_MODEL_SMALL": "gemini-small",
    "FIREWORKS_API_MODEL": "fireworks",
    "OPENCODE_API_MODEL": "opencode",
    "OPENCODE_API_MODEL_ALT": "opencode-alt",
    "OPENROUTER_TTS_MODEL": "openrouter-tts",
}
SPECS: dict[str, tuple[str, frozenset[str]]] = {
    provider: _split(getenv(key)) for key, provider in _MODEL_ENVS.items()
}
CAPABILITIES: dict[str, frozenset[str]] = {
    provider: caps for provider, (_, caps) in SPECS.items()
}


def supports(provider: str | None, *caps: str) -> bool:
    """Check whether a provider declares all the given capabilities."""
    return set(caps) <= CAPABILITIES.get(
        provider or (LLM_ORDER[0] if LLM_ORDER else ""), frozenset()
    )


_jail: dict[str, dict[str, float]] = {}


def _env_num(name: str, default: float) -> float:
    """Read a numeric env var, falling back to `default` on garbage."""
    raw = getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        getLogger(__name__).warning("Invalid %s=%r — using %s", name, raw, default)
        return default


def mark_alive(provider: str) -> None:
    """Clear failure history after a successful call."""
    _jail.pop(provider, None)


def mark_dead(provider: str, cooldown: float | None = None) -> None:
    """Count a failed call against `provider`; jail it after enough strikes.

    Each strike parks the provider out of selection for LLM_DEAD_COOLDOWN
    seconds (default 300). After LLM_JAIL_STRIKES consecutive strikes
    (default 3) it is jailed for LLM_JAIL_HOURS hours (default 24) until
    release. mark_alive() clears the count on any successful call.
    """
    rec = _jail.setdefault(provider, {"fails": 0.0, "until": 0.0})
    rec["fails"] += 1
    if rec["fails"] >= _env_num("LLM_JAIL_STRIKES", 3):
        hours = _env_num("LLM_JAIL_HOURS", 24)
        rec["until"], rec["fails"] = monotonic() + hours * 3600, 0.0
        getLogger(__name__).warning("LLM %s jailed for %.1fh", provider, hours)
        return
    rec["until"] = monotonic() + (
        cooldown if cooldown is not None else _env_num("LLM_DEAD_COOLDOWN", 300)
    )


def _alive(provider: str) -> bool:
    return _jail.get(provider, {}).get("until", 0.0) <= monotonic()


def can_read(provider: str | None = None) -> bool:
    """Provider accepts text input/output."""
    return supports(provider, "text")


def can_docs(provider: str | None = None) -> bool:
    """Provider accepts documents (PDF and similar) as input."""
    return supports(provider, "pdf")


def can_struct(provider: str | None = None) -> bool:
    """Provider natively outputs structured JSON."""
    return supports(provider, "structured")


def can_see(provider: str | None = None) -> bool:
    """Provider accepts image input."""
    return supports(provider, "vision")


def can_listen(provider: str | None = None) -> bool:
    """Provider accepts audio input (speech-to-text)."""
    return supports(provider, "stt")


def can_speak(provider: str | None = None) -> bool:
    """Provider outputs speech (text-to-speech)."""
    return supports(provider, "tts")


def can_watch(provider: str | None = None) -> bool:
    """Provider accepts video input."""
    return supports(provider, "video")


def can_draw(provider: str | None = None) -> bool:
    """Provider generates images."""
    return supports(provider, "image")


class LLM(Singleton):
    """Singleton for managing LLM providers."""

    llm: dict[str, BaseChatModel]
    extra: dict[str, Any]

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.llm = {}
        self.extra = {}

    @staticmethod
    def pick(*caps: str, fast: bool = False) -> str | None:
        """Resolve the run order to a provider name, else None.

        First configured provider wins; with caps, first configured provider
        declaring them all (fast list falls back to main list, then to any
        aux endpoint). Providers parked by mark_dead() sort last, so a dead
        key/model fails over to the next candidate instead of breaking calls.
        """
        obj = LLM()
        if not obj.llm:
            LLM.get()
        seen: list[str] = []
        for order in [LLM_ORDER_FAST, LLM_ORDER] if fast else [LLM_ORDER]:
            seen += [p for p in order if p in obj.llm and p not in seen]
        capable = [p for p in seen if not caps or supports(p, *caps)]
        if caps:
            configured = obj.llm.keys() | obj.extra.keys()
            capable += [
                p
                for p in CAPABILITIES
                if p not in capable and p in configured and supports(p, *caps)
            ]
        if not capable:
            return None
        # Alive providers first; jailed/cooled-down ones only tried if alone.
        return min(capable, key=lambda p: not _alive(p))

    @staticmethod
    def get(provider: str | None = None) -> BaseChatModel:
        """Get the LLM for the specified provider (default: head of LLM_ORDER)."""
        obj = LLM()
        if not obj.llm:
            # Ollama
            base_url_ollama = getenv("OLLAMA_API_BASE")
            model_ollama = SPECS["ollama"][0]
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
            model_gemini = SPECS["gemini"][0]
            model_gemini_small = SPECS["gemini-small"][0]
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
            model_fireworks = SPECS["fireworks"][0]
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
            model_opencode = SPECS["opencode"][0]
            if api_key_opencode and model_opencode:
                obj.llm["opencode"] = ChatDeepSeek(
                    base_url="https://opencode.ai/zen/go/v1",
                    api_key=api_key_opencode,
                    model=model_opencode,
                    reasoning_effort="low",
                    disable_streaming="tool_calling",
                    http_client=_OPENCODE_HTTP_CLIENT,
                    http_async_client=_OPENCODE_HTTP_ASYNC_CLIENT,
                )

            model_opencode_alt = SPECS["opencode-alt"][0]
            if api_key_opencode and model_opencode_alt:
                obj.llm["opencode-alt"] = ChatDeepSeek(
                    base_url="https://opencode.ai/zen/go/v1",
                    api_key=api_key_opencode,
                    model=model_opencode_alt,
                    reasoning_effort="low",
                    disable_streaming="tool_calling",
                    http_client=_OPENCODE_HTTP_CLIENT,
                    http_async_client=_OPENCODE_HTTP_ASYNC_CLIENT,
                )

        if not obj.extra:
            # TTS (Text-to-Speech via OpenRouter, OpenAI-compatible audio modality)
            openrouter_api_key: Any = getenv("OPENROUTER_API_KEY")
            if openrouter_api_key:
                obj.extra["openrouter-tts"] = AsyncOpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_api_key,
                ).audio.speech

        chosen_provider: str | None = provider or LLM.pick()
        llm: BaseChatModel | None = obj.llm.get(chosen_provider or "")
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
            llm = LLM.get(LLM.pick(fast=True))
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            adapted, _ = extract_response(response)
            return adapted.strip() or text
        except Exception:
            getLogger(__name__).warning("TTS adaptation failed", exc_info=True)
            return text

    @staticmethod
    async def tts(text: str) -> bytes | None:
        """Generate speech audio bytes from text using the TTS endpoint."""
        try:
            tts_client = LLM().extra.get("openrouter-tts")
            if not tts_client:
                return None
            openrouter_tts_model = (
                SPECS["openrouter-tts"][0] or "x-ai/grok-voice-tts-1.0"
            )
            openrouter_tts_voice = getenv("OPENROUTER_TTS_VOICE", "eve")
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
            response = await tts_client.create(
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
