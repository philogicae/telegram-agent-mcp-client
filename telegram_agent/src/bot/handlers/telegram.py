"""Telegram bot handlers."""

import traceback
from asyncio import sleep
from os import getenv

from dotenv import load_dotenv
from telebot.types import Message

from ..abstract import AgenticBot, handler
from ..utils import str_size, unpack_user

load_dotenv()
TELEGRAM_CHAT_DEV = getenv("TELEGRAM_CHAT_DEV")


@handler
async def telegram_report_issue(
    instance: AgenticBot, orig_msg: Message, reply_msg: Message, e: Exception | str
) -> None:
    """Report an issue to the admin and notify the user."""
    cause = "Agent" if isinstance(e, str) else "Telegram"
    error = f"\n{e}"
    instance.log.error(f"{cause} -> Exception: {e}")
    if TELEGRAM_CHAT_DEV:  # Report to admin
        user, name = unpack_user(orig_msg)
        await instance.bot.send(
            TELEGRAM_CHAT_DEV,
            instance.bot.logify(
                "Error",
                f"⚠️ {cause} issue detected on chat:\n[{orig_msg.chat.id}] {orig_msg.chat.title or 'Private'}\n[@{user}] {name}{error}",
            ),
        )
    if str(orig_msg.chat.id) != TELEGRAM_CHAT_DEV:  # Notify user
        await instance.bot.reply(
            reply_msg,
            instance.bot.logify(
                "Error",
                f"⚠️ Something went wrong with {cause}...\n🚒 Reported automatically to admin, meanwhile you can still try again.",
            ),
        )


@handler
async def telegram_chat(instance: AgenticBot, msg: Message) -> None:
    """Handle chat messages and orchestrate agent responses."""
    timer = instance.log.received(msg)
    if msg.text in ["/start", "/help"]:
        await instance.bot.send(msg, "🌟 Welcome! How can I help you?")
        return

    init = instance.bot.reply if msg.chat.type != "private" else instance.bot.send
    reply, prev = await init(msg), ""
    try:
        async for agent, step, done, extra in instance.agent.chat(msg):
            if step != prev:
                prev = step
                await instance.bot.edit(reply, step, final=done, agent=agent)
                if step[0] == "✅":
                    tool = extra.get("tool")
                    if tool and tool in instance.managers:
                        await instance.managers[tool].notify(
                            msg.chat.id, extra.get("output")
                        )
                elif step[0] == "❌":
                    await telegram_report_issue(
                        instance,
                        msg,
                        reply,
                        f"{agent} -> Tool error = {extra.get('tool')}",
                    )
            if not done:
                await sleep(0.5)  # No need to spam
    except Exception as e:
        traceback.print_exc()
        await telegram_report_issue(instance, msg, reply, e)
    instance.log.sent(msg, timer)


@handler
async def telegram_file(instance: AgenticBot, msg: Message) -> None:
    """Handle file/document uploads from users."""
    try:
        if msg.document:
            file_name = msg.document.file_name
            file_info = await instance.bot.core.get_file(msg.document.file_id)
            file_path = file_info.file_path
            file_size = str_size(file_info.file_size)
            msg.text = f"DOCUMENT ({file_size}): {file_name} = {file_path}"
            timer = instance.log.received(msg)
            await instance.managers["document"].notify(
                msg.chat.id,
                {"filename": file_name, "size": file_size, "path": file_path},
            )
            instance.log.sent(msg, timer)
    except Exception as e:
        if str(e).endswith("too big"):
            await instance.managers["document"].file_too_large(
                msg.chat.id, str(file_name)
            )
            instance.log.warning("File: too big. Redirected to Docs UI.")
        else:
            await telegram_report_issue(instance, msg, msg, e)
            instance.log.exception("File handling error")
