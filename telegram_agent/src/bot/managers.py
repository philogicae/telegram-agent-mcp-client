from asyncio import sleep

from .abstract import AgenticBot
from .utils import progress_bar


class DownloadManager:
    instance: AgenticBot
    torrents: dict[int, dict[str, str]]

    def __init__(self, instance: AgenticBot):
        self.instance = instance
        self.torrents = {}

    async def start(self) -> None:
        msg = await self.instance.bot.send(515014246, progress_bar(0, 20, size=10))
        await self.instance.bot.pin(msg)
        for i in range(1, 21):
            await sleep(1)
            await self.instance.bot.edit(
                msg, progress_bar(i, 20, size=10), replace=True
            )
        await self.instance.bot.send(515014246, "Done.")
        await self.instance.bot.delete(msg)
        await sleep(1000)
