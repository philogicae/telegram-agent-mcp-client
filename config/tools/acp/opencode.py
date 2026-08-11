"""Opencode bridge: drive remote coding sessions over the HTTP API of `opencode acp`."""

import asyncio
import base64
from contextlib import suppress
from datetime import UTC, datetime
from functools import wraps
from json import JSONDecodeError, dumps, loads
from os import getenv
from pathlib import Path
from time import monotonic
from typing import Annotated, Any
from urllib.parse import quote, urlsplit, urlunsplit

import aiofiles
from aiohttp import BasicAuth, ClientError, ClientSession, ClientTimeout
from dotenv import load_dotenv
from langchain.tools import tool
from pydantic import Field

from telegram_agent.src.core.progress import ProgressTracker, has_progress_sink

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

_RAW_URL = getenv("OPENCODE_ACP_URL", "")
_USERNAME = getenv("OPENCODE_SERVER_USERNAME", "opencode")
_PASSWORD = getenv("OPENCODE_SERVER_PASSWORD", "")
_TIMEOUT = float(getenv("OPENCODE_SERVER_TIMEOUT", "600"))
_MAX_OUTPUT = int(getenv("OPENCODE_SERVER_MAX_OUTPUT", "20000"))
_PROGRESS_POLL = float(getenv("OPENCODE_SERVER_PROGRESS_POLL", "3"))
_PROGRESS_LINES = int(getenv("OPENCODE_SERVER_PROGRESS_LINES", "6"))
_WEB_URL = getenv("OPENCODE_WEB_URL", "").strip().rstrip("/")
_ERRORS = (ClientError, PermissionError, RuntimeError, TimeoutError)


def _parse_url(raw: str) -> tuple[str, BasicAuth | None]:
    """Split a server URL into a clean base URL and its basic-auth credentials."""
    if not raw.strip():
        return "", None
    raw = raw.strip()
    try:
        parts = urlsplit(raw if "//" in raw else f"http://{raw}")
        netloc = parts.hostname or ""
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
    except ValueError:
        raise RuntimeError(f"Invalid OPENCODE_ACP_URL: {raw!r}") from None
    base = urlunsplit((parts.scheme or "http", netloc, parts.path.rstrip("/"), "", ""))
    user = parts.username or _USERNAME
    password = parts.password or _PASSWORD
    if not password:
        if parts.username:
            raise RuntimeError(
                "OPENCODE_ACP_URL has a username but no password; "
                "embed both (http://user:pass@host) or set OPENCODE_SERVER_PASSWORD"
            )
        return base, None
    return base, BasicAuth(user, password)


# Validate all required config ONCE at module load. On failure the tools stay
# registered (so the agent can see them) but every call short-circuits with
# the same error instead of repeating the check in each tool.
_CONFIG_ERROR: str | None = None
try:
    _BASE_URL, _AUTH = _parse_url(_RAW_URL)
except RuntimeError as e:
    _BASE_URL, _AUTH, _CONFIG_ERROR = "", None, str(e)
if not _BASE_URL and not _CONFIG_ERROR:
    _CONFIG_ERROR = "OPENCODE_ACP_URL not set"


def _require_config(func: Any) -> Any:
    """Short-circuit a tool with the startup config error when unconfigured."""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _CONFIG_ERROR:
            return {"error": _CONFIG_ERROR}
        return await func(*args, **kwargs)

    return wrapper


# ============================================================
# PERSISTENCE
# ============================================================

_DATA_DIR = Path(getenv("DATA_DIR", "./data")) / "opencode"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
with suppress(PermissionError):
    _DATA_DIR.chmod(0o777)


def _server_code(base_url: str) -> str:
    """Normalize the server URL into a filesystem-safe code (like gree_ac MAC)."""
    try:
        parts = urlsplit(base_url)
        host = (parts.hostname or "localhost").replace(".", "-")
        port = f"_{parts.port}" if parts.port else ""
        return f"{host}{port}"
    except Exception:
        return "default"


