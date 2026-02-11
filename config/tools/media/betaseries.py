"""Check the BetaSeries episode release planning."""

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

BETASERIES_API_KEY = getenv("BETASERIES_API_KEY", "")
BETASERIES_USERNAME = getenv("BETASERIES_USERNAME", "")
BASE_URL = "https://api.betaseries.com"


def _date_to_weekday(date: str) -> str:
    """Convert a date to a weekday."""
    return datetime.strptime(date, "%Y-%m-%d").astimezone().strftime("%A")


def _get(endpoint: str, params: dict) -> dict[str, Any]:
    """Perform a GET request to the BetaSeries API."""
    url = f"{BASE_URL}{endpoint}?{urlencode(params)}"
    headers = {"X-BetaSeries-Key": BETASERIES_API_KEY}
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


def _find_user_id(username: str) -> int | None:
    """Resolve a BetaSeries username to its user ID."""
    data = _get("/search/all", {"query": username})
    for user in data.get("users", []):
        if user.get("login", "").lower() == username.lower():
            return user["id"]
    return None


def _fetch_planning(user_id: int, unseen: bool, month: str | None) -> list[Any]:
    params = {"id": user_id}
    if unseen:
        params["unseen"] = str(unseen).lower()
    if month:
        params["month"] = month
    data = _get("/planning/member", params)
    return data.get("episodes", [])


@tool
def check_betaseries_planning(
    username: Annotated[
        str | None,
        Field(
            description="Optional username to check planning for (default: configured user)",
            default=None,
        ),
    ] = None,
    unseen: Annotated[
        bool,
        Field(
            description="Only return unseen episodes",
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
    Check the BetaSeries episode release planning. Default behavior: no arguments provided.
    Usage: When needing to check episodes release dates or unseen episodes.

    Args:
        username: Optional username to check planning for (default: configured user).
        month: Optional month to check in YYYY-MM format (e.g. '2026-02').
        unseen: If True, only return unseen episodes. Defaults to True.
        max_items: Optional maximum number of items to return.

    Returns:
        A dict mapping each date (YYYY-MM-DD) to a list of episodes formatted as 'Show Title SxxExx'.

    """
    user = username or BETASERIES_USERNAME
    if not BETASERIES_API_KEY:
        return {"error": "BETASERIES_API_KEY not set"}
    if not user:
        return {"error": "user not set"}

    user_id = _find_user_id(user)
    if user_id is None:
        return {"error": f"User '{user}' not found on BetaSeries"}

    episodes = _fetch_planning(user_id, unseen, month)
    if not episodes:
        return {"info": "No episodes found"}

    planning: dict[str, list[str]] = defaultdict(list)
    count = 0
    for ep in episodes:
        date = ep.get("date")
        show_title = ep.get("show", {}).get("title")
        code = ep.get("code")
        if date and show_title and code and count <= max_items:
            planning[f"{date} ({_date_to_weekday(date)})"].append(
                f"{show_title} {code}"
            )
            count += 1
    return dict(planning)
