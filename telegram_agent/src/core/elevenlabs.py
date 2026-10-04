"""ElevenLabs speech: TTS (``eleven_v4_turbo``) and STT (``scribe_v2``).

One account covers both speech directions, replacing the two unrelated
providers the bot used before: OpenRouter/Grok for text-to-speech and a
multimodal chat model (Gemini) for speech-to-text. Both stay registered as the
fallback, so nothing regresses when ``ELEVENLABS_API_KEY`` is absent or the
account runs out of credits.

The provider names match the keys registered in :mod:`core.llm` -
``elevenlabs-tts`` (capability ``tts``) and ``elevenlabs-stt`` (capability
``stt``) - so ``LLM.pick("tts")``/``LLM.pick("stt")`` select them purely by
their position in ``LLM_ORDER``.

Imports stdlib + ``httpx`` only, and nothing from :mod:`core.llm`, to keep the
dependency one-way.

Reference: https://elevenlabs.io/docs/overview/intro
"""

import re
from collections.abc import Iterator
from datetime import date
from logging import getLogger
from os import getenv
from typing import Any

import httpx

logger = getLogger(__name__)

TTS_PROVIDER = "elevenlabs-tts"
STT_PROVIDER = "elevenlabs-stt"

DEFAULT_TTS_MODEL = "eleven_v4_turbo"
DEFAULT_STT_MODEL = "scribe_v2"
# Documented default, and the best format the free plan allows: mp3 at 192 kbps
# needs Creator and 44.1 kHz PCM/WAV needs Pro.
DEFAULT_TTS_FORMAT = "mp3_44100_128"
# Sarah - young, american, verified for French (fr-FR). Voice Library voices are
# rejected on the free plan ("paid_plan_required"), so the 21 premade voices are
# the whole menu; ELEVENLABS_TTS_VOICE overrides this.
DEFAULT_TTS_VOICE = "EXAVITQu4vr4xnSDxMaL"
# ISO 639-1. Left on by default: every premade voice is an American/English
# recording, and without an explicit language v4 infers the variety from the
# text and lands on the wrong one - French in, Quebec French out.
DEFAULT_TTS_LANGUAGE = "fr"
# Free-plan allowances (https://elevenlabs.io/pricing/api).
DEFAULT_TTS_CHARS = 20_000
DEFAULT_STT_SECONDS = 16_200
# Eleven v4 rejects more than 10 000 characters in one request.
DEFAULT_MAX_CHARS = 9_000
_CONTINUITY_TAIL = 200
_TIMEOUT = 60.0


class ElevenLabsError(RuntimeError):
    """ElevenLabs rejected or failed a request."""


class QuotaExhausted(ElevenLabsError):
    """The account's monthly credits (or plan limits) are spent."""


def _env_str(name: str, default: str) -> str:
    return getenv(name) or default


def _env_num(name: str, default: float) -> float:
    """Read a numeric env var, falling back to `default` on garbage."""
    raw = getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r - using %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    return int(_env_num(name, default))


