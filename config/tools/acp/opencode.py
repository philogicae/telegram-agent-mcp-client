"""Opencode bridge: drive remote coding sessions over the HTTP API of `opencode acp`."""

from contextlib import suppress
from datetime import UTC, datetime
from json import JSONDecodeError, dumps, loads
from os import getenv
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, urlsplit, urlunsplit

from aiohttp import BasicAuth, ClientError, ClientSession, ClientTimeout
from dotenv import load_dotenv
from langchain.tools import tool
from pydantic import Field

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

_RAW_URL = getenv("OPENCODE_ACP_URL", "")
_USERNAME = getenv("OPENCODE_SERVER_USERNAME", "opencode")
_PASSWORD = getenv("OPENCODE_SERVER_PASSWORD", "")
_TIMEOUT = float(getenv("OPENCODE_SERVER_TIMEOUT", "1200"))
_MAX_OUTPUT = int(getenv("OPENCODE_SERVER_MAX_OUTPUT", "20000"))
_NOT_CONFIGURED = "OPENCODE_ACP_URL not set"
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


_BASE_URL, _AUTH = _parse_url(_RAW_URL)


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


def _persist_sessions(sessions: list[dict[str, Any]]) -> None:
    """Upsert sessions into the JSONL file, keyed by session id (newest first)."""
    if not sessions:
        return
    now = datetime.now(UTC).isoformat()
    # Read existing entries into a dict keyed by session id
    existing: dict[str, dict[str, Any]] = {}
    if _SESSIONS_FILE.exists():
        for line in _SESSIONS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
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

    # Write back, sorted by created time descending (newest first)
    def _sort_key(e: dict[str, Any]) -> int:
        t = e.get("time") or {}
        return int(t.get("created") or 0)

    ordered = sorted(existing.values(), key=_sort_key, reverse=True)
    with _SESSIONS_FILE.open("w", encoding="utf-8") as f:
        for entry in ordered:
            f.write(dumps(entry, ensure_ascii=False) + "\n")


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


_client = OpencodeClient(_BASE_URL, _AUTH, _TIMEOUT)


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
    return {
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
    if not _BASE_URL:
        return {"error": _NOT_CONFIGURED}

    try:
        sessions = await _client.list_sessions(
            limit=max(1, min(limit, 100)), search=search
        )
    except _ERRORS as e:
        return {"error": f"Opencode server error: {e}"}

    with suppress(Exception):
        _persist_sessions(sessions)

    return {"sessions": [_format_session(s) for s in sessions]}


@tool
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
        A dict with session_id (pass it to `resume_dev_session` for follow-ups or `abort_dev_session` to stop a run), message_id,
        agent, model, output, tool_calls, files_changed, usage, or an error.
        Long runs can take several minutes.

    """
    if not _BASE_URL:
        return {"error": _NOT_CONFIGURED}

    session_id: str | None = None
    try:
        session = await _client.create_session(title or prompt[:60])
        session_id = session.get("id")
        if not session_id:
            return {"error": "Opencode server did not return a session id"}
        message = await _client.prompt(session_id, prompt)
    except _ERRORS as e:
        if session_id:
            with suppress(*_ERRORS):
                await _client.delete_session(session_id)
        return {"error": f"Opencode server error: {e}"}

    with suppress(Exception):
        full = await _client.session(session_id)
        if full:
            _persist_sessions([full])

    return _format_run(session_id, message)


@tool
async def resume_dev_session(
    session_id: Annotated[
        str,
        Field(
            description="Session id from a previous `init_dev_session` or `resume_dev_session` result (e.g. 'ses_...')"
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

    Args:
        session_id: Session id from a previous run.
        prompt: Follow-up instructions, relative to the session's existing context.

    Returns:
        A dict with session_id, message_id, agent, model, output, tool_calls,
        files_changed, usage, or an error.

    """
    if not _BASE_URL:
        return {"error": _NOT_CONFIGURED}
    if not session_id or not session_id.strip():
        return {"error": "session_id is required"}

    try:
        message = await _client.prompt(session_id.strip(), prompt)
    except _ERRORS as e:
        return {"error": f"Opencode server error: {e}"}

    with suppress(Exception):
        full = await _client.session(session_id.strip())
        if full:
            _persist_sessions([full])

    return _format_run(session_id.strip(), message)


@tool
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
    if not _BASE_URL:
        return {"error": _NOT_CONFIGURED}
    if not session_id or not session_id.strip():
        return {"error": "session_id is required"}

    try:
        await _client.abort(session_id.strip())
    except _ERRORS as e:
        return {"error": f"Opencode server error: {e}"}

    return {"aborted": session_id.strip()}
