"""Download manager for Transmission torrent client."""

from asyncio import create_task, sleep
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

# Consecutive failed polls before a tracked torrent is considered lost.
_MAX_FAILURES = 3

# A vanished torrent this far along counts as finished: the manager removes
# torrents itself right after completion, so a disappearance at ~100% known
# progress means the data landed and is playable.
_ALMOST_DONE = 0.95

# Emby refresh milestones: files appear on disk, half-way (streamable quality
# of life), and completion is handled separately in update_chats.
_REFRESH_HALF = 0.5

# Display truncation for torrent names inside the monospace panel.
_MAX_NAME = 44


class Torrent(BaseModel):
    """Torrent data model.

    Lifecycle: stats=None until first poll succeeds; done/gone are terminal
    states. A torrent is "gone" when Transmission no longer knows it (canceled
    by the user/agent, or lost after repeated poll failures); if its last known
    progress was >= _ALMOST_DONE it is reported as success instead (data
    effectively landed), otherwise as canceled.
    """

    name: str
    stats: dict[str, Any] | None = None
    failures: int = 0
    done: bool = False
    gone: bool = False
    refreshed_start: bool = False
    refreshed_half: bool = False

    @property
    def nearly_done(self) -> bool:
        """True when last known progress is close enough to count as done."""
        return bool((self.stats or {}).get("percentDone", 0) >= _ALMOST_DONE)


class Message(BaseModel):
    """Chat message tracking model for downloads."""

    obj: Any
    prev: str | None
    torrent_ids: set[str]