def _env_flag(name: str) -> bool:
    return (getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _model_id(env: str, default: str) -> str:
    """Read the model from a capability-suffixed env var (``<model>|<caps>``)."""
    return (getenv(env) or "").partition("|")[0] or default


def _base_url() -> str:
    return _env_str("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").rstrip("/")


class _Budget:
    """Monthly usage allowance, reset when the calendar month rolls over.

    A spent free-plan quota answers 402/429 to every further request, so
    counting locally is what stops the bot from paying that latency (and
    logging a failure) on audio it already knows it cannot generate.
    """

    def __init__(self, env: str, default: float, unit: str) -> None:
        self.env = env
        self.default = default
        self.unit = unit
        self.month = ""
        self.used = 0.0

    def limit(self) -> float:
        return _env_num(self.env, self.default)

    def _roll(self) -> None:
        current = date.today().strftime("%Y-%m")
        if current != self.month:
            self.month, self.used = current, 0.0

    def charge(self, amount: float) -> bool:
        """Record `amount` of usage; False once the monthly limit is spent."""
        self._roll()
        limit = self.limit()
        if self.used + amount > limit:
            logger.warning(
                "ElevenLabs %s budget spent (%.0f/%.0f %s this month)",
                self.env,
                self.used,
                limit,
                self.unit,
            )
            return False
        self.used += amount
        return True


_tts_budget = _Budget("ELEVENLABS_TTS_MONTHLY_CHARS", DEFAULT_TTS_CHARS, "characters")
_stt_budget = _Budget(
    "ELEVENLABS_STT_MONTHLY_SECONDS", DEFAULT_STT_SECONDS, "audio seconds"
)


def _reset_budgets() -> None:
    """Forget local usage; the month rollover handles this in production."""
    for budget in (_tts_budget, _stt_budget):
        budget.month, budget.used = "", 0.0


def configured() -> bool:
    """True when an ElevenLabs API key is available."""
    return bool(getenv("ELEVENLABS_API_KEY"))


# v4 has no `instructions` and no `speed`: delivery is steered by bracketed
# audio tags written inline with the text, which `LLM.tts_adapt` already emits.
# It only follows tags that read as voice delivery though, and will happily
# speak an unrecognised bracketed span as prose - so each tag is normalised to a
# documented wording, and anything that does not read as delivery is dropped.
# Documented v4 voice tags, plus the multi-word shapes the docs show
# ([laughs harder], [dry amusement]). Anything outside this set is dropped: a
# heuristic "does it look like words" test would happily keep a markdown link
# label or a bracketed noun and have v4 read it aloud.
_V4_TAGS = frozenset(
    {
        "amused",
        "annoyed",
        "apologetic",
        "casually",
        "confused",
        "confidently",
        "curious",
        "disappointed",
        "dry",
        "excited",
        "frustrated",
        "happily",
        "nervously",
        "playfully",
        "professional",
        "reassuring",
        "sadly",
        "sarcastic",
        "serious",
        "sympathetic",
        "tired",
        "warmly",
        "whispers",
        "whispering",
        "calmly",
        "amusement",
        "chuckles",
        "crying",
        "delighted",
        "exhales",
        "giggles",
        "laughs",
        "laughing",
        "measured",
        "mischievously",
        "sighs",
        "snorts",
        "surprised",
        "thoughtful",
        "wheezing",
    }
)
_V4_INTENSIFIERS = frozenset(
    {"harder", "loudly", "really", "slightly", "very", "softly"}
)
_TAG_SYNONYMS: dict[str, str] = {
    "amused": "playfully",
    "amusingly": "playfully",
    "amusement": "playfully",
    "angrily": "annoyed",
    "annoyance": "annoyed",
    "apologetic": "apologetic",
    "apologetically": "apologetic",
    "astonished": "surprised",
    "chortling": "laughs",
    "chuckling": "laughs",
    "chuckles": "laughs",
    "confusedly": "confused",
    "confidently": "confidently",
    "delighted": "happily",
    "disappointed": "sadly",
    "enthusiastic": "excited",
    "enthusiastically": "excited",
    "exhausted": "tired",
    "formally": "serious",
    "friendly": "warmly",
    "frustratedly": "frustrated",
    "gently": "calmly",
    "giggles": "laughs",
    "gloomily": "sadly",
    "happily": "happily",
    "irritated": "annoyed",
    "joking": "playfully",
    "laughing": "laughs",
    "lightly": "casually",
    "mockingly": "sarcastic",
    "mournfully": "sadly",
    "playful": "playfully",
    "seriously": "serious",
    "sheepishly": "apologetic",
    "shocked": "surprised",
    "smile": "warmly",
    "smiles": "warmly",
    "sniffling": "sadly",
    "softly": "calmly",
    "surprisedly": "surprised",
    "teasing": "playfully",
    "thankfully": "warmly",
    "tiredly": "tired",
    "uneasy": "nervously",
    "warm": "warmly",
    "worriedly": "nervously",
}
_TAG_SPAN = re.compile(r"\[([^\[\]]{1,60})\]")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def canonical_tag(tag: str) -> str | None:
    """Normalise one emotion tag to a documented v4 delivery tag, or None.

    Every word must survive the mapping and land in `_V4_TAGS`, so a partial
    match never passes: `[00:01]` and `[lien]` are dropped, not spoken.
    """
    words = [word for word in re.split(r"[\s_]+", tag.strip().lower()) if word]
    if not words:
        return None
    normalized = " ".join(_TAG_SYNONYMS.get(word, word) for word in words)
    if normalized in _V4_TAGS:
        return normalized
    # "laughs harder" and friends: a documented tag qualified by an intensity
    # word, which qualifies as loudly / really / slightly as much as it does.
    head, _, qualifier = normalized.rpartition(" ")
    if head in _V4_TAGS and qualifier in _V4_INTENSIFIERS:
        return normalized
    return None


def apply_audio_tags(text: str) -> str:
    """Keep recognised emotion tags inline, drop every other bracket span."""
    return re.sub(
        r"[ \t]{2,}",
        " ",
        _TAG_SPAN.sub(
            lambda match: f"[{tag}]" if (tag := canonical_tag(match.group(1))) else " ",
            text,
        ),
    ).strip()


def _pieces(sentence: str, limit: int) -> Iterator[str]:
    """Split one sentence into pieces no longer than `limit`."""
    current = ""
    for word in sentence.split():
        if len(word) > limit:
            if current:
                yield current
                current = ""
            for start in range(0, len(word), limit):
                yield word[start : start + limit]
        elif len(current) + 1 + len(word) > limit:
            yield current
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        yield current


def chunk_text(text: str, limit: int) -> list[str]:
    """Split text into request-sized pieces, preferring sentence boundaries."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buffer = ""
    for sentence in _SENTENCE_END.split(text):
        for piece in _pieces(sentence, limit):
            if buffer and len(buffer) + 1 + len(piece) > limit:
                parts.append(buffer)
                buffer = piece
            elif buffer:
                buffer = f"{buffer} {piece}"
            else:
                buffer = piece
    if buffer:
        parts.append(buffer)
    return parts


async def _post(client: httpx.AsyncClient, path: str, **kwargs: Any) -> httpx.Response:
    """POST with the API key, mapping transport failures to our own errors."""
    response = await client.post(
        f"{_base_url()}{path}",
        headers={"xi-api-key": getenv("ELEVENLABS_API_KEY") or ""},
        **kwargs,
    )
    if response.status_code in (402, 429):
        raise QuotaExhausted(f"ElevenLabs returned {_error_detail(response)}")
    if response.is_error:
        raise ElevenLabsError(f"ElevenLabs returned {_error_detail(response)}")
    return response


def _error_detail(response: httpx.Response) -> str:
    """Human-readable reason for a failed call, free of echoed request content.

    The bare status hides the two failures that actually need naming: a spent
    quota, and a voice the account's plan cannot reach (402 ``paid_plan_required``
    covers both, and the message is the only way to tell them apart).
    """
    try:
        detail = response.json()["detail"]
    except ValueError, KeyError, TypeError:
        return f"HTTP {response.status_code}"
    if isinstance(detail, dict):
        return f"HTTP {response.status_code} {detail.get('code', '')}: {detail.get('message', '')}".rstrip(
            ": "
        )
    return f"HTTP {response.status_code} {detail}"


async def speak(text: str) -> bytes:
    """Synthesise `text` to MP3 audio with Eleven v4 Turbo.

    Text too long for one request is chunked on sentence boundaries and the
    chunks concatenated; each chunk after the first carries the tail of its
    predecessor so prosody survives the join.

    Raises QuotaExhausted when the account or the local budget is spent, and
    ElevenLabsError on any other API failure - the caller decides whether to
    fall back to another provider.
    """
    spoken = apply_audio_tags(text)
    if not spoken:
        raise ElevenLabsError("nothing left to speak after tag filtering")
    parts = chunk_text(spoken, _env_int("ELEVENLABS_TTS_MAX_CHARS", DEFAULT_MAX_CHARS))
    if not _tts_budget.charge(len(spoken)):
        raise QuotaExhausted("local TTS character budget spent")
    voice = _env_str("ELEVENLABS_TTS_VOICE", DEFAULT_TTS_VOICE)
    path = (
        f"/v1/text-to-speech/{voice}"
        f"?output_format={_env_str('ELEVENLABS_TTS_FORMAT', DEFAULT_TTS_FORMAT)}"
    )
    body = {
        "model_id": _model_id("ELEVENLABS_TTS_MODEL", DEFAULT_TTS_MODEL),
        "voice_settings": {
            "stability": _env_num("ELEVENLABS_TTS_STABILITY", 0.5),
            "similarity_boost": _env_num("ELEVENLABS_TTS_SIMILARITY", 0.75),
        },
    }
    # Without this the model infers the language and may pick the wrong
    # regional variety - a French voice reading French with no hint came out
    # with a Quebec accent. ISO 639-1 only: eleven_v4_turbo rejects "fra" and
    # "fr-FR" outright.
    body["language_code"] = _env_str("ELEVENLABS_TTS_LANGUAGE", DEFAULT_TTS_LANGUAGE)
    logger.info("ElevenLabs TTS: %d chars in %d request(s)", len(spoken), len(parts))
    audio = b""
    previous = ""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for part in parts:
            payload = {**body, "text": part}
            if previous:
                payload["previous_text"] = previous
            response = await _post(client, path, json=payload)
            audio += response.content
            previous = part[-_CONTINUITY_TAIL:]
    return audio


async def transcribe(
    audio: bytes, *, mime: str = "audio/ogg", seconds: float | None = None
) -> str:
    """Transcribe `audio` verbatim with Scribe v2.

    Unlike the LLM fallback this needs no prompt, no decoding and no retry loop:
    the endpoint accepts every major container and large uploads, and returns
    the plain transcript. `seconds` only feeds the monthly budget and may be
    omitted when the caller does not know the duration.
    """
    if not audio:
        raise ElevenLabsError("no audio to transcribe")
    form: dict[str, str] = {
        "model_id": _model_id("ELEVENLABS_STT_MODEL", DEFAULT_STT_MODEL)
    }
    # Left to Scribe's own detection, unlike TTS: it reports the language it
    # found, and pinning one here would mistranscribe every other language.
    if language := _env_str("ELEVENLABS_STT_LANGUAGE", ""):
        form["language_code"] = language
    if _env_flag("ELEVENLABS_STT_TAG_EVENTS"):
        form["tag_audio_events"] = "true"
    if seconds and not _stt_budget.charge(seconds):
        raise QuotaExhausted("local STT time budget spent")
    logger.info("ElevenLabs STT: %d bytes of %s", len(audio), mime)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await _post(
            client,
            "/v1/speech-to-text",
            data=form,
            files={"file": ("audio", audio, mime)},
        )
    text = str(response.json().get("text") or "").strip()
    if not text:
        raise ElevenLabsError("ElevenLabs returned an empty transcript")
    return text
