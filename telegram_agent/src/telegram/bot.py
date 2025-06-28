from asyncio import sleep
from os import getenv
from typing import Any

from dotenv import load_dotenv

from ..core import Agent
from .base_bot import Bot
from .logger import Logger

load_dotenv()


async def telegram_bot(**kwargs) -> None:
    log = Logger()
    log.info("Starting bot...")
    bot = Bot(**kwargs)
    agent = await Agent().initialize()

    async def chat(message: Any) -> None:
        timer = log.received(message)
        if message.text == "/start":
            await bot.send(message, "🌟 Welcome! How can I help you?")
            return

        reply = await bot.reply(message)
        # async for step, done in agent.chat(message):  # TODO: Fix tool bug
        done = False
        while not done:
            step, done = await anext(agent.chat(message))
            if done:
                await bot.final(reply, step)
            else:
                await bot.edit(reply, step)
                await sleep(0.5)
        log.sent(message, timer)

    await bot.initialize(chat)
    log.info("Bot is ready!")

    try:
        await bot.start()
    except KeyboardInterrupt:
        log.info("Killed by KeyboardInterrupt")
    except Exception as e:
        log.error(e)


async def run_bot(dev: bool = False) -> None:
    telegram_id = getenv("TELEGRAM_BOT_ID")
    telegram_id_dev = getenv("TELEGRAM_BOT_ID_DEV")
    if dev:
        if telegram_id_dev:
            telegram_id = telegram_id_dev
        else:
            raise ValueError("TELEGRAM_BOT_ID_DEV is not set")
    else:
        if not telegram_id:
            raise ValueError("TELEGRAM_BOT_ID is not set")

    await telegram_bot(
        telegram_id=telegram_id,
        delay=0.2,
        group_msg_trigger="!",
        waiting="I'm thinking...",
    )
