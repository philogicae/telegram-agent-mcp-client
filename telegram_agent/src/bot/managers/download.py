from asyncio import gather, sleep
from json import loads
from os import getenv
from typing import Any

from dotenv import load_dotenv
from httpx import AsyncClient
from pydantic import BaseModel
from rqbit_client import RqbitClient

from ..abstract import AgenticBot, Manager
from ..utils import progress_bar

load_dotenv()
MEDIA_LIB_REFRESH = getenv("MEDIA_LIB_REFRESH")
SEPARATOR = "___________________________________"


class Torrent(BaseModel):
    name: str
    stats: dict[str, Any] | bool


class Message(BaseModel):
    obj: Any
    prev: str
    torrent_ids: set[str]


class DownloadManager(Manager):
    instance: AgenticBot
    client: RqbitClient
    torrents: dict[str, Torrent]
    chats: dict[int, Message]
    delay: float = 4

    def __init__(self, instance: AgenticBot, delay: float | None = None):
        self.name = "Torrent Manager"
        self.instance = instance
        self.client = RqbitClient()
        self.torrents = {}
        self.chats = {}
        if delay:
            self.delay = delay

    async def start(self) -> None:
        while True:
            if self.torrents:
                await self.update_torrent_stats()
                await self.update_chats()
            await sleep(self.delay)

    async def notify(self, chat_id: int, data: str) -> None:
        torrent = loads(data)
        self.torrents[torrent["details"]["info_hash"]] = Torrent(
            name=torrent["details"]["name"], stats=True
        )
        if chat_id not in self.chats:
            self.chats[chat_id] = Message(obj=None, prev="", torrent_ids=set())
        else:  # Recreate message
            old_message_obj = self.chats[chat_id].obj
            if old_message_obj:
                await self.instance.bot.unpin(old_message_obj)
                await self.instance.bot.delete(old_message_obj)
            self.chats[chat_id].obj = None
        self.chats[chat_id].torrent_ids.add(torrent["details"]["info_hash"])
        await self.refresh_media_lib()

    async def refresh_media_lib(self) -> None:
        if MEDIA_LIB_REFRESH:
            try:
                async with AsyncClient() as http:
                    await http.post(MEDIA_LIB_REFRESH)
            except Exception as e:
                self.instance.log.error(f"Refreshing media lib: {e}")

    async def update_torrent_stats(self) -> None:
        if not self.torrents:
            return
        results = await gather(
            *[self.client.get_torrent_stats(torrent_id) for torrent_id in self.torrents]
        )
        for torrent_id, stats in zip(self.torrents.keys(), results):
            self.torrents[torrent_id].stats = (
                stats
                if isinstance(stats, dict) and not stats.get("finished")
                else False
            )

    async def update_chats(self) -> None:
        to_delete = []
        for chat_id, message in self.chats.items():
            active: list[Torrent] = []
            finished: list[tuple[str, Torrent]] = []
            for torrent_id in message.torrent_ids:
                torrent = self.torrents[torrent_id]
                if torrent.stats:
                    active.append(torrent)
                else:
                    finished.append((torrent_id, torrent))
            if active:
                text = self.create_message(active)
                if not message.obj:
                    message.obj = await self.instance.bot.send(
                        chat_id, self.instance.bot.logify(self.name, text)
                    )
                    await self.instance.bot.pin(message.obj)
                elif message.prev != text:
                    await self.instance.bot.edit(
                        message.obj,
                        self.instance.bot.logify(self.name, text),
                        replace=True,
                    )
                message.prev = text
            if finished:
                for torrent_id, torrent in finished:
                    await self.instance.bot.send(
                        chat_id,
                        self.instance.bot.logify(self.name, f"✅ {torrent.name}"),
                    )
                    message.torrent_ids.remove(torrent_id)
                    await self.client.forget_torrent(torrent_id)
                    del self.torrents[torrent_id]
            if not active and finished:
                if message.obj:
                    await self.instance.bot.unpin(message.obj)
                    await self.instance.bot.delete(message.obj)
                to_delete.append(chat_id)
        if to_delete:
            for chat_id in to_delete:
                del self.chats[chat_id]

    def create_message(self, torrents: list[Torrent]) -> str:
        current, total, total_count, hidden_count, files = 0, 0, 0, 0, []
        for torrent in sorted(
            torrents,
            key=lambda x: (
                (x.stats if isinstance(x.stats, dict) else {}).get("state") == "live"
            ),
        ):
            if total_count < 3:
                stats = torrent.stats if isinstance(torrent.stats, dict) else {}
                status = "🟢" if stats.get("state") == "live" else "🟧"
                current_bytes, total_bytes = (
                    stats.get("progress_bytes", 0),
                    stats.get("total_bytes", 0),
                )
                live_stats = stats.get("live") or {}
                peers = live_stats.get("snapshot", {}).get("peer_stats", {})
                live = peers.get("live", 0)
                seen = peers.get("seen", 0)
                download_speed = live_stats.get("download_speed", {}).get(
                    "human_readable", "♾"
                )
                time_remaining = (live_stats.get("time_remaining") or {}).get(
                    "human_readable", "♾"
                )
                details = (
                    f"👤 {live}/{seen} 📊 {download_speed} ⏰ {time_remaining}\n"
                    if live
                    else ""
                )
                files.append(
                    f"{torrent.name}\n{details}{status} {progress_bar(current_bytes, total_bytes)}"
                )
                current += current_bytes
                total += total_bytes
            else:
                hidden_count += 1
            total_count += 1
        header = (
            f"🌊 [{len(torrents)}] {progress_bar(current, total, size=11)}\n{SEPARATOR}"
        )
        content = f"\n{SEPARATOR}\n".join(files)
        hidden = (
            f"\n{SEPARATOR}\n+{hidden_count} more in queue..." if hidden_count else ""
        )
        return f"{header}\n{content}{hidden}"
