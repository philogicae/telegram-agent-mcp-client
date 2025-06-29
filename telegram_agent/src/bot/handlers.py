from asyncio import sleep

from telebot.types import Message

from .abstract import AgenticBot, handler


@handler
async def telegram_chat(agentic_bot: AgenticBot, message: Message) -> None:
    timer = agentic_bot.log.received(message)
    if message.text in ["/start", "/help"]:
        await agentic_bot.bot.send(message, "🌟 Welcome! How can I help you?")
        return

    reply = await agentic_bot.bot.reply(message)
    async for step, done in agentic_bot.agent.chat(message):
        if step:
            if done:
                await agentic_bot.bot.final(reply, step)
            else:
                await agentic_bot.bot.edit(reply, step)
                await sleep(0.5)
    agentic_bot.log.sent(message, timer)
