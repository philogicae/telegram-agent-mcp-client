"""Cooperative cancellation for the active per-chat turn (supersede, TAM-21).

The Telegram worker runs exactly one turn per chat; a new message from the same
chat sets the active turn's cancel event so the turn stops at its next step.
Chunk-level checks live in `bot/handlers/telegram.py`, but a turn blocked inside
a long in-process tool (e.g. a dev-session watch) never yields a chunk until the
tool returns. The event is therefore exposed through a contextvar that tools can
poll from their own wait loops.
"""

from asyncio import Event
from contextvars import ContextVar, Token

_active_turn_cancel: ContextVar[Event | None] = ContextVar(
    "active_turn_cancel", default=None
)


def set_active_turn_cancel(event: Event | None) -> Token[Event | None]:
    """Bind the current turn's cancel event for the duration of the turn."""
    return _active_turn_cancel.set(event)


def reset_active_turn_cancel(token: Token[Event | None]) -> None:
    """Restore the previous binding once the turn is over."""
    _active_turn_cancel.reset(token)


def active_turn_cancelled() -> bool:
    """True when the current turn was superseded by a newer same-chat message."""
    event = _active_turn_cancel.get()
    return bool(event and event.is_set())
