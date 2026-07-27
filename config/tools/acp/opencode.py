"""Opencode bridge: drive remote coding sessions over the HTTP API of `opencode acp`."""

from datetime import UTC, datetime
from json import JSONDecodeError, loads
from os import getenv
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

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


def _parse_url(raw: str) -> tuple[str, BasicAuth | None]:
    """Split a server URL into a clean base URL and its basic-auth credentials."""
    if not raw.strip():
        return "", None
    parts = urlsplit(raw.strip() if "//" in raw else f"http://{raw.strip()}")
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    base = urlunsplit((parts.scheme or "http", netloc, parts.path.rstrip("/"), "", ""))
    user = parts.username or _USERNAME
    password = parts.password or _PASSWORD
    return base, BasicAuth(user, password) if password else None


_BASE_URL, _AUTH = _parse_url(_RAW_URL)


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
        return await self._request("GET", f"/session/{session_id}") or {}

    async def prompt(self, session_id: str, text: str) -> dict[str, Any]:
        """Send a prompt and block until the agent finishes its turn."""
        payload: dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        return (
            await self._request(
                "POST", f"/session/{session_id}/message", payload=payload
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
        "tokens": tokens.get("input", 0) + tokens.get("output", 0) or None,
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
async def list_sessions(
    search: Annotated[
        str | None,
        Field(
            description="Optional case-insensitive title filter (e.g. 'refactor' to find sessions with that in the title)",
            default=None,
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of sessions to return (default 20)",
            default=20,
        ),
    ] = 20,
) -> dict[str, Any]:
    """
    List Opencode coding sessions on the remote server, newest first.
    Usage: Call this to find session_ids for `resume_session`, or to check what tasks have been run.

    Args:
        search: Optional case-insensitive title filter.
        limit: Maximum sessions to return (default 20).

    Returns:
        A dict with a list of sessions (session_id, title, agent, model,
        created, updated, cost, tokens, files), or an error.

    """
    if not _BASE_URL:
        return {"error": _NOT_CONFIGURED}

    try:
        sessions = await _client.list_sessions(limit=limit, search=search)
    except (ClientError, PermissionError, RuntimeError, TimeoutError) as e:
        return {"error": f"Opencode server error: {e}"}

    return {"sessions": [_format_session(s) for s in sessions]}


@tool
async def init_session(
    prompt: Annotated[
        str,
        Field(
            description="Detailed, self-contained task for the coding agent: what to do, in which files/project, and the expected result"
        ),
    ],
    title: Annotated[
        str | None,
        Field(
            description="Short session title, must be prefixed with '[acp]' (e.g. '[acp] fix auth bug')",
            default=None,
        ),
    ] = None,
) -> dict[str, Any]:
    """
    Start a new Opencode coding session and run a task on it, blocking until the agent finishes.
    Usage: For any coding/development task (write, fix, refactor, review code).

    Args:
        prompt: Detailed, self-contained description of the task.
        title: Optional short session title.

    Returns:
        A dict with session_id (reuse it with `resume_session`), message_id,
        agent, model, output, tool_calls, files_changed, usage, or an error.
        Long runs can take several minutes.

    """
    if not _BASE_URL:
        return {"error": _NOT_CONFIGURED}

    try:
        session = await _client.create_session(title or prompt[:60])
        session_id = session.get("id")
        if not session_id:
            return {"error": "Opencode server did not return a session id"}
        message = await _client.prompt(session_id, prompt)
    except (ClientError, PermissionError, RuntimeError, TimeoutError) as e:
        return {"error": f"Opencode server error: {e}"}

    return _format_run(session_id, message)


@tool
async def resume_session(
    session_id: Annotated[
        str,
        Field(
            description="Session id returned by a previous `init_session` call (e.g. 'ses_...')"
        ),
    ],
    prompt: Annotated[
        str,
        Field(
            description="Continuation instructions; the agent keeps the full history of that session"
        ),
    ],
) -> dict[str, Any]:
    """
    Continue a previous Opencode coding session with new instructions, keeping its full context.
    Usage: For 'continue', 'resume', or follow-up changes on an earlier run.

    Args:
        session_id: Session id returned by a previous `init_session` call.
        prompt: Continuation instructions.

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
    except (ClientError, PermissionError, RuntimeError, TimeoutError) as e:
        return {"error": f"Opencode server error: {e}"}

    return _format_run(session_id.strip(), message)
