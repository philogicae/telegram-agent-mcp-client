from asyncio import sleep
from os import getenv

from dotenv import load_dotenv
from telebot.types import Message

from .abstract import AgenticBot, handler
from .utils import fixed_markdown, unpack_user

load_dotenv()
TELEGRAM_CHAT_DEV = getenv("TELEGRAM_CHAT_DEV")


async def telegram_report_issue(
    agentic: AgenticBot, msg: Message, e: Exception
) -> None:
    agentic.log.info(f"-> TELEGRAM EXCEPTION: {e}")
    user, name = unpack_user(msg)
    if TELEGRAM_CHAT_DEV:
        await agentic.bot.send(
            TELEGRAM_CHAT_DEV,
            f"⚠️ Issue detected on chat:\n- *{msg.chat.id}* | {msg.chat.title or 'Private'}\n- @{user}: {name}",
        )
    await agentic.bot.reply(
        msg,
        "⚠️ Something went wrong...\n🚒 Reported automatically to admin",
    )


@handler
async def telegram_chat(
    agentic: AgenticBot, message: Message, dev: bool = False
) -> None:
    timer = agentic.log.received(message)
    if message.text in ["/start", "/help"]:
        await agentic.bot.send(message, "🌟 Welcome! How can I help you?")
        return

    init = agentic.bot.reply if message.chat.type != "private" else agentic.bot.send
    reply = await init(message)
    try:
        async for step, done in agentic.agent.chat(message, dev):
            await agentic.bot.edit(reply, fixed_markdown(step), final=done)
            if not done:
                await sleep(0.5)  # No need to spam
    except Exception as e:
        await telegram_report_issue(agentic, message, e)
    agentic.log.sent(message, timer)
