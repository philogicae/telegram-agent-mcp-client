from asyncio import sleep
from os import getenv

from dotenv import load_dotenv
from telebot.types import Message

from .abstract import AgenticBot, handler
from .utils import fixed_markdown, unpack_user

load_dotenv()
TELEGRAM_CHAT_DEV = getenv("TELEGRAM_CHAT_DEV")


@handler
async def telegram_report_issue(
    instance: AgenticBot, orig_msg: Message, reply_msg: Message, e: Exception | str
) -> None:
    cause, error = "Telegram", ""
    if isinstance(e, str):
        cause = "Agent"
        error = f"\n- {e}"
    instance.log.info(f"-> {cause} Exception: {e}")
    user, name = unpack_user(orig_msg)
    if TELEGRAM_CHAT_DEV:
        await instance.bot.send(
            TELEGRAM_CHAT_DEV,
            f"⚠️ {cause} issue detected on chat:\n- *{orig_msg.chat.id}* | {orig_msg.chat.title or 'Private'}\n- @{user}: {name}{error}",
        )
    await instance.bot.reply(
        reply_msg,
        f"⚠️ Something went wrong with {cause}...\n🚒 Reported automatically to admin",
    )


@handler
async def telegram_chat(instance: AgenticBot, msg: Message) -> None:
    timer = instance.log.received(msg)
    if msg.text in ["/start", "/help"]:
        await instance.bot.send(msg, "🌟 Welcome! How can I help you?")
        return

    init = instance.bot.reply if msg.chat.type != "private" else instance.bot.send
    reply, prev = await init(msg), ""
    try:
        async for step, done, extra in instance.agent.chat(msg):
            text = fixed_markdown(step)
            if text != prev:
                await instance.bot.edit(reply, text, final=done)
                prev = text
                if step == "✅":
                    tool = extra.get("tool")
                    if tool and tool in instance.managers:
                        await instance.managers[tool].notify(
                            msg.chat.id, extra.get("output")
                        )
                elif step == "❌":
                    await telegram_report_issue(
                        instance, msg, reply, f"Tool error = {extra.get('tool')}"
                    )
            if not done:
                await sleep(0.5)  # No need to spam
    except Exception as e:
        await telegram_report_issue(instance, msg, reply, e)
    instance.log.sent(msg, timer)
