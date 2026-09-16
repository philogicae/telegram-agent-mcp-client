"""Tests for ``core/progress.py`` and ``core/cancel.py``."""

import asyncio

import pytest

from telegram_agent.src.core.cancel import (
    active_turn_cancelled,
    reset_active_turn_cancel,
    set_active_turn_cancel,
)
from telegram_agent.src.core.progress import (
    ProgressTracker,
    TurnTrackerPanel,
    default_max_lines,
    emit_progress,
    get_turn_tracker,
    has_progress_sink,
    reset_progress_sink,
    reset_turn_tracker,
    set_progress_sink,
    set_turn_tracker,
)


class TestDefaultMaxLines:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("OPENCODE_SERVER_PROGRESS_LINES", raising=False)
        assert default_max_lines() == 6

    def test_custom(self, monkeypatch):
        monkeypatch.setenv("OPENCODE_SERVER_PROGRESS_LINES", "12")
        assert default_max_lines() == 12

    def test_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("OPENCODE_SERVER_PROGRESS_LINES", "many")
        assert default_max_lines() == 6


class TestSinkContext:
    async def test_no_sink_is_noop(self):
        assert not has_progress_sink()
        await emit_progress("ignored")

    async def test_sink_receives_lines(self):
        received: list[str] = []

        async def sink(line: str) -> None:
            received.append(line)

        token = set_progress_sink(sink)
        try:
            assert has_progress_sink()
            await emit_progress("hello")
        finally:
            reset_progress_sink(token)
        assert received == ["hello"]
        assert not has_progress_sink()

    async def test_sink_failures_are_swallowed(self):
        async def broken(_line: str) -> None:
            raise RuntimeError("boom")

        token = set_progress_sink(broken)
        try:
            await emit_progress("hello")  # must not raise
        finally:
            reset_progress_sink(token)


class TestTurnTracker:
    def test_none_by_default(self):
        assert get_turn_tracker() is None

    def test_set_and_reset(self):
        tracker = TurnTrackerPanel()
        token = set_turn_tracker(tracker)
        assert get_turn_tracker() is tracker
        reset_turn_tracker(token)
        assert get_turn_tracker() is None


class TestProgressTracker:
    def test_clip_truncates_with_ellipsis(self):
        tracker = ProgressTracker()
        tracker.add_line("x" * 150)
        line = tracker.render()
        assert "x" * 100 + "..." in line

    def test_set_line_ignores_empty(self):
        tracker = ProgressTracker()
        tracker.set_line("k", "")
        assert not tracker._lines

    def test_set_line_replaces_by_key(self):
        tracker = ProgressTracker()
        tracker.set_line("k", "first")
        tracker.set_line("k", "second")
        assert [line for _, line in tracker._lines] == ["second"]

    def test_add_line_skips_consecutive_duplicates(self):
        tracker = ProgressTracker()
        tracker.add_line("same")
        tracker.add_line("same")
        tracker.add_line("other")
        assert [line for _, line in tracker._lines] == ["same", "other"]

    def test_max_lines_bounds_the_deque(self):
        tracker = ProgressTracker(max_lines=2)
        for i in range(5):
            tracker.add_line(f"line {i}")
        assert [line for _, line in tracker._lines] == ["line 3", "line 4"]

    def test_render_includes_status_session_and_escaped_logs(self):
        tracker = ProgressTracker(status="🟢 Working")
        tracker.set_session("dev", "https://x")
        tracker.add_line("a < b & c")
        rendered = tracker.render()
        assert rendered.startswith("🟢 Working\n")
        assert "🔗 Live: [dev](https://x)" in rendered
        assert "a &lt; b &amp; c" in rendered
        assert '<code class="language-Logs">' in rendered

    def test_render_without_lines(self):
        assert ProgressTracker(status="s").render() == "s"

    async def test_emit_skips_unchanged_and_sends_changes(self):
        received: list[str] = []

        async def sink(line: str) -> None:
            received.append(line)

        tracker = ProgressTracker()
        token = set_progress_sink(sink)
        try:
            await tracker.emit()
            await tracker.emit()  # unchanged
            tracker.add_line("new")
            await tracker.emit()
        finally:
            reset_progress_sink(token)
        assert len(received) == 2

    async def test_sub_tracker_forwards_to_parent(self):
        received: list[str] = []

        async def sink(line: str) -> None:
            received.append(line)

        panel = TurnTrackerPanel()
        sub = panel.tracker("session")
        token = set_progress_sink(sink)
        try:
            sub.set_status("sub")
            await sub.emit()
        finally:
            reset_progress_sink(token)
        assert received
        assert "sub" in received[0]


class TestTurnTrackerPanel:
    def test_tracker_reused_per_session(self):
        panel = TurnTrackerPanel()
        assert panel.tracker("a") is panel.tracker("a")
        assert panel.tracker("a") is not panel.tracker("b")

    def test_render_joins_sections_in_order(self):
        panel = TurnTrackerPanel()
        panel.tracker("first").set_status("one")
        panel.tracker("second").set_status("two")
        assert panel.render() == "one\n\ntwo"

    async def test_emit_dedupes(self):
        received: list[str] = []

        async def sink(line: str) -> None:
            received.append(line)

        panel = TurnTrackerPanel()
        panel.tracker("a").set_status("one")
        token = set_progress_sink(sink)
        try:
            await panel.emit()
            await panel.emit()
            panel.tracker("b").set_status("two")
            await panel.emit()
        finally:
            reset_progress_sink(token)
        assert len(received) == 2


class TestCancel:
    def test_no_event_means_not_cancelled(self):
        assert active_turn_cancelled() is False

    async def test_event_lifecycle(self):
        event = asyncio.Event()
        token = set_active_turn_cancel(event)
        try:
            assert active_turn_cancelled() is False
            event.set()
            assert active_turn_cancelled() is True
        finally:
            reset_active_turn_cancel(token)
        assert active_turn_cancelled() is False


@pytest.mark.parametrize("value", ["-1", "0"])
def test_default_max_lines_zero_and_negative(monkeypatch, value):
    monkeypatch.setenv("OPENCODE_SERVER_PROGRESS_LINES", value)
    assert default_max_lines() == int(value)