class DownloadManager(Manager):
    """Manager for torrent downloads via Transmission."""

    instance: AgenticBot
    client: TransmissionClient
    torrents: dict[str, Torrent]
    chats: dict[int, Message]
    delay: float = 4

    def __init__(self, instance: AgenticBot, delay: float | None = None):
        self.name = "Torrent Manager"
        self.instance = instance
        # Bounded timeout: RPC calls run on the event loop, don't let a hung
        # Transmission stall the whole bot.
        self.client = TransmissionClient(timeout=10.0)
        self.torrents = {}
        self.chats = {}
        self._refresh_task: Any = None
        if delay:
            self.delay = delay

    async def start(self) -> None:
        """Start the torrent status monitoring loop."""
        while True:
            try:
                await self.update_torrent_stats()
                await self.update_chats()
            except Exception:
                self.instance.log.exception("Torrent monitoring error")
            await sleep(self.delay)

    async def notify(self, chat_id: int, data: str) -> None:
        """Handle a new torrent notification."""
        torrent = loads(data)
        torrent_hash = torrent.get("hashString") or torrent.get("infoHash")
        if not torrent_hash:
            self.instance.log.error("No hash found in torrent data")
            return
        existing = self.torrents.get(torrent_hash)
        if existing is None or existing.done or existing.gone:
            # Fresh tracking: also revives a hash previously marked done/gone.
            self.torrents[torrent_hash] = Torrent(name=torrent.get("name", "Unknown"))
        if chat_id not in self.chats:
            self.chats[chat_id] = Message(obj=None, prev="", torrent_ids=set())
        else:
            old_message_obj = self.chats[chat_id].obj
            if old_message_obj:
                await self.instance.bot.unpin(old_message_obj)
                await self.instance.bot.delete(old_message_obj)
            self.chats[chat_id].obj = None
        self.chats[chat_id].torrent_ids.add(torrent_hash)

    async def refresh_media_lib(self, _count: int = 0) -> None:
        """Refresh media library after download."""
        if MEDIA_LIB_REFRESH:
            try:
                async with AsyncClient() as http:
                    await http.post(MEDIA_LIB_REFRESH)
                self.instance.log.info("Media lib refreshed")
            except Exception:
                self.instance.log.exception("Refreshing media lib failed")

        # Run 3 times with 1 minute intervals
        if _count < 2:
            await sleep(60)
            await self.refresh_media_lib(_count + 1)

    async def update_torrent_stats(self) -> None:
        """Update state for all tracked torrents."""
        for torrent_id in list(self.torrents):
            torrent = self.torrents[torrent_id]
            if torrent.done or torrent.gone:
                continue
            try:
                result = await self.client.get_torrent(torrent_id)
            except Exception as e:
                result = e
            # The client wrapper converts RPC errors to strings instead of
            # raising; classify them rather than conflating with completion.
            if isinstance(result, Exception):
                self._mark_failure(torrent_id, f"{result}")
            elif isinstance(result, str):
                if "not found" in result.lower():
                    # Expected when canceled via agent or removed externally.
                    torrent.gone = True
                    self.instance.log.info(
                        f"Torrent {torrent_id} no longer in Transmission"
                        " (canceled or removed)"
                    )
                else:
                    self._mark_failure(torrent_id, result)
            elif isinstance(result, dict):
                torrent.failures = 0
                if result.get("isFinished") or result.get("percentDone", 0) >= 1.0:
                    torrent.done = True
                else:
                    pct = float(result.get("percentDone", 0) or 0)
                    fired = False
                    # Milestones fire once each; a fast jump can cross both in
                    # one poll, spawning a single refresh.
                    if pct > 0 and not torrent.refreshed_start:
                        torrent.refreshed_start = True
                        fired = True
                    if pct > _REFRESH_HALF and not torrent.refreshed_half:
                        torrent.refreshed_half = True
                        fired = True
                    if fired:
                        self._spawn_refresh(
                            "files created" if torrent.refreshed_start else "50%"
                        )
                torrent.stats = result

    def _spawn_refresh(self, reason: str) -> None:
        """Kick off an Emby refresh cycle unless one is already in flight.

        A cycle performs three whole-library scans over ~2 minutes, so a
        milestone landing inside a running cycle is already covered by its
        remaining scans — spawning another would stack duplicate scans.
        """
        if self._refresh_task is not None and not self._refresh_task.done():
            self.instance.log.info(f"Emby refresh skipped ({reason}); cycle in flight")
            return
        self.instance.log.info(f"Emby refresh scheduled ({reason})")
        self._refresh_task = create_task(self.refresh_media_lib())

    def _mark_failure(self, torrent_id: str, error: str) -> None:
        """Record a transient poll failure, giving up after too many."""
        torrent = self.torrents[torrent_id]
        torrent.failures += 1
        if torrent.failures >= _MAX_FAILURES:
            torrent.gone = True
            self.instance.log.error(
                f"Giving up on torrent {torrent_id} after"
                f" {torrent.failures} failed polls: {error}"
            )
        else:
            self.instance.log.warning(
                f"Poll failed for torrent {torrent_id}"
                f" ({torrent.failures}/{_MAX_FAILURES}): {error}"
            )

    async def update_chats(self) -> None:
        """Update chat messages with current torrent status."""
        chats_to_delete: list[int] = []
        any_completed = False
        for chat_id, message in self.chats.items():
            active: list[Torrent] = []
            completed: list[str] = []
            lost: list[tuple[str, Torrent]] = []
            text: str | None = None
            for torrent_id in list(message.torrent_ids):
                torrent = self.torrents.get(torrent_id)
                if not torrent:
                    continue
                if torrent.gone:
                    if torrent.nearly_done:
                        # Vanished while ~complete: data landed, count as done.
                        completed.append(torrent_id)
                    else:
                        lost.append((torrent_id, torrent))
                elif torrent.done:
                    completed.append(torrent_id)
                else:
                    active.append(torrent)
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
                        self.instance.log.exception("Editing message error")
                        message.obj = await self.instance.bot.send(
                            chat_id, self.instance.bot.logify(self.name, text)
                        )
                        await self.instance.bot.pin(message.obj)
            message.prev = text
            for torrent_id in completed:
                torrent = self.torrents.get(torrent_id)
                if not torrent:
                    continue
                name = torrent.name
                await self.instance.bot.send(
                    chat_id, self.instance.bot.logify(self.name, f"✅ {name}")
                )
                if not torrent.gone:
                    removal = await self.client.remove_torrent(
                        torrent_id, delete_data=False
                    )
                    if isinstance(removal, str) and "not found" not in removal.lower():
                        self.instance.log.error(
                            f"Failed to remove finished torrent {torrent_id}: {removal}"
                        )
                self._drop(message, torrent_id)
                any_completed = True
            for torrent_id, torrent in lost:
                await self.instance.bot.send(
                    chat_id,
                    self.instance.bot.logify(
                        self.name, f"⏹ {torrent.name} — canceled or removed"
                    ),
                )
                self._drop(message, torrent_id)
            if not active and not message.torrent_ids:
                if message.obj:
                    await self.instance.bot.unpin(message.obj)
                    await self.instance.bot.delete(message.obj)
                chats_to_delete.append(chat_id)
        if chats_to_delete:
            for chat_id in chats_to_delete:
                del self.chats[chat_id]
        # Refresh Emby only when something actually landed in the library.
        if any_completed:
            self._spawn_refresh("completion")

    def _drop(self, message: Message, torrent_id: str) -> None:
        """Forget a torrent for one chat, globally once unreferenced."""
        message.torrent_ids.discard(torrent_id)
        if any(torrent_id in m.torrent_ids for m in self.chats.values()):
            return
        self.torrents.pop(torrent_id, None)

    @staticmethod
    def _short_name(name: str) -> str:
        """Truncate long release names for the monospace panel."""
        if len(name) <= _MAX_NAME:
            return name
        return name[: _MAX_NAME - 1] + "…"

    def create_message(self, torrents: list[Torrent]) -> str:
        """Create a status message for active torrents."""
        current, total, hidden_count, files = 0, 0, 0, []
        for total_count, torrent in enumerate(
            sorted(
                torrents,
                key=lambda x: (x.stats or {}).get("rateDownload", 0) > 0,
                reverse=True,
            )
        ):
            if total_count < 3:
                stats = torrent.stats or {}
                is_downloading = stats.get("rateDownload", 0) > 0
                status = "🟢" if is_downloading else "🟧"
                current_bytes = int(stats.get("downloadedEver", 0))
                total_bytes = int(stats.get("totalSize", 0))
                left_bytes = int(stats.get("leftUntilDone", 0))
                peers_connected = stats.get("peersConnected", 0)
                peers_sending = stats.get("peersSendingToUs", 0)
                download_speed_bytes = stats.get("rateDownload", 0)
                # Pad the speed column so peer/eta fields line up across
                # entries in the monospace panel.
                download_speed = f"{self._format_speed(download_speed_bytes):>8}"
                eta = stats.get("eta") or "♾"
                details = f"👤 {peers_sending}/{peers_connected} 📊 {download_speed} ⏰ {eta}\n"
                progress_bytes = (
                    total_bytes - left_bytes if total_bytes > 0 else current_bytes
                )
                files.append(
                    f"{self._short_name(torrent.name)}\n{details}{status} {progress_bar(progress_bytes, total_bytes)}"
                )
                current += progress_bytes
                total += total_bytes
            else:
                hidden_count += 1
        header = (
            f"🌊 [{len(torrents)}] {progress_bar(current, total, size=11)}\n{SEPARATOR}"
        )
        content = f"\n{SEPARATOR}\n".join(files)
        hidden = (
            f"\n{SEPARATOR}\n+{hidden_count} more in queue..." if hidden_count else ""
        )
        return f"{header}\n{content}{hidden}"

    def _format_speed(self, bytes_per_sec: float) -> str:
        """Format download speed for display."""
        try:
            speed = float(bytes_per_sec)
            if speed < 1024:
                return f"{speed:.0f}B/s"
            if speed < 1024 * 1024:
                return f"{speed / 1024:.1f}KB/s"
            if speed < 1024 * 1024 * 1024:
                return f"{speed / (1024 * 1024):.1f}MB/s"
            return f"{speed / (1024 * 1024 * 1024):.1f}GB/s"
        except ValueError, TypeError:
            return "0B/s"
