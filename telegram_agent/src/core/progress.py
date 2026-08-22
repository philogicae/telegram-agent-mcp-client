"""Async progress sink shared between tools and the bot handler."""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from contextvars import ContextVar, Token
from os import getenv

ProgressSink = Callable[[str], Awaitable[None]]
_sink: ContextVar[ProgressSink | None] = ContextVar("progress_sink", default=None)
_tracker: ContextVar = ContextVar("progress_tracker", default=None)


def default_max_lines() -> int:
    """Panel size from OPENCODE_SERVER_PROGRESS_LINES, tolerant of bad values."""
    try:
        return int(getenv("OPENCODE_SERVER_PROGRESS_LINES", "6"))
    except ValueError:
        return 6


def set_progress_sink(sink: ProgressSink | None) -> Token[ProgressSink | None]:
    """Bind a progress sink for the current task context; returns a reset token."""
    return _sink.set(sink)


def reset_progress_sink(token: Token[ProgressSink | None]) -> None:
    """Unbind the progress sink registered with the given token."""
    _sink.reset(token)


def set_turn_tracker(
    tracker: ProgressTracker | None,
) -> Token[ProgressTracker | None]:
    """Bind a turn-scoped tracker so consecutive tool calls share one panel."""
    return _tracker.set(tracker)


def reset_turn_tracker(token: Token[ProgressTracker | None]) -> None:
    """Unbind the turn tracker registered with the given token."""
    _tracker.reset(token)


def get_turn_tracker() -> ProgressTracker | None:
    """The tracker shared by all tool calls in the current turn, if any."""
    return _tracker.get()


def has_progress_sink() -> bool:
    """Whether a progress sink is bound in the current task context."""
    return _sink.get() is not None


async def emit_progress(line: str) -> None:
    """Forward a progress line to the sink bound in the current context, if any.

    Failures are swallowed: progress reporting must never break the tool run.
    """
    sink = _sink.get()
    if sink is None:
        return
    with suppress(Exception):
        await sink(line)


class ProgressTracker:
    """Reusable live-progress panel for long-running tools.

    Any tool can build one, feed it lines with :meth:`add_line`, optionally set
    a status line and a session link, and call :meth:`emit` after each change.
    Lines can also be updated in place by key (:meth:`set_line`), so a running
    tool line is replaced by its completion line instead of appended.
    The rendered panel is only forwarded to the sink when it actually changed,
    so unchanged progress never causes a second update.
    """

    def __init__(self, max_lines: int = 6, status: str = "🟢 Status: Working") -> None:
        self._lines: deque[tuple[str, str]] = deque(maxlen=max_lines)
        self._status = status
        self._session: tuple[str, str] | None = None
        self._last: str = ""
        self._seq: int = 0

    def set_status(self, status: str) -> None:
        """Override the status line (e.g. '✅ Status: Done')."""
        self._status = status

    def set_session(self, label: str, url: str) -> None:
        """Attach a clickable session link shown between status and logs."""
        self._session = (label, url)

    @staticmethod
    def _clip(line: str) -> str:
        """Truncate a line to 100 chars with a trailing '...'."""
        if len(line) > 100:
            line = line[:100].rstrip() + "..."
        return line

    def set_line(self, key: str, line: str) -> None:
        """Set or update a line by key; existing keys are replaced in place."""
        if not line:
            return
        line = self._clip(line)
        for i, (k, _) in enumerate(self._lines):
            if k == key:
                self._lines[i] = (key, line)
                return
        if not self._lines or self._lines[-1][1] != line:
            self._lines.append((key, line))

    def add_line(self, line: str) -> None:
        """Append a log line, skipping consecutive duplicates."""
        self._seq += 1
        self.set_line(f"line:{self._seq}", line)

    def render(self) -> str:
        """Render the panel as plain-text lines (status, session link, logs).

        It is appended AFTER the single tool-logs code block and replaced on
        each update, so it reads as temporary progress info — never confused
        with the final response. The logs live in a code block showing only
        the latest lines.
        """
        lines = [self._status]
        if self._session:
            label, url = self._session
            lines.append(f"🔗 Live: [{label}]({url})")
        if self._lines:
            inner = (
                "\n".join(line for _, line in self._lines)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            lines.append(f'<pre><code class="language-Logs">{inner}\n</code></pre>')
        return "\n".join(lines)

    async def emit(self) -> None:
        """Send the panel to the sink, skipping it if unchanged since last emit."""
        rendered = self.render()
        if rendered == self._last:
            return
        self._last = rendered
        await emit_progress(rendered)
