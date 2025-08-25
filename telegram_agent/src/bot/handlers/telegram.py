from asyncio import sleep
from os import getenv

from dotenv import load_dotenv
from telebot.types import Message

from ..abstract import AgenticBot, handler
from ..utils import logify, unpack_user

load_dotenv()
TELEGRAM_CHAT_DEV = getenv("TELEGRAM_CHAT_DEV")


@handler
async def telegram_report_issue(
    instance: AgenticBot, orig_msg: Message, reply_msg: Message, e: Exception | str
) -> None:
    cause = "Agent" if isinstance(e, str) else "Telegram"
    error = f"\n{e}"
    instance.log.error(f"-> {cause} Exception: {e}")
    user, name = unpack_user(orig_msg)
    if TELEGRAM_CHAT_DEV and TELEGRAM_CHAT_DEV == str(orig_msg.chat.id):
        await instance.bot.send(
            TELEGRAM_CHAT_DEV,
            logify(
                "Error",
                f"⚠️ {cause} issue detected on chat:\n- *{orig_msg.chat.id}* | {orig_msg.chat.title or 'Private'}\n- @{user}: {name}{error}",
            ),
        )
    else:
        await instance.bot.reply(
            reply_msg,
            logify(
                "Error",
                f"⚠️ Something went wrong with {cause}...\n🚒 Reported automatically to admin",
            ),
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
        async for agent, step, done, extra in instance.agent.chat(msg):
            if step != prev:
                await instance.bot.edit(reply, step, final=done, agent=agent)
                prev = step
                if step == "✅":
                    tool = extra.get("tool")
                    if tool and tool in instance.managers:
                        await instance.managers[tool].notify(
                            msg.chat.id, extra.get("output")
                        )
                elif step == "❌":
                    await telegram_report_issue(
                        instance,
                        msg,
                        reply,
                        f"{agent} -> Tool error = {extra.get('tool')}",
                    )
            if not done:
                await sleep(0.5)  # No need to spam
    except Exception as e:
        await telegram_report_issue(
            instance, msg, reply, f"{instance.agent.current_agent} -> {e}"
        )
    instance.log.sent(msg, timer)


@handler
async def telegram_file(instance: AgenticBot, msg: Message) -> None:
    timer = instance.log.received(msg)
    doc = msg.document
    if doc:
        file_name = doc.file_name
        file_info = await instance.bot.bot.get_file(doc.file_id)
        # downloaded_file = instance.bot.download_file(file_info.file_path)
        print(file_name, file_info)
    instance.log.sent(msg, timer)
