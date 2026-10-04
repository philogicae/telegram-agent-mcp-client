"""Tests for ``telegram_agent/src/core/elevenlabs.py``."""

from typing import Any

import httpx
import pytest

from telegram_agent.src.core import elevenlabs as el


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self._payload = payload
        self.is_error = status_code >= 400

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            raise ValueError("no JSON body")
        return self._payload


class FakeClient:
    """Stands in for ``httpx.AsyncClient``, recording the requests it saw."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def install(monkeypatch: pytest.MonkeyPatch, client: FakeClient) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(el, "_reset_budgets", el._reset_budgets)
    monkeypatch.setattr(
        el.httpx, "AsyncClient", lambda **_kwargs: client, raising=False
    )


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch):
    """No real key, no real quota, no real network."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    for var in (
        "ELEVENLABS_BASE_URL",
        "ELEVENLABS_TTS_MODEL",
        "ELEVENLABS_STT_MODEL",
        "ELEVENLABS_TTS_VOICE",
        "ELEVENLABS_TTS_FORMAT",
        "ELEVENLABS_TTS_LANGUAGE",
        "ELEVENLABS_TTS_STABILITY",
        "ELEVENLABS_TTS_SIMILARITY",
        "ELEVENLABS_TTS_MAX_CHARS",
        "ELEVENLABS_STT_LANGUAGE",
        "ELEVENLABS_STT_TAG_EVENTS",
        "ELEVENLABS_TTS_MONTHLY_CHARS",
        "ELEVENLABS_STT_MONTHLY_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    el._reset_budgets()
    yield
    el._reset_budgets()


