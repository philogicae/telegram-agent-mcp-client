from asyncio import sleep
from os import getenv

from dotenv import load_dotenv
from telebot.types import Message

from .abstract import AgenticBot, handler
from .utils import fixed_markdown, unpack_user

load_dotenv()
TELEGRAM_CHAT_DEV = getenv("TELEGRAM_CHAT_DEV")


async def telegram_report_issue(
    agentic: AgenticBot, orig_msg: Message, reply_msg: Message, e: Exception | str
) -> None:
    cause = "Telegram" if isinstance(e, Exception) else "Agent"
    agentic.log.info(f"-> {cause} Exception: {e}")
    user, name = unpack_user(orig_msg)
    if TELEGRAM_CHAT_DEV:
        await agentic.bot.send(
            TELEGRAM_CHAT_DEV,
            f"⚠️ {cause} issue detected on chat:\n- *{orig_msg.chat.id}* | {orig_msg.chat.title or 'Private'}\n- @{user}: {name}",
        )
    await agentic.bot.reply(
        reply_msg,
        f"⚠️ Something went wrong with {cause}...\n🚒 Reported automatically to admin",
    )


@handler
async def telegram_chat(agentic: AgenticBot, msg: Message, dev: bool = False) -> None:
    timer = agentic.log.received(msg)
    if msg.text in ["/start", "/help"]:
        await agentic.bot.send(msg, "🌟 Welcome! How can I help you?")
        return

    init = agentic.bot.reply if msg.chat.type != "private" else agentic.bot.send
    reply = await init(msg)
    try:
        async for step, done in agentic.agent.chat(msg, dev):
            await agentic.bot.edit(reply, fixed_markdown(step), final=done)
            if step == "❌":
                await sleep(0.5)
                await telegram_report_issue(agentic, msg, reply, "Tool error")
            if not done:
                await sleep(0.5)  # No need to spam
    except Exception as e:
        await sleep(0.5)
        await telegram_report_issue(agentic, msg, reply, e)
    agentic.log.sent(msg, timer)
