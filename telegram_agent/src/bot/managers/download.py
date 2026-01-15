from asyncio import gather, sleep
from json import loads
from os import getenv
from typing import Any

from dotenv import load_dotenv
from httpx import AsyncClient
from pydantic import BaseModel
from transmission_client import TransmissionClient

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
    client: TransmissionClient
    torrents: dict[str, Torrent]
    chats: dict[int, Message]
    delay: float = 4

    def __init__(self, instance: AgenticBot, delay: float | None = None):
        self.name = "Torrent Manager"
        self.instance = instance
        self.client = TransmissionClient()
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
        torrent_hash = torrent.get("hashString") or torrent.get("infoHash")
        if not torrent_hash:
            self.instance.log.error("No hash found in torrent data")
            return
        self.torrents[torrent_hash] = Torrent(
            name=torrent.get("name", "Unknown"), stats=True
        )
        if chat_id not in self.chats:
            self.chats[chat_id] = Message(obj=None, prev="", torrent_ids=set())
        else:
            old_message_obj = self.chats[chat_id].obj
            if old_message_obj:
                await self.instance.bot.unpin(old_message_obj)
                await self.instance.bot.delete(old_message_obj)
            self.chats[chat_id].obj = None
        self.chats[chat_id].torrent_ids.add(torrent_hash)
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
            *[self.client.get_torrent(torrent_id) for torrent_id in self.torrents],
            return_exceptions=True,
        )
        for torrent_id, stats in zip(self.torrents.keys(), results):
            if isinstance(stats, Exception):
                self.instance.log.error(f"Error fetching torrent {torrent_id}: {stats}")
                self.torrents[torrent_id].stats = False
            elif isinstance(stats, str):
                self.instance.log.error(f"API error for torrent {torrent_id}: {stats}")
                self.torrents[torrent_id].stats = False
            elif isinstance(stats, dict):
                if stats.get("isFinished") or stats.get("percentDone", 0) >= 1.0:
                    self.torrents[torrent_id].stats = False
                else:
                    self.torrents[torrent_id].stats = stats
            else:
                self.torrents[torrent_id].stats = False

    async def update_chats(self) -> None:
        to_delete = []
        for chat_id, message in self.chats.items():
            active: list[Torrent] = []
            finished: list[tuple[str, Torrent]] = []
            for torrent_id in message.torrent_ids:
                torrent = self.torrents.get(torrent_id)
                if not torrent:
                    continue
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
                    try:
                        await self.instance.bot.edit(
                            message.obj,
                            self.instance.bot.logify(self.name, text),
                            replace=True,
                        )
                    except Exception:
                        self.instance.log.error("IGNORED: Editing message error")
                        message.obj = await self.instance.bot.send(
                            chat_id, self.instance.bot.logify(self.name, text)
                        )
                        await self.instance.bot.pin(message.obj)
                message.prev = text
            if finished:
                for torrent_id, torrent in finished:
                    await self.instance.bot.send(
                        chat_id,
                        self.instance.bot.logify(self.name, f"✅ {torrent.name}"),
                    )
                    message.torrent_ids.remove(torrent_id)
                    await self.client.remove_torrent(torrent_id, delete_data=False)
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
                (x.stats if isinstance(x.stats, dict) else {}).get("rateDownload", 0)
                > 0
            ),
            reverse=True,
        ):
            if total_count < 3:
                stats = torrent.stats if isinstance(torrent.stats, dict) else {}
                is_downloading = stats.get("rateDownload", 0) > 0
                status = "🟢" if is_downloading else "🟧"
                current_bytes = int(stats.get("downloadedEver", 0))
                total_bytes = int(stats.get("totalSize", 0))
                left_bytes = int(stats.get("leftUntilDone", 0))
                peers_connected = stats.get("peersConnected", 0)
                peers_sending = stats.get("peersSendingToUs", 0)
                download_speed_bytes = stats.get("rateDownload", 0)
                download_speed = self._format_speed(download_speed_bytes)
                eta = stats.get("eta") or "♾"
                details = f"👤 {peers_sending}/{peers_connected} 📊 {download_speed} ⏰ {eta}\n"
                progress_bytes = (
                    total_bytes - left_bytes if total_bytes > 0 else current_bytes
                )
                files.append(
                    f"{torrent.name}\n{details}{status} {progress_bar(progress_bytes, total_bytes)}"
                )
                current += progress_bytes
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

    def _format_speed(self, bytes_per_sec: int | float) -> str:
        try:
            speed = float(bytes_per_sec)
            if speed < 1024:
                return f"{speed:.0f}B/s"
            elif speed < 1024 * 1024:
                return f"{speed / 1024:.1f}KB/s"
            elif speed < 1024 * 1024 * 1024:
                return f"{speed / (1024 * 1024):.1f}MB/s"
            else:
                return f"{speed / (1024 * 1024 * 1024):.1f}GB/s"
        except (ValueError, TypeError):
            return "0B/s"
