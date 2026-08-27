"""HTTP relay: lets trusted services inject prompts into the agent pipeline.

Bots never receive bot-authored messages on Telegram (not even their own),
so services (e.g. torrent-search webapp approval) POST the directive here
instead of relaying it through the Bot API.
"""

from asyncio import Event, create_task
from json import loads
from os import getenv
from secrets import compare_digest
from time import time
from typing import Any

from aiohttp import web
from telebot.types import Message

from .abstract import AgenticBot
from .handlers import telegram_chat

_RELAY_PORT = int(getenv("AGENT_RELAY_PORT") or 4041)
_RELAY_TOKEN = getenv("AGENT_RELAY_TOKEN") or None


def _log_task_failure(instance: AgenticBot, task: Any) -> None:
    exc = task.exception() if not task.cancelled() else None
    if exc:
        instance.log.exception(exc)


async def _handle_relay(instance: AgenticBot, request: web.Request) -> web.Response:
    if not _RELAY_TOKEN or not compare_digest(
        request.headers.get("X-Relay-Token") or "", _RELAY_TOKEN
    ):
        return web.json_response({"error": "unauthorized"}, status=401)
    try:
        data = loads(await request.text())
        chat_id = int(data["chat_id"])
        sender = str(data["sender"] or "").strip()
        prompt = str(data["prompt"] or "").strip()
        if not sender or not prompt:
            raise ValueError("sender and prompt are required")
    except Exception:
        return web.json_response({"error": "invalid payload"}, status=400)
    notice = str(data.get("notice") or "").strip()
    instance.log.info(
        f"Relaying message from {sender} to {chat_id}: "
        f"{prompt[:100]}{'...' if len(prompt) > 100 else ''}"
    )
    if notice:
        await instance.bot.send(chat_id, notice)

    msg = Message.de_json(
        {
            "message_id": 0,
            "from": {"id": 0, "is_bot": False, "first_name": sender},
            "chat": {"id": chat_id, "type": "private"},
            "date": int(time()),
            "text": prompt,
        }
    )

    async def run() -> None:
        await telegram_chat(instance, msg)

    task = create_task(run())
    task.add_done_callback(lambda t: _log_task_failure(instance, t))
    return web.json_response({"status": "accepted"})


def start_relay(instance: AgenticBot) -> web.Application | None:
    """Build the relay app, or None when AGENT_RELAY_TOKEN is unset."""
    if not _RELAY_TOKEN:
        return None
    app = web.Application()
    app.router.add_post("/relay", lambda r: _handle_relay(instance, r))
    return app


async def serve(app: web.Application) -> None:
    """Serve the relay app until cancelled."""
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", _RELAY_PORT).start()
    await Event().wait()
