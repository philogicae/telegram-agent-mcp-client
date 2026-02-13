"""BetaSeries tools: check episode planning and mark episodes as downloaded."""

from collections import defaultdict
from datetime import datetime
from os import getenv
from typing import Annotated, Any
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from langchain.tools import tool
from pydantic import Field

load_dotenv()

BETASERIES_API_KEY_TOKEN = getenv("BETASERIES_API_KEY_TOKEN", "")
BETASERIES_API_KEY, BETASERIES_API_TOKEN = (
    BETASERIES_API_KEY_TOKEN.split(":", 1)
    if ":" in BETASERIES_API_KEY_TOKEN
    else ("", "")
)
BETASERIES_USERNAME = getenv("BETASERIES_USERNAME", "")
BASE_URL = "https://api.betaseries.com"


def _date_to_weekday(date: str) -> str:
    """Convert a date to a weekday."""
    return datetime.strptime(date, "%Y-%m-%d").astimezone().strftime("%A")


def _headers(auth: bool = False) -> dict[str, str]:
    """Build request headers, optionally including the auth token."""
    h: dict[str, str] = {"X-BetaSeries-Key": BETASERIES_API_KEY}
    if auth:
        h["X-BetaSeries-Token"] = BETASERIES_API_TOKEN
    return h


def _get(endpoint: str, params: dict) -> dict[str, Any]:
    """Perform a GET request to the BetaSeries API."""
    url = f"{BASE_URL}{endpoint}?{urlencode(params)}"
    response = requests.get(url, headers=_headers(), timeout=10)
    response.raise_for_status()
    return response.json()


def _post(endpoint: str, params: dict) -> dict[str, Any]:
    """Perform an authenticated POST request to the BetaSeries API."""
    url = f"{BASE_URL}{endpoint}?{urlencode(params)}"
    response = requests.post(url, headers=_headers(auth=True), timeout=10)
    response.raise_for_status()
    return response.json()


def _find_user_id(username: str) -> int | None:
    """Resolve a BetaSeries username to its user ID."""
    data = _get("/search/all", {"query": username})
    for user in data.get("users", []):
        if user.get("login", "").lower() == username.lower():
            return user["id"]
    return None


def _fetch_planning(user_id: int, undownloaded: bool, month: str | None) -> list[Any]:
    """Fetch episode planning for a given user."""
    params = {"id": user_id}
    if undownloaded:
        params["unseen"] = "true"
    if month:
        params["month"] = month
    data = _get("/planning/member", params)
    return data.get("episodes", [])


@tool
def check_series_planning(
    username: Annotated[
        str | None,
        Field(
            description="Optional username to check planning for (default: configured user)",
            default=None,
        ),
    ] = None,
    undownloaded: Annotated[
        bool,
        Field(
            description="Only return undownloaded episodes",
            default=True,
        ),
    ] = True,
    month: Annotated[
        str | None,
        Field(
            description="Optional month to check in YYYY-MM format (e.g. '2026-02')",
            default=None,
        ),
    ] = None,
    max_items: Annotated[
        int,
        Field(
            description="Optional maximum number of items to return",
            default=20,
        ),
    ] = 20,
) -> dict[str, Any]:
    """
    Check the BetaSeries episode release planning. Default calling: all arguments omitted.
    Usage: When needing to check episodes' release dates or undownloaded episodes.

    Args:
        username: Optional username to check planning for (default: configured user).
        month: Optional month to check in YYYY-MM format (e.g. '2026-02').
        undownloaded: If True, only return undownloaded episodes. Defaults to True.
        max_items: Optional maximum number of items to return.

    Returns:
        A dict mapping each date ({YYYY-MM-DD} > {WEEKDAY}) to a list of episode dicts with id, code, date, show, and user info, or an error.

    """
    user = username or BETASERIES_USERNAME
    if not BETASERIES_API_KEY:
        return {"error": "BETASERIES_API_KEY_TOKEN not set"}
    if not user:
        return {"error": "user not set"}

    user_id = _find_user_id(user)
    if user_id is None:
        return {"error": f"User '{user}' not found on BetaSeries"}

    episodes = _fetch_planning(user_id, undownloaded, month)
    if not episodes:
        return {"info": "No episodes found"}

    planning: dict[str, list[dict]] = defaultdict(list)
    count = 0
    for ep in episodes:
        eid = ep.get("id")
        date = ep.get("date")
        code = ep.get("code")
        show = ep.get("show", {})
        user = ep.get("user", {})
        if not date or not code:
            continue
        if count >= max_items:
            break
        planning[f"{date} > {_date_to_weekday(date)}"].append(
            {
                "id": eid,
                "code": code,
                "date": date,
                "show": {
                    "id": show.get("id"),
                    "title": show.get("title"),
                    "creation": show.get("creation"),
                    "status": show.get("status"),
                },
                "user": {
                    "downloaded": user.get("seen", False),
                    "downloaded_date": user.get("seen_date"),
                },
            }
        )
        count += 1
    return dict(planning)


@tool
def mark_episode_downloaded(
    episode_id: Annotated[
        int,
        Field(
            description="The BetaSeries episode ID to mark as downloaded",
        ),
    ],
) -> dict[str, Any]:
    """
    Mark a BetaSeries episode as downloaded for the default authenticated user.
    Usage: After downloading an episode, you must automatically mark it.

    Args:
        episode_id: The BetaSeries episode ID (numeric) to mark as downloaded.

    Returns:
        An episode dict with id, code, date, show, and user info, or an error.

    """
    if not BETASERIES_API_KEY or not BETASERIES_API_TOKEN:
        return {"error": "BETASERIES_API_KEY_TOKEN not set or missing token"}

    try:
        data = _post("/episodes/watched", {"id": episode_id})
    except requests.RequestException as e:
        return {"error": f"API request failed: {e}"}

    ep = data.get("episode", {})
    eid = ep.get("id")
    date = ep.get("date")
    code = ep.get("code")
    show = ep.get("show", {})
    user = ep.get("user", {})
    if not date or not code:
        return {"error": "episode not found"}
    return {
        "id": eid,
        "code": code,
        "date": date,
        "show": {
            "id": show.get("id"),
            "title": show.get("title"),
            "creation": show.get("creation"),
            "status": show.get("status"),
        },
        "user": {
            "downloaded": user.get("seen", False),
            "downloaded_date": user.get("seen_date"),
        },
    }
