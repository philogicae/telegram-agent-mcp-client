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

    def __init__(self, instance: AgenticBot):
        self.instance = instance
        self.client = RqbitClient()
        self.torrents = {}
        self.chats = {}

    async def start(self) -> None:
        while True:
            if self.torrents:
                await self.update_torrent_stats()
                await self.update_chats()
            await sleep(4)

    async def notify(self, chat_id: int, data: str) -> None:
        torrent = loads(data)
        self.torrents[torrent["details"]["info_hash"]] = Torrent(
            name=torrent["details"]["name"], stats=True
        )
        if chat_id not in self.chats:
            self.chats[chat_id] = Message(obj=None, prev="", torrent_ids=set())
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
            status = "🟢" if torrent.stats["state"] == "live" else "🟧"  # type: ignore
            current_bytes, total_bytes = (
                torrent.stats["progress_bytes"],  # type: ignore
                torrent.stats["total_bytes"],  # type: ignore
            )
            files.append(
                f"{status} {progress_bar(current_bytes, total_bytes)}\n{torrent.name}"
            )
            current += current_bytes
            total += total_bytes
        header = f"⬇️ *[{len(torrents)}]* {progress_bar(current, total, size=11)} ⬇️"
        content = "\n\n".join(files)
        return f"{header}\n\n{content}"