_SERVER_DIR = _DATA_DIR / _server_code(_BASE_URL)
_SERVER_DIR.mkdir(parents=True, exist_ok=True)
with suppress(PermissionError):
    _SERVER_DIR.chmod(0o777)

_SESSIONS_FILE = _SERVER_DIR / "opencode_sessions.jsonl"
_MAX_CACHED_SESSIONS = int(getenv("OPENCODE_SERVER_MAX_CACHED_SESSIONS", "100"))
# Serializes file access so concurrent tool calls don't corrupt the JSONL.
_sessions_lock = asyncio.Lock()


async def _persist_sessions(sessions: list[dict[str, Any]]) -> None:
    """Upsert sessions into the JSONL file, keyed by session id (newest first).

    Keeps at most `_MAX_CACHED_SESSIONS` (default 100): older entries are
    dropped, so the file never grows unbounded.
    """
    if not sessions:
        return
    now = datetime.now(UTC).isoformat()
    async with _sessions_lock:
        # Read existing entries into a dict keyed by session id
        existing: dict[str, dict[str, Any]] = {}
        if _SESSIONS_FILE.exists():
            async with aiofiles.open(_SESSIONS_FILE, encoding="utf-8") as f:
                async for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = loads(line)
                        if sid := entry.get("id"):
                            existing[sid] = entry
                    except JSONDecodeError:
                        continue
        # Upsert new sessions
        for s in sessions:
            sid = s.get("id")
            if not sid:
                continue
            entry = dict(s)
            entry["fetched_at"] = now
            existing[sid] = entry

        # Write back, sorted by created time descending (newest first),
        # trimmed to the most recent MAX_CACHED_SESSIONS
        def _sort_key(e: dict[str, Any]) -> int:
            t = e.get("time") or {}
            return int(t.get("created") or 0)

        ordered = sorted(existing.values(), key=_sort_key, reverse=True)[
            :_MAX_CACHED_SESSIONS
        ]
        async with aiofiles.open(_SESSIONS_FILE, "w", encoding="utf-8") as f:
            for entry in ordered:
                await f.write(dumps(entry, ensure_ascii=False) + "\n")


# ============================================================
# API CLIENT
# ============================================================


