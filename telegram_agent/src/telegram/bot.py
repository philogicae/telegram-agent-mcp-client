from logging import INFO, basicConfig, getLogger
from os import getenv
from time import sleep
from time import time as now
from typing import Any, Callable

from dotenv import load_dotenv
from rich.logging import RichHandler
from telebot import types
from telebot.async_telebot import AsyncTeleBot

from ..core import Agent

# Logs
basicConfig(
    format="%(message)s", datefmt="[%d-%m %X]", level=INFO, handlers=[RichHandler()]
)
logger = getLogger("rich")

# .env
load_dotenv()
TOKEN = getenv("TELEGRAM_BOT_ID")
DELAY = 0.2
VERSION = 1


# Utils
def sent(chat_id: int, user: str, name: str, log: str) -> None:
    logger.info(f"<-[{chat_id}](@{user}) {name}: {log}")


def received(chat_id: int, user: str, name: str, log: str) -> None:
    logger.info(f"->[{chat_id}](@{user}) {name}: {log}")


def happened(chat_id: int, user: str, name: str, log: str) -> None:
    logger.info(f"-x[{chat_id}](@{user}) {name}: {log}")


def new_version(msg: str) -> str:
    return f"🔥 NEW VERSION: v{VERSION} 🔥\n\nChanges:{msg}"


# Display
UPDATING = "Update in progress...\n🛠️ Repairing broken AIs 🛠️\nPlease come back later..."
WAITING = "Geppetto is thinking..."
HELP = "🌟 How to communicate with Geppetto 🌟\n\n✍️ Simple use:\n*. your-message*\nOR\n*Reply to any Geppetto's message*"
POST_UPDATE = "Update pushed...\n🔥 Bot relaunched 🔥\nSorry for the inconvenience."


class SafeRequest:
    def __init__(self, telebot: AsyncTeleBot):
        self.bot = telebot
        self.delay: float = DELAY
        self.last: float = 0

    def done(self) -> None:
        self.last = now()

    def is_free(self) -> bool:
        return self.last + self.delay < now()

    async def exec(self, method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        while True:
            if self.is_free():
                try:
                    result = await method(*args, **kwargs)
                    self.done()
                    return result
                except Exception:
                    pass
            else:
                sleep(DELAY)

    async def reply(
        self, message: types.Message, text: str, parse_mode: str | None = None
    ) -> Any:
        return await self.exec(self.bot.reply_to, message, text, parse_mode=parse_mode)

    async def edit(
        self, text: str, chat_id: int, message_id: int, parse_mode: str | None = None
    ) -> Any:
        return await self.exec(
            self.bot.edit_message_text, text, chat_id, message_id, parse_mode=parse_mode
        )

    async def delete(self, chat_id: int, message_id: int) -> Any:
        return await self.exec(self.bot.delete_message, chat_id, message_id)


# args: list[str] | None = None
async def run_bot() -> None:
    logger.info("Starting...")
    bot = AsyncTeleBot(
        token=str(TOKEN),
        # threaded=False,
        # disable_web_page_preview=True,
        # skip_pending=True,
    )
    geppetto = await bot.get_me()
    safe = SafeRequest(bot)
    agent = Agent()
    await agent.initialize()

    updated = False
    """ if args and args[0] == "update":
        updated = True
        logger.info("[UPDATE MODE]")
    elif args and args[0] == "new":
        logger.info("[UPDATE PUSHED]")
        for group in []:
            msg = new_version(args[1].replace("-", "\n-"))
            await bot.send_message(group, msg)
            sent(group, "admin", "admin", msg)
    elif args and args[0] == "post_update":
        for group in []:
            await bot.send_message(group, POST_UPDATE)
            sent(group, "admin", "admin", POST_UPDATE) """

    await bot.set_my_commands(
        commands=[
            types.BotCommand("help", "🤖 How to communicate with Geppetto")  # type: ignore
        ]
    )
    logger.info("Bot started")

    async def chatting(message: types.Message, text: str | None = None) -> None:
        chat_id = message.chat.id
        sender = message.from_user
        text = text or message.text
        if updated and sender.username != "philogicae":
            await safe.reply(message, UPDATING)
            sent(chat_id, sender.username, sender.first_name, "UPDATE")
        else:
            received(chat_id, sender.username, sender.first_name, text)
            start_call, msg_id = now(), (await safe.reply(message, WAITING)).id
            sleep(5)
            response = await agent.chat(chat_id, text)
            await safe.edit(response, chat_id, msg_id)
            sent(
                chat_id,
                sender.username,
                sender.first_name,
                f"{response} {now() - start_call:.2f}s",
            )

    @bot.message_handler(commands=["help"])  # type: ignore
    async def handle_help(message: types.Message) -> None:
        await safe.reply(message, HELP, parse_mode="Markdown")
        sent(
            message.chat.id,
            message.from_user.username,
            message.from_user.first_name,
            "HELP",
        )

    @bot.message_handler(func=lambda m: m.text.startswith(". "), content_types=["text"])  # type: ignore
    async def handle_msg(message: types.Message) -> None:
        await chatting(message, message.text[2:])

    @bot.message_handler(
        func=lambda m: m.reply_to_message
        and m.reply_to_message.from_user.id == geppetto.id,
        content_types=["text"],
    )  # type: ignore
    async def handle_reply(message: types.Message) -> None:
        await chatting(message)

    try:
        await bot.infinity_polling(skip_pending=True, timeout=300)
    except KeyboardInterrupt:
        logger.info("Killed by KeyboardInterrupt")
    except Exception as e:
        logger.error(f"Error: {e}")