class TestConfiguration:
    def test_configured_tracks_the_key(self, monkeypatch):
        assert not el.configured()
        monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
        assert el.configured()

    def test_model_id_strips_the_capability_suffix(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_TTS_MODEL", "eleven_v4|extra|tts")
        assert el._model_id("ELEVENLABS_TTS_MODEL", "fallback") == "eleven_v4"

    def test_model_id_falls_back_when_unset(self):
        assert el._model_id("ELEVENLABS_TTS_MODEL", "fallback") == "fallback"

    def test_provider_names_match_the_llm_registry(self):
        assert el.TTS_PROVIDER == "elevenlabs-tts"
        assert el.STT_PROVIDER == "elevenlabs-stt"

    def test_env_flag_accepts_common_spellings(self, monkeypatch):
        for raw, expected in (("1", True), ("true", True), ("YES", True), ("0", False)):
            monkeypatch.setenv("ELEVENLABS_STT_TAG_EVENTS", raw)
            assert el._env_flag("ELEVENLABS_STT_TAG_EVENTS") is expected


class TestBudget:
    def test_charges_until_the_limit(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_TTS_MONTHLY_CHARS", "10")
        budget = el._Budget("ELEVENLABS_TTS_MONTHLY_CHARS", 10, "chars")
        assert budget.charge(6) is True
        assert budget.charge(4) is True
        assert budget.charge(1) is False

    def test_resets_when_the_month_rolls(self):
        budget = el._Budget("ELEVENLABS_TTS_MONTHLY_CHARS", 1, "chars")
        budget.charge(1)
        budget.month = "1999-01"
        assert budget.charge(1) is True
        assert budget.used == 1

    def test_invalid_env_limit_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("ELEVENLABS_TTS_MONTHLY_CHARS", "not-a-number")
        budget = el._Budget("ELEVENLABS_TTS_MONTHLY_CHARS", 7, "chars")
        assert budget.limit() == 7
        assert "not-a-number" in caplog.text

    async def test_speak_refuses_once_the_local_budget_is_spent(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_TTS_MONTHLY_CHARS", "5")
        client = FakeClient([])
        install(monkeypatch, client)
        with pytest.raises(el.QuotaExhausted):
            await el.speak("a much longer line than five characters")
        assert client.calls == []  # never spent an API call

    async def test_transcribe_refuses_once_the_local_budget_is_spent(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_STT_MONTHLY_SECONDS", "10")
        client = FakeClient([])
        install(monkeypatch, client)
        with pytest.raises(el.QuotaExhausted):
            await el.transcribe(b"OGG", seconds=30)
        assert client.calls == []

    async def test_transcribe_skips_charging_an_unknown_duration(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_STT_MONTHLY_SECONDS", "1")
        install(monkeypatch, FakeClient([FakeResponse(payload={"text": "salut"})]))
        assert await el.transcribe(b"OGG") == "salut"


class TestCanonicalTag:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("[excited]", "excited"),
            ("[laughs]", "laughs"),
            ("[Smiles]", "warmly"),
            ("[laughing]", "laughs"),
            ("[sadly]", "sadly"),
            ("[whispers]", "whispers"),
            ("[quietly curious]", None),  # "quietly" is not a documented tag
        ],
    )
    def test_recognised_tags_are_normalised(self, raw, expected):
        assert el.canonical_tag(raw[1:-1]) == expected

    @pytest.mark.parametrize(
        "raw", ["", "   ", "00:01", "2024", "lien", "bruit", "a" * 40, "[nested]"]
    )
    def test_non_delivery_tags_are_rejected(self, raw):
        assert el.canonical_tag(raw) is None

    def test_multi_word_tag_needs_every_word_recognised(self):
        assert el.canonical_tag("laughs harder") == "laughs harder"
        assert el.canonical_tag("laughs intrus") is None


class TestApplyAudioTags:
    def test_keeps_delivery_tags_inline(self):
        assert el.apply_audio_tags("[excited] bonjour") == "[excited] bonjour"

    def test_maps_synonyms(self):
        assert el.apply_audio_tags("[smiles] salut") == "[warmly] salut"

    def test_drops_timestamps_and_links(self):
        # v4 speaks an unrecognised bracketed span as prose, so they must go.
        # The link's URL part survives as prose; tts_adapt is what removes it,
        # so the check here is only that neither part is left bracketed.
        assert el.apply_audio_tags("[00:01] bonjour [lien](http://x)") == (
            "bonjour (http://x)"
        )

    def test_collapses_whitespace_left_behind(self):
        assert el.apply_audio_tags("a  [bruit]  b") == "a b"

    def test_plain_text_untouched(self):
        assert el.apply_audio_tags("bonjour") == "bonjour"


class TestChunkText:
    def test_short_text_is_one_piece(self):
        assert el.chunk_text("bonjour", 100) == ["bonjour"]

    def test_splits_on_sentence_boundaries(self):
        parts = el.chunk_text("un. deux. trois.", 9)
        assert parts == ["un. deux.", "trois."]

    def test_every_piece_fits_the_limit(self):
        text = "phrase " * 100
        parts = el.chunk_text(text, 50)
        assert all(len(part) <= 50 for part in parts)
        assert " ".join(parts) == text.strip()

    def test_long_unbreakable_token_is_hard_split(self):
        parts = el.chunk_text("x" * 25, 10)
        assert [len(part) for part in parts] == [10, 10, 5]

    def test_long_token_flushes_the_pending_words_first(self):
        parts = el.chunk_text("court mot " + "y" * 25, 10)
        assert parts[0] == "court mot"
        assert all(len(part) <= 10 for part in parts)

    def test_nothing_is_lost(self):
        text = "a bb ccc dddd. e fff gggg hhhhh."
        assert " ".join(el.chunk_text(text, 12)) == text


class TestSpeak:
    async def test_posts_v4_turbo_and_returns_audio(self, monkeypatch):
        client = FakeClient([FakeResponse(content=b"ID3")])
        install(monkeypatch, client)
        assert await el.speak("bonjour") == b"ID3"
        call = client.calls[0]
        assert call["url"].startswith("https://api.elevenlabs.io/v1/text-to-speech/")
        assert "output_format=mp3_44100_128" in call["url"]
        assert call["headers"]["xi-api-key"] == "test-key"
        assert call["json"]["model_id"] == "eleven_v4_turbo"
        assert call["json"]["text"] == "bonjour"

    async def test_language_is_pinned_by_default(self, monkeypatch):
        # Every premade voice is an English recording: left to inference, v4
        # picks the regional variety from the text and gets French wrong.
        client = FakeClient([FakeResponse(content=b"ID3")])
        install(monkeypatch, client)
        await el.speak("bonjour")
        assert client.calls[0]["json"]["language_code"] == "fr"

    async def test_language_is_overridable(self, monkeypatch):
        client = FakeClient([FakeResponse(content=b"ID3")])
        install(monkeypatch, client)
        monkeypatch.setenv("ELEVENLABS_TTS_LANGUAGE", "es")
        await el.speak("hola")
        assert client.calls[0]["json"]["language_code"] == "es"

    async def test_voice_and_voice_settings_are_configurable(self, monkeypatch):
        client = FakeClient([FakeResponse(content=b"ID3")])
        install(monkeypatch, client)
        monkeypatch.setenv("ELEVENLABS_TTS_VOICE", "VOICE_ID")
        monkeypatch.setenv("ELEVENLABS_TTS_FORMAT", "mp3_44100_32")
        monkeypatch.setenv("ELEVENLABS_TTS_STABILITY", "0.25")
        monkeypatch.setenv("ELEVENLABS_TTS_SIMILARITY", "0.9")
        await el.speak("bonjour")
        call = client.calls[0]
        assert "/v1/text-to-speech/VOICE_ID?" in call["url"]
        assert "output_format=mp3_44100_32" in call["url"]
        settings = call["json"]["voice_settings"]
        assert settings == {"stability": 0.25, "similarity_boost": 0.9}
        # v4 has no style or speed slider.
        assert "style" not in settings
        assert "speed" not in settings

    async def test_long_text_is_chunked_with_continuity(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_TTS_MAX_CHARS", "20")
        client = FakeClient([FakeResponse(content=b"A"), FakeResponse(content=b"B")])
        install(monkeypatch, client)
        assert await el.speak("un. deux. trois. quatre.") == b"AB"
        assert len(client.calls) == 2
        assert client.calls[0]["json"]["text"] == "un. deux. trois."
        # The second chunk carries the first one's tail so prosody continues.
        assert "previous_text" not in client.calls[0]["json"]
        assert client.calls[1]["json"]["previous_text"] == "un. deux. trois."

    async def test_emotion_tags_reach_the_model_inline(self, monkeypatch):
        client = FakeClient([FakeResponse(content=b"ID3")])
        install(monkeypatch, client)
        await el.speak("[smiles] salut")
        assert client.calls[0]["json"]["text"] == "[warmly] salut"

    async def test_empty_after_tag_filtering(self, monkeypatch):
        install(monkeypatch, FakeClient([]))
        with pytest.raises(el.ElevenLabsError):
            await el.speak("[00:01]")

    @pytest.mark.parametrize("status", [401, 403, 422, 500])
    async def test_http_errors_raise_without_leaking_the_key(
        self, monkeypatch, status, caplog
    ):
        install(monkeypatch, FakeClient([FakeResponse(status_code=status)]))
        with pytest.raises(el.ElevenLabsError) as err:
            await el.speak("bonjour")
        assert str(status) in str(err.value)
        assert "test-key" not in caplog.text
        assert "test-key" not in str(err.value)

    @pytest.mark.parametrize("status", [402, 429])
    async def test_quota_status_raises_quota_exhausted(self, monkeypatch, status):
        install(monkeypatch, FakeClient([FakeResponse(status_code=status)]))
        with pytest.raises(el.QuotaExhausted):
            await el.speak("bonjour")

    async def test_paid_plan_error_is_named(self, monkeypatch):
        # A Voice Library voice answers 402 on the free plan; the status alone
        # is indistinguishable from a spent quota, the message is not.
        payload = {
            "detail": {
                "type": "payment_required",
                "code": "paid_plan_required",
                "message": "Free users cannot use library voices via the API.",
            }
        }
        install(monkeypatch, FakeClient([FakeResponse(402, payload=payload)]))
        with pytest.raises(el.QuotaExhausted) as err:
            await el.speak("bonjour")
        assert "paid_plan_required" in str(err.value)
        assert "library voices" in str(err.value)

    async def test_non_json_error_body_falls_back_to_status(self, monkeypatch):
        client = FakeClient([FakeResponse(500)])
        install(monkeypatch, client)
        with pytest.raises(el.ElevenLabsError, match="HTTP 500"):
            await el.speak("bonjour")

    async def test_non_dict_detail_is_still_reported(self, monkeypatch):
        client = FakeClient([FakeResponse(422, payload={"detail": ["bad field"]})])
        install(monkeypatch, client)
        with pytest.raises(el.ElevenLabsError, match="bad field"):
            await el.speak("bonjour")

    async def test_transport_error_propagates(self, monkeypatch):
        class Boom(FakeClient):
            async def post(self, url: str, **kwargs: Any) -> FakeResponse:
                raise httpx.ConnectError("no route", request=None)

        install(monkeypatch, Boom([]))
        with pytest.raises(httpx.ConnectError):
            await el.speak("bonjour")


class TestTranscribe:
    async def test_posts_multipart_and_returns_text(self, monkeypatch):
        client = FakeClient([FakeResponse(payload={"text": "  bonjour  "})])
        install(monkeypatch, client)
        assert await el.transcribe(b"OGG", mime="audio/ogg") == "bonjour"
        call = client.calls[0]
        assert call["url"].endswith("/v1/speech-to-text")
        assert call["data"]["model_id"] == "scribe_v2"
        assert call["files"]["file"] == ("audio", b"OGG", "audio/ogg")
        assert "language_code" not in call["data"]
        assert "tag_audio_events" not in call["data"]

    async def test_language_and_event_tagging_are_optional(self, monkeypatch):
        client = FakeClient([FakeResponse(payload={"text": "salut"})])
        install(monkeypatch, client)
        monkeypatch.setenv("ELEVENLABS_STT_LANGUAGE", "fra")
        monkeypatch.setenv("ELEVENLABS_STT_TAG_EVENTS", "1")
        await el.transcribe(b"OGG")
        assert client.calls[0]["data"]["language_code"] == "fra"
        assert client.calls[0]["data"]["tag_audio_events"] == "true"

    async def test_stt_model_from_env(self, monkeypatch):
        client = FakeClient([FakeResponse(payload={"text": "salut"})])
        install(monkeypatch, client)
        monkeypatch.setenv("ELEVENLABS_STT_MODEL", "scribe_v1|stt")
        await el.transcribe(b"OGG")
        assert client.calls[0]["data"]["model_id"] == "scribe_v1"

    async def test_empty_audio_rejected_before_the_call(self, monkeypatch):
        client = FakeClient([])
        install(monkeypatch, client)
        with pytest.raises(el.ElevenLabsError):
            await el.transcribe(b"")
        assert client.calls == []

    async def test_empty_transcript_raises(self, monkeypatch):
        install(monkeypatch, FakeClient([FakeResponse(payload={"text": "  "})]))
        with pytest.raises(el.ElevenLabsError):
            await el.transcribe(b"OGG")

    async def test_quota_status_raises_quota_exhausted(self, monkeypatch):
        install(monkeypatch, FakeClient([FakeResponse(status_code=429)]))
        with pytest.raises(el.QuotaExhausted):
            await el.transcribe(b"OGG")

    async def test_base_url_is_configurable(self, monkeypatch):
        client = FakeClient([FakeResponse(payload={"text": "salut"})])
        install(monkeypatch, client)
        monkeypatch.setenv(
            "ELEVENLABS_BASE_URL", "https://api.eu.residency.elevenlabs.io"
        )
        await el.transcribe(b"OGG")
        assert client.calls[0]["url"] == (
            "https://api.eu.residency.elevenlabs.io/v1/speech-to-text"
        )