class OpencodeClient:
    """Minimal async client for the Opencode server HTTP API."""

    def __init__(self, base_url: str, auth: BasicAuth | None, timeout: float) -> None:
        """Store connection settings; sessions are opened per request."""
        self._base_url = base_url
        self._auth = auth
        self._timeout = ClientTimeout(total=timeout, connect=10, sock_connect=10)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Perform a request, returning the decoded JSON body. Raises on failure."""
        async with (
            ClientSession(auth=self._auth, timeout=self._timeout) as session,
            session.request(
                method, f"{self._base_url}{path}", params=params, json=payload
            ) as response,
        ):
            body = (await response.text()).strip()
            if response.status == 401:
                raise PermissionError(
                    "Unauthorized: set OPENCODE_SERVER_PASSWORD (and "
                    "OPENCODE_SERVER_USERNAME if not 'opencode'), or embed "
                    "credentials in OPENCODE_ACP_URL"
                )
            if response.status >= 400:
                raise RuntimeError(
                    f"{method} {path} failed [{response.status}]: {body[:300]}"
                )
            try:
                return loads(body) if body else None
            except JSONDecodeError:
                raise RuntimeError(
                    f"{method} {path}: non-JSON response: {body[:300]}"
                ) from None

    async def list_sessions(
        self, limit: int = 20, search: str | None = None
    ) -> list[dict[str, Any]]:
        """List sessions, optionally filtered by title search."""
        params: dict[str, Any] = {"limit": limit}
        if search:
            params["search"] = search
        return await self._request("GET", "/session", params=params) or []

    async def create_session(self, title: str | None = None) -> dict[str, Any]:
        """Create a session, optionally titled."""
        return (
            await self._request(
                "POST", "/session", payload={"title": title} if title else {}
            )
            or {}
        )

    async def session(self, session_id: str) -> dict[str, Any]:
        """Return a single session."""
        return (
            await self._request("GET", f"/session/{quote(session_id, safe='')}") or {}
        )

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        await self._request("DELETE", f"/session/{quote(session_id, safe='')}")

    async def abort(self, session_id: str) -> None:
        """Abort the current run of a session."""
        await self._request("POST", f"/session/{quote(session_id, safe='')}/abort")

    async def session_status(self) -> dict[str, Any]:
        """Return the status of all sessions known to the server (id -> status)."""
        return await self._request("GET", "/session/status") or {}

    async def prompt(self, session_id: str, text: str) -> dict[str, Any]:
        """Send a prompt and block until the agent finishes its turn."""
        payload: dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        return (
            await self._request(
                "POST",
                f"/session/{quote(session_id, safe='')}/message",
                payload=payload,
            )
            or {}
        )

    async def messages(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """List the most recent messages of a session (newest last)."""
        return (
            await self._request(
                "GET",
                f"/session/{quote(session_id, safe='')}/message",
                params={"limit": limit},
            )
            or []
        )


_client = OpencodeClient(_BASE_URL, _AUTH, _TIMEOUT)


# ============================================================
# PROGRESS WATCHER
# ============================================================


def _session_url(session_id: str) -> str:
    """Build a clickable web UI URL for a session, or '' when OPENCODE_WEB_URL is unset.

    Format mirrors the opencode web proxy:
    ``{web}/server/{base64url(web)}/session/{session_id}``
    """
    if not _WEB_URL or not session_id:
        return ""
    encoded = base64.urlsafe_b64encode(_WEB_URL.encode()).decode().rstrip("=")
    return f"{_WEB_URL}/server/{encoded}/session/{session_id}"


def _progress_line(part: dict[str, Any]) -> str | None:
    """Format a single message part as a short Telegram log line."""
    kind = part.get("type")
    if kind == "tool":
        state = part.get("state") or {}
        status = state.get("status")
        tool = part.get("tool") or "tool"
        title = state.get("title") or ""
        if status == "error":
            error = state.get("error")
            return f"❌ {tool}: {str(error)[:200]}"
        if status == "completed":
            return f"✅ {tool}: {title}" if title else f"✅ {tool}"
        if status == "running":
            return f"🔧 {tool}: {title}" if title else f"🔧 {tool}..."
        if status == "pending":
            return f"⏳ {tool}..."
    if kind == "patch":
        files = part.get("files") or []
        if files:
            shown = ", ".join(files[:6])
            more = f" (+{len(files) - 6})" if len(files) > 6 else ""
            return f"📄 {shown}{more}"
    return None


async def _watch_progress(session_id: str, tracker: ProgressTracker) -> None:
    """Poll the session for new message parts while a prompt runs, emitting progress lines.

    Starts at the moment of creation, so pre-existing history is not replayed.
    `ponytail: 3s polling; switch to /event SSE if finer granularity is needed.`
    """
    start_ms = int(datetime.now(UTC).timestamp() * 1000) - 1000
    emitted: dict[str, str] = {}  # part id -> last emitted text (for text parts)
    tool_status: dict[str, str] = {}  # part id -> last seen status
    while True:
        try:
            messages = await _client.messages(session_id, limit=20)
        except Exception:
            messages = []  # Transient poll failures must not break the run
        for message in messages:
            info = message.get("info") or {}
            created = (info.get("time") or {}).get("created") or 0
            if created < start_ms:
                continue
            if info.get("role") != "assistant":
                continue  # Don't echo the user's own prompt back as progress
            for part in message.get("parts") or []:
                pid = part.get("id")
                if not pid:
                    continue
                kind = part.get("type")
                if kind == "tool":
                    status = (part.get("state") or {}).get("status")
                    if status and tool_status.get(pid) != status:
                        tool_status[pid] = status
                        if line := _progress_line(part):
                            # Keyed by part id: the running line is replaced
                            # in place by its completion line, not appended.
                            tracker.set_line(f"tool:{pid}", line)
                elif kind in ("text", "reasoning"):
                    text = part.get("text") or ""
                    last = emitted.get(pid, "")
                    if len(text) > len(last):
                        emitted[pid] = text
                        if delta := text[len(last) :].strip():
                            prefix = "💭" if kind == "reasoning" else "💬"
                            tracker.set_line(f"{kind}:{pid}", f"{prefix} {delta}")
                elif kind == "patch":
                    if pid not in emitted:
                        emitted[pid] = "patch"
                        if line := _progress_line(part):
                            tracker.add_line(line)
        await tracker.emit()
        await asyncio.sleep(_PROGRESS_POLL)


# ============================================================
# HELPERS
# ============================================================


def _ms_iso(ms: Any) -> str | None:
    """Convert a millisecond epoch to an ISO-8601 string, or None."""
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def _truncate(text: str) -> str:
    """Clip long outputs so a single run cannot flood the context window."""
    if len(text) <= _MAX_OUTPUT:
        return text
    return f"{text[:_MAX_OUTPUT]}\n\n[...truncated {len(text) - _MAX_OUTPUT} chars]"


def _split_parts(parts: list[dict[str, Any]]) -> tuple[str, list[dict], list[str]]:
    """Split message parts into assistant text, a tool trace, and changed files."""
    texts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    files: list[str] = []
    for part in parts:
        kind = part.get("type")
        if kind == "text" and not part.get("synthetic"):
            if text := (part.get("text") or "").strip():
                texts.append(text)
        elif kind == "tool":
            state = part.get("state") or {}
            call = {"tool": part.get("tool"), "status": state.get("status")}
            if title := state.get("title"):
                call["title"] = title
            if state.get("status") == "error" and (error := state.get("error")):
                call["error"] = str(error)[:300]
            tool_calls.append(call)
        elif kind == "patch":
            files.extend(part.get("files") or [])
    return "\n\n".join(texts), tool_calls, sorted(set(files))


def _format_session(s: dict[str, Any]) -> dict[str, Any]:
    """Compact a session object into the fields the agent needs."""
    model = s.get("model") or {}
    time = s.get("time") or {}
    tokens = s.get("tokens") or {}
    result = {
        "session_id": s.get("id"),
        "title": s.get("title"),
        "agent": s.get("agent"),
        "model": "/".join(p for p in (model.get("providerID"), model.get("id")) if p)
        or None,
        "created": _ms_iso(time.get("created")),
        "updated": _ms_iso(time.get("updated")),
        "cost": s.get("cost"),
        "tokens": (tokens.get("input", 0) + tokens.get("output", 0)) or None,
        "files": (s.get("summary") or {}).get("files") or None,
    }
    if url := _session_url(s.get("id") or ""):
        result["session_url"] = url
    return result


def _format_run(session_id: str, message: dict[str, Any]) -> dict[str, Any]:
    """Shape a server message response into a compact tool result."""
    info = message.get("info") or {}
    output, tool_calls, files = _split_parts(message.get("parts") or [])
    model = "/".join(p for p in (info.get("providerID"), info.get("modelID")) if p)
    result: dict[str, Any] = {
        "session_id": session_id,
        "message_id": info.get("id"),
        "agent": info.get("agent") or info.get("mode"),
        "model": model or None,
        "output": _truncate(output) or "(agent returned no text output)",
    }
    if url := _session_url(session_id):
        result["session_url"] = url
    if tool_calls:
        result["tool_calls"] = tool_calls
    if files:
        result["files_changed"] = files
    tokens, cost = info.get("tokens"), info.get("cost")
    if tokens or cost is not None:
        result["usage"] = {"tokens": tokens, "cost": cost}
    if error := info.get("error"):
        result["error"] = (
            error.get("data", {}).get("message") or error.get("name")
            if isinstance(error, dict)
            else str(error)
        )
    return result


# ============================================================
# TOOLS
# ============================================================


@tool
@_require_config
async def list_dev_sessions(
    search: Annotated[
        str | None,
        Field(
            description="Case-insensitive substring filter on session titles (e.g. 'refactor'). Omit to list all recent sessions.",
            default=None,
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of sessions to return, 1-100 (default 20).",
            default=20,
        ),
    ] = 20,
) -> dict[str, Any]:
    """
    List Opencode coding sessions on the remote server, newest first.
    Usage: Call this to discover session_ids for `resume_dev_session` or `abort_dev_session`, or to review past tasks and their cost.

    Args:
        search: Optional case-insensitive title filter.
        limit: Maximum sessions to return, clamped to 1-100 (default 20).

    Returns:
        A dict with a list of sessions (session_id, title, agent, model,
        created, updated, cost, tokens, files), or an error.

    """

    try:
        sessions = await _client.list_sessions(
            limit=max(1, min(limit, 100)), search=search
        )
    except _ERRORS as e:
        return {"error": f"Opencode server error: {e}"}

    with suppress(Exception):
        await _persist_sessions(sessions)

    return {"sessions": [_format_session(s) for s in sessions]}


def _timeout_at() -> str:
    """Local wall-clock time of a timeout, for the '🔸 Timeout at <time>' marker."""
    return datetime.now().astimezone().strftime("%H:%M:%S")


def _timeout_result(
    session_id: str | None, url: str, extra: str = ""
) -> dict[str, Any]:
    """Timeout marker returned to the agent loop, which renders it as '🔸 ...'.

    Not an error: the run keeps going server-side, so the session is kept and
    the caller can re-attach with `watch_dev_session`.
    """
    return {
        "timeout": True,
        "timeout_at": _timeout_at(),
        "session_id": session_id or "",
        "session_url": url,
        "message": (
            "The session is still running on the server and its history is "
            "preserved. Re-attach with `watch_dev_session` to wait for the "
            "result without sending a new message." + extra
        ),
    }


async def _start_tracker(session_id: str) -> ProgressTracker | None:
    """Create a progress tracker bound to the session, with its live link."""
    tracker = (
        ProgressTracker(max_lines=_PROGRESS_LINES) if has_progress_sink() else None
    )
    if tracker:
        tracker.set_session(session_id, _session_url(session_id))
        await tracker.emit()
    return tracker


async def _wait_for_idle(
    session_id: str, deadline: float, tracker: ProgressTracker | None
) -> None:
    """Poll /session/status until the session is idle or the deadline passes."""
    while monotonic() < deadline:
        status = (await _client.session_status()) or {}
        state = (status.get(session_id) or {}).get("type")
        if state is None or state == "idle":
            return
        await asyncio.sleep(_PROGRESS_POLL)
    if tracker:
        tracker.set_status("🔸 Status: Timed out (still running)")
        await tracker.emit()
    raise TimeoutError


async def _wait_for_message(
    session_id: str, deadline: float, role: str = "assistant"
) -> dict[str, Any] | None:
    """Poll /session/{id}/message for the latest message matching `role`.

    If the deadline passes before a matching message appears, the most
    recent message of any role (if any) is returned as a fallback.
    """
    last: dict[str, Any] | None = None
    while monotonic() < deadline:
        messages = await _client.messages(session_id, limit=10)
        if messages:
            last = messages[-1]
        for m in reversed(messages):
            if (m.get("info") or {}).get("role") == role:
                return m
        await asyncio.sleep(_PROGRESS_POLL)
    return last


async def _run_with_watcher(
    session_id: str, prompt: str
) -> tuple[dict[str, Any], ProgressTracker | None]:
    """Run a prompt with live progress streaming; returns (message, tracker).

    Raises TimeoutError when the server does not finish within the configured
    timeout — the caller decides whether to keep or drop the session.
    """
    start = monotonic()
    deadline = start + _TIMEOUT
    tracker = await _start_tracker(session_id)
    watcher: asyncio.Task | None = None
    try:
        if tracker:
            watcher = asyncio.create_task(_watch_progress(session_id, tracker))
        try:
            message = await asyncio.wait_for(
                _client.prompt(session_id, prompt),
                timeout=deadline - monotonic(),
            )
        except TimeoutError:
            if tracker:
                tracker.set_status("🔸 Status: Timed out (still running)")
                await tracker.emit()
            raise
        await _wait_for_idle(session_id, deadline, tracker)
        newest = await _wait_for_message(session_id, deadline)
        if newest and (newest.get("info") or {}).get("role") == "assistant":
            message = newest
    finally:
        if watcher:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher
    return message, tracker


@tool
@_require_config
async def init_dev_session(
    prompt: Annotated[
        str,
        Field(
            description="Detailed, self-contained task for the coding agent: goal, relevant files/project paths, constraints, and the expected outcome. The agent has no prior context, so include everything it needs."
        ),
    ],
    title: Annotated[
        str | None,
        Field(
            description="Short session title, must be prefixed with '[acp]' (e.g. '[acp] fix auth bug'). Defaults to the first 60 chars of the prompt.",
            default=None,
        ),
    ] = None,
) -> dict[str, Any]:
    """
    Start a new Opencode coding session and run a task on it, blocking until the agent finishes.
    Usage: For any coding/development task (write, fix, refactor, review code). Prefer this over `resume_dev_session` for unrelated tasks.

    Args:
        prompt: Detailed, self-contained description of the task.
        title: Optional short session title prefixed with '[acp]'.

    Returns:
        A dict with session_id (pass it to `resume_dev_session` for follow-ups, `watch_dev_session` to wait out a timeout, or `abort_dev_session` to stop a run), message_id,
        agent, model, output, tool_calls, files_changed, usage, session_url, or an error.
        While the run is in progress, a live progress panel (status, session
        link, tool/file logs) is streamed to the chat.
        Runs time out after 10 minutes by default; a timeout is NOT an error:
        the session keeps running server-side, returns with `timeout: True`,
        and can be re-attached via `watch_dev_session`.

    """

    session_id: str | None = None
    tracker: ProgressTracker | None = None
    try:
        session = await _client.create_session(title or prompt[:60])
        session_id = session.get("id")
        if not session_id:
            return {"error": "Opencode server did not return a session id"}
        message, tracker = await _run_with_watcher(session_id, prompt)
    except TimeoutError:
        return _timeout_result(session_id, _session_url(session_id or ""))
    except _ERRORS as e:
        if session_id:
            with suppress(*_ERRORS):
                await _client.delete_session(session_id)
        return {"error": f"Opencode server error: {e}"}
    if tracker:
        tracker.set_status("✅ Status: Done")
        await tracker.emit()

    with suppress(Exception):
        full = await _client.session(session_id)
        if full:
            await _persist_sessions([full])

    return _format_run(session_id, message)


@tool
@_require_config
async def resume_dev_session(
    session_id: Annotated[
        str,
        Field(
            description="Session id from a previous `init_dev_session`, `resume_dev_session`, or `watch_dev_session` result (e.g. 'ses_...')"
        ),
    ],
    prompt: Annotated[
        str,
        Field(
            description="Follow-up instructions; the agent keeps the full history and working state of that session, so only describe what changes relative to it"
        ),
    ],
) -> dict[str, Any]:
    """
    Continue a previous Opencode coding session with new instructions, keeping its full context.
    Usage: For 'continue', 'resume', or follow-up changes on an earlier run. Use `init_dev_session` instead for unrelated tasks.
    After a timeout, prefer `watch_dev_session` to wait out the running task without sending a new message.

    Args:
        session_id: Session id from a previous run.
        prompt: Follow-up instructions, relative to the session's existing context.

    Returns:
        A dict with session_id, message_id, agent, model, output, tool_calls,
        files_changed, usage, session_url, or an error.
        While the run is in progress, a live progress panel (status, session
        link, tool/file logs) is streamed to the chat.
        Runs time out after 10 minutes by default; a timeout is NOT an error:
        the session keeps running server-side, returns with `timeout: True`,
        and can be re-attached via `watch_dev_session`.

    """
    if not session_id or not session_id.strip():
        return {"error": "session_id is required"}
    sid = session_id.strip()

    try:
        message, tracker = await _run_with_watcher(sid, prompt)
    except TimeoutError:
        return _timeout_result(sid, _session_url(sid))
    except _ERRORS as e:
        return {"error": f"Opencode server error: {e}"}
    if tracker:
        tracker.set_status("✅ Status: Done")
        await tracker.emit()

    with suppress(Exception):
        full = await _client.session(sid)
        if full:
            await _persist_sessions([full])

    return _format_run(sid, message)


@tool
@_require_config
async def abort_dev_session(
    session_id: Annotated[
        str,
        Field(
            description="Session id of the run to stop (e.g. 'ses_...'), from `init_dev_session`, `resume_dev_session`, or `list_dev_sessions`"
        ),
    ],
) -> dict[str, Any]:
    """
    Abort the currently running task of an Opencode session, without deleting the session or its history.
    Usage: When a run is stuck, taking too long, or the user asks to stop/cancel it. The session can still be resumed afterwards.

    Args:
        session_id: Session id of the run to abort.

    Returns:
        A dict confirming the abort, or an error.

    """
    if not session_id or not session_id.strip():
        return {"error": "session_id is required"}

    try:
        await _client.abort(session_id.strip())
    except _ERRORS as e:
        return {"error": f"Opencode server error: {e}"}

    sid = session_id.strip()
    result: dict[str, Any] = {"aborted": sid}
    if url := _session_url(sid):
        result["session_url"] = url
    return result


@tool
@_require_config
async def watch_dev_session(
    session_id: Annotated[
        str,
        Field(
            description="Session id of a run that timed out (e.g. 'ses_...'), from the `timeout` result of `init_dev_session` or `resume_dev_session`"
        ),
    ],
    max_wait: Annotated[
        int,
        Field(
            description="Max seconds to wait for the run to finish (default 600 = 10 min).",
            default=600,
        ),
    ] = 600,
) -> dict[str, Any]:
    """
    Re-attach to a session whose run timed out and wait for it to finish WITHOUT sending a new message.
    Usage: After `init_dev_session`/`resume_dev_session` returned `timeout: true`, the task is still running
    server-side. Call this with the same session_id to stream its progress and get the final result.
    Also useful to check whether a previous run already completed.

    Args:
        session_id: Session id from the `timeout` result.
        max_wait: Max seconds to wait before returning another `timeout` marker.

    Returns:
        A dict with session_id, message_id, agent, model, output, tool_calls,
        files_changed, usage, session_url, or a `timeout` marker (not an error)
        when the run is still going after `max_wait` seconds.

    """
    if not session_id or not session_id.strip():
        return {"error": "session_id is required"}
    sid = session_id.strip()

    tracker = await _start_tracker(sid)
    watcher: asyncio.Task | None = None
    deadline = monotonic() + max_wait
    try:
        if tracker:
            watcher = asyncio.create_task(_watch_progress(sid, tracker))
        await _wait_for_idle(sid, deadline, tracker)
        newest = await _wait_for_message(sid, deadline)
        if not newest:
            return {"error": "No messages found for this session"}
        if tracker:
            tracker.set_status("✅ Status: Done")
            await tracker.emit()
        return _format_run(sid, newest)
    except TimeoutError:
        return _timeout_result(sid, _session_url(sid))
    except _ERRORS as e:
        return {"error": f"Opencode server error: {e}"}
    finally:
        if watcher:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher
