from asyncio import gather, sleep
from json import loads
from os import getenv
from typing import Any

from dotenv import load_dotenv
from httpx import AsyncClient
from pydantic import BaseModel
from rqbit_client import RqbitClient

from .abstract import AgenticBot, Manager
from .utils import progress_bar

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
            async with AsyncClient() as client:
                await client.post(MEDIA_LIB_REFRESH)

    async def update_torrent_stats(self) -> None:
        if not self.torrents:
            return
        results = await gather(
            *[self.client.get_torrent_stats(torrent_id) for torrent_id in self.torrents]
        )
        for torrent_id, stats in zip(self.torrents.keys(), results):
            self.torrents[torrent_id].stats = (
                stats if isinstance(stats, dict) and not stats["finished"] else False
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
                    message.obj = await self.instance.bot.send(chat_id, text)
                    await self.instance.bot.pin(message.obj)
                elif message.prev != text:
                    await self.instance.bot.edit(message.obj, text, replace=True)
                message.prev = text
            if finished:
                for torrent_id, torrent in finished:
                    await self.instance.bot.send(chat_id, f"✅  {torrent.name}")
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
        current, total, files = 0, 0, []
        for torrent in torrents:
            status = "🟢" if torrent.stats.get("state") == "live" else "🟧"  # type: ignore
            current_bytes, total_bytes = (
                torrent.stats["progress_bytes"],  # type: ignore
                torrent.stats["total_bytes"],  # type: ignore
            )
            stats: dict[str, Any] = torrent.stats.get("live") or {}  # type: ignore
            peers = stats.get("snapshot", {}).get("peer_stats", {})
            live = peers.get("live", 0)
            seen = peers.get("seen", 0)
            download_speed = stats.get("download_speed", {}).get("human_readable", "♾")
            time_remaining = (stats.get("time_remaining") or {}).get(
                "human_readable", "♾"
            )
            details = (
                f"👤 {live}/{seen} 📊 {download_speed.ljust(12)} ⏰ {time_remaining}\n"
                if live
                else ""
            )
            files.append(
                f"{torrent.name}\n{details}{status} {progress_bar(current_bytes, total_bytes)}"
            )
            current += current_bytes
            total += total_bytes
        header = f"⬇️ [{len(torrents)}] {progress_bar(current, total, size=11)} ⬇️\n{SEPARATOR}"
        content = f"\n{SEPARATOR}\n".join(files)
        return f"{header}\n{content}"
