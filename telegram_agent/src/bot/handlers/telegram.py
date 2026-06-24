"""Telegram bot handlers."""

from asyncio import gather, sleep, to_thread
from io import BytesIO
from os import getenv
from pathlib import Path
from traceback import print_exc

from dotenv import load_dotenv
from langchain.messages import HumanMessage
from telebot.types import InputFile, InputMediaPhoto, Message

from ...core.llm import LLM, LLM_CHOICE, LLM_UTILS
from ..abstract import AgenticBot, handler
from ..utils import str_size, unpack_user

load_dotenv()
TELEGRAM_CHAT_DEV = getenv("TELEGRAM_CHAT_DEV")


def _is_multimodal() -> bool:
    """Check if the main LLM supports multimodal input (audio/vision)."""
    return "gemini" in LLM_CHOICE and "gemini" in LLM_UTILS


async def _media_to_text(media: list[dict], context: str = "") -> str:
    """
    Use Gemini to transcribe audio or describe images into text.

    Called when the main LLM lacks multimodal capability.
    """
    is_audio = any("audio" in m.get("mime_type", "") for m in media)
    if is_audio:
        prompt = (
            "Transcribe this audio message verbatim in the same language the speaker uses. "
            "Preserve natural phrasing, filler words, and emotional tone. "
            "Do not translate, summarize, or paraphrase — write exactly what was said."
        )
    else:
        prompt = (
            "Describe this image with enough detail that someone could recreate or identify it. "
            "Cover: the medium (photo, screenshot, drawing, diagram, chart, meme, etc.), "
            "all visible text verbatim, the scene layout and composition, "
            "colors and lighting, objects and their positions, people (appearance, clothing, pose, expression), "
            "background and setting, and any notable style or aesthetic. "
            "Be thorough — omit nothing visible."
        )
    if context:
        prompt += f"\n\nUser's message for context: {context}"
    parts = [{"type": "text", "text": prompt}, *media]
    response = await LLM.get("gemini-small").ainvoke([HumanMessage(content=parts)])
    content = response.content
    if isinstance(content, list):
        content = " ".join(
            part["text"]
            for part in content
            if isinstance(part, dict) and "text" in part
        )
    return content.strip()


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

    # Consume pending images for this chat
    pending = instance.pending_media.pop(msg.chat.id, [])
    if pending:
        if _is_multimodal():
            existing = getattr(msg, "media", [])
            msg.media = [  # ty: ignore[unresolved-attribute]
                *existing,
                *[
                    {"type": "media", "data": img, "mime_type": "image/jpeg"}
                    for img in pending
                ],
            ]
        else:
            media_dicts = [
                {"type": "media", "data": img, "mime_type": "image/jpeg"}
                for img in pending
            ]
            description = await _media_to_text(media_dicts, msg.text or "")
            msg.text = f"{msg.text or ''}\n\n[Image context: {description}]".strip()

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
            elif extra.get("images"):
                paths = [p for p in extra["images"] if Path(p).exists()]
                if paths:
                    if len(paths) == 1:
                        img_bytes = await to_thread(Path(paths[0]).read_bytes)
                        await instance.bot.core.send_photo(msg.chat.id, img_bytes)
                    else:
                        for i in range(0, len(paths), 10):
                            batch = paths[i : i + 10]
                            imgs = await gather(
                                *(to_thread(Path(p).read_bytes) for p in batch)
                            )
                            media = [
                                InputMediaPhoto(InputFile(BytesIO(b))) for b in imgs
                            ]
                            await instance.bot.core.send_media_group(msg.chat.id, media)
    except Exception as e:
        print_exc()
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


@handler
async def telegram_voice(instance: AgenticBot, msg: Message) -> None:
    """Handle voice messages: attach audio as media and process through agent."""
    try:
        voice = msg.voice
        if not voice:
            return
        file_info = await instance.bot.core.get_file(voice.file_id)
        audio = await instance.bot.core.download_file(file_info.file_path)
        media = [{"type": "media", "data": audio, "mime_type": "audio/ogg"}]
        if _is_multimodal():
            msg.media = media  # ty: ignore[unresolved-attribute]
            msg.text = "🎤 [voice message]"
        else:
            transcription = await _media_to_text(media)
            msg.text = f"🎤 [voice message]: {transcription}"
        await telegram_chat(instance, msg)
    except Exception as e:
        print_exc()
        await telegram_report_issue(instance, msg, msg, e)


# Media group accumulation: {media_group_id: {"images": [], "msg": Message}}
_media_groups: dict[str, dict] = {}


@handler
async def telegram_image(instance: AgenticBot, msg: Message) -> None:
    """Handle image/photo messages: attach images as media and process through agent."""
    try:
        if not msg.photo:
            return
        # Download highest resolution
        photo = msg.photo[-1]
        file_info = await instance.bot.core.get_file(photo.file_id)
        img_bytes = await instance.bot.core.download_file(file_info.file_path)

        if msg.media_group_id:
            # Album: accumulate images, debounce processing
            group_id = msg.media_group_id
            if group_id not in _media_groups:
                _media_groups[group_id] = {"images": [], "msg": msg}
            _media_groups[group_id]["images"].append(img_bytes)
            my_count = len(_media_groups[group_id]["images"])
            # Wait briefly for more images in this group
            await sleep(1.0)
            # Only the last callback to arrive processes the group
            current = _media_groups.get(group_id)
            if not current or len(current["images"]) != my_count:
                return  # A newer callback arrived, let it handle processing
            data = _media_groups.pop(group_id)
            images = data["images"]
            album_msg = data["msg"]
        else:
            images = [img_bytes]
            album_msg = msg

        caption = (album_msg.caption or "").strip()
        media_dicts = [
            {"type": "media", "data": img, "mime_type": "image/jpeg"} for img in images
        ]
        if caption:
            # Caption present: process immediately through agent
            if _is_multimodal():
                album_msg.text = caption
                album_msg.media = media_dicts  # ty: ignore[invalid-assignment]
            else:
                description = await _media_to_text(media_dicts, caption)
                album_msg.text = f"{caption}\n\n[Image context: {description}]"
            await telegram_chat(instance, album_msg)
        else:
            # No caption: store as pending, wait for next text/voice
            instance.pending_media.setdefault(album_msg.chat.id, []).extend(images)
            timer = instance.log.received(album_msg)
            await instance.bot.reply(
                album_msg,
                "📷 Got it! Send a text or voice message with your instruction.",
            )
            instance.log.sent(album_msg, timer)
    except Exception as e:
        if msg.media_group_id and msg.media_group_id in _media_groups:
            _media_groups.pop(msg.media_group_id, None)
        print_exc()
        await telegram_report_issue(instance, msg, msg, e)
