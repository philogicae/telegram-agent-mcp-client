from asyncio import sleep
from datetime import datetime, timedelta
from os import getenv
from typing import Any

from dotenv import load_dotenv
from httpx import AsyncClient
from pydantic import BaseModel

from ..abstract import AgenticBot, Manager
from ..utils import progress_bar, sanitize_filename

load_dotenv()
RAG_URL = getenv("RAG_URL")
DOCS_UI_URL = getenv("DOCS_UI_URL", "").strip("/")
SEPARATOR = "___________________________________"


class Document(BaseModel):
    status: str
    percent: str
    created_at: str
    uploaded_at: datetime
    done: bool = False
    error: bool = False
    source: str = ""


class Message(BaseModel):
    obj: Any
    prev: str
    filenames: set[str]


class DocumentManager(Manager):
    instance: AgenticBot
    documents: dict[str, Document]
    chats: dict[int, Message]
    delay: float = 4

    def __init__(self, instance: AgenticBot, delay: float | None = None):
        self.name = "Document Manager"
        self.instance = instance
        self.documents = {}
        self.chats = {}
        if delay:
            self.delay = delay

    async def start(self) -> None:
        while True:
            if self.documents:
                await self.update_document_status()
                await self.update_chats()
            await sleep(self.delay)

    async def notify(self, chat_id: int, data: dict[str, str]) -> None:
        source = data["filename"]
        res = await self.upload_document(source, data["path"])
        source = sanitize_filename(source)
        documents: list[str] = res.get("files")
        if not documents:
            await self.no_file(chat_id, source, data["size"])
        else:
            now = datetime.now()
            for filename in documents:
                self.documents[filename] = Document(
                    status="in queue",
                    percent="0%",
                    created_at=now.strftime("%Y-%m-%d %H:%M:%S"),
                    uploaded_at=now,
                    source=source if source != filename else "",
                )
            if chat_id not in self.chats:
                self.chats[chat_id] = Message(obj=None, prev="", filenames=set())
            else:  # Recreate message
                old_message_obj = self.chats[chat_id].obj
                if old_message_obj:
                    await self.instance.bot.unpin(old_message_obj)
                    await self.instance.bot.delete(old_message_obj)
                self.chats[chat_id].obj = None
            for filename in documents:
                self.chats[chat_id].filenames.add(filename)

    async def no_file(self, chat_id: int, filename: str, size: str) -> None:
        await self.instance.bot.send(
            chat_id,
            self.instance.bot.logify(
                self.name, f"❌ No valid files found in {filename} ({size})"
            ),
        )

    async def file_too_large(self, chat_id: int, filename: str) -> None:
        await self.instance.bot.send(
            chat_id,
            self.instance.bot.logify(
                self.name,
                f"❌ File too large (>20MB): {filename}",
            )
            + f"\nTelegram API only allows files up to 20MB.\nTo upload multiple or larger files: [{DOCS_UI_URL.split('/')[-1]}/upload/dev]({DOCS_UI_URL}/upload/dev)",
        )

    async def upload_document(self, file_name: str, file_path: str) -> Any:
        try:
            file = await self.instance.bot.core.download_file(file_path)
            try:
                async with AsyncClient() as http:
                    res = await http.post(
                        f"{RAG_URL}/upload",
                        files={"file": (file_name, file)},
                    )
                    return res.json()
            except Exception as e:
                self.instance.log.exception(f"Uploading document: {e}")
        except Exception as e:
            self.instance.log.exception(f"Downloading file: {e}")
        return {"files": []}

    async def all_document_status(self) -> Any:
        try:
            async with AsyncClient() as http:
                res = await http.get(f"{RAG_URL}/status")
                return res.json()
        except Exception as e:
            self.instance.log.error(f"Getting document statuses: {e}")
        return None

    async def update_document_status(self) -> None:
        if not self.documents:
            return
        documents = await self.all_document_status()
        now = datetime.now()
        if documents:
            queue = documents.get("queue", {})
            failed = documents.get("failed", {})
            if queue:
                for filename, details in queue.items():
                    if filename in self.documents:
                        self.documents[filename].status = details.get(
                            "status", "unknown"
                        )
                        self.documents[filename].percent = details.get("percent", "0%")
                        self.documents[filename].uploaded_at = now
            if failed:
                for filename, details in failed.items():
                    if filename in self.documents:
                        self.documents[filename].status = details.get(
                            "status", "unknown"
                        )
                        self.documents[filename].percent = details.get("percent", "0%")
                        self.documents[filename].uploaded_at = now
                        self.documents[filename].done = True
                        self.documents[filename].error = True
        all_found = queue.keys() | failed.keys()
        for filename, document in self.documents.items():
            if filename not in all_found and (
                document.uploaded_at + timedelta(seconds=30) < now
                or int(document.percent.strip("%")) > 0
            ):
                self.documents[filename].done = True

    async def update_chats(self) -> None:
        to_delete = []
        for chat_id, message in self.chats.items():
            active: list[tuple[str, Document]] = []
            finished: list[tuple[str, Document]] = []
            for filename in message.filenames:
                document = self.documents[filename]
                (active if not document.done else finished).append((filename, document))
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
                for filename, document in finished:
                    success = "❌" if document.error else "✅"
                    await self.instance.bot.send(
                        chat_id,
                        self.instance.bot.logify(self.name, f"{success} {filename}"),
                    )
                    message.filenames.remove(filename)
                    del self.documents[filename]
            if not active and finished:
                if message.obj:
                    await self.instance.bot.unpin(message.obj)
                    await self.instance.bot.delete(message.obj)
                to_delete.append(chat_id)
        if to_delete:
            for chat_id in to_delete:
                del self.chats[chat_id]

    def create_message(self, documents: list[tuple[str, Document]]) -> str:
        current, total_count, hidden_count, files = 0, 0, 0, []
        for filename, document in sorted(
            documents,
            key=lambda x: (x[1].status == "in queue", -int(x[1].percent.strip("%"))),
        ):
            if total_count < 3:
                source = f"[{document.source}] " if document.source else ""
                status = document.status[0].upper() + document.status[1:]
                status_icon = "🟢" if status != "In queue" else "⏳"
                current_percent = int(document.percent.strip("%"))
                files.append(
                    f"{source}{filename}\nStatus: {status}\n{status_icon} {progress_bar(current_percent, 100)}"
                )
                current += current_percent
            else:
                hidden_count += 1
            total_count += 1
        header = f"📄 [{len(documents)}] {progress_bar(current, total_count * 100, size=11)}\n{SEPARATOR}"
        content = f"\n{SEPARATOR}\n".join(files)
        hidden = (
            f"\n{SEPARATOR}\n+{hidden_count} more in queue..." if hidden_count else ""
        )
        return f"{header}\n{content}{hidden}"
