"""Telegram bot handlers."""

from asyncio import Event, create_subprocess_exec, gather, sleep
from datetime import datetime
from io import BytesIO
from os import getenv
from pathlib import Path
from subprocess import DEVNULL, PIPE
from traceback import print_exc

import aiofiles.os  # ty: explicit submodule import
from dotenv import load_dotenv
from langchain.messages import HumanMessage
from telebot.types import InputFile, InputMediaPhoto, Message

from ...core.llm import LLM, LLM_CHOICE, LLM_UTILS
from ..abstract import AgenticBot, handler
from ..utils import str_size, unpack_user

load_dotenv()
TELEGRAM_CHAT_DEV = getenv("TELEGRAM_CHAT_DEV")
_RECEIVED_DIR = Path(getenv("DATA_DIR", "./data")) / "image_received"
_RECEIVED_DIR.mkdir(parents=True, exist_ok=True)


def _save_received_image(img_bytes: bytes) -> str:
    """Persist a received image to disk and return its path."""
    ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    path = _RECEIVED_DIR / f"img_{ts}.jpg"
    path.write_bytes(img_bytes)
    return str(path)


async def _read_image(path: str) -> bytes:
    async with aiofiles.open(path, "rb") as f:
        return await f.read()


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
async def telegram_chat(
    instance: AgenticBot, msg: Message, overwrite: Message | None = None
) -> None:
    """Handle chat messages and orchestrate agent responses."""
    timer = instance.log.received(msg)
    if msg.text in ["/start", "/help"]:
        await instance.bot.send(msg, "🌟 Welcome! How can I help you?")
        return
    if msg.text == "/tts":
        user_id = msg.from_user.id if msg.from_user else 0
        current = instance.tts_enabled.get(user_id, False)
        instance.tts_enabled[user_id] = not current
        state = "on 🔊" if not current else "off 🔇"
        await instance.bot.send(msg, f"TTS is now {state}")
        return

    chat_id = msg.chat.id
    if msg.text == "/cancel":
        if chat_id in instance.cancel_events:
            instance.cancel_events[chat_id].set()
            await instance.bot.send(msg, "⏹️ Cancelling...")
        else:
            await instance.bot.send(msg, "Nothing to cancel.")
        return

    # Rate limiting: reject if this chat already has an active agent run
    if chat_id in instance.cancel_events:
        await instance.bot.send(
            msg, "⏳ I'm still working on your previous message. Send /cancel to abort."
        )
        return

    # Claim the slot immediately to prevent concurrent runs in the same chat.
    # This must happen before any await to avoid a TOCTOU race.
    cancel_event = Event()
    instance.cancel_events[chat_id] = cancel_event

    # Consume pending images for this chat
    pending = instance.pending_media.pop(msg.chat.id, [])
    if pending:
        img_paths = [p for _, p in pending]
        if _is_multimodal():
            existing = getattr(msg, "media", [])
            msg.media = [  # ty: ignore[unresolved-attribute]
                *existing,
                *[
                    {"type": "media", "data": img, "mime_type": "image/jpeg"}
                    for img, _ in pending
                ],
            ]
            paths_str = "\n".join(f"  - {p}" for p in img_paths)
            msg.text = (
                f"{msg.text or ''}\n\n[Received image files:]\n{paths_str}".strip()
            )
        else:
            # Describe each image individually and persist descriptions to disk
            # so the agent can reference them later even after context loss.
            desc_parts = []
            for img_bytes, img_path in pending:
                media_dicts = [
                    {"type": "media", "data": img_bytes, "mime_type": "image/jpeg"}
                ]
                desc = await _media_to_text(media_dicts, msg.text or "")
                desc_path = str(
                    Path(img_path).parent / f"{Path(img_path).stem}_desc.txt"
                )
                async with aiofiles.open(desc_path, "w", encoding="utf-8") as f:
                    await f.write(desc)
                desc_parts.append(
                    f"  - {img_path}\n    Description: {desc_path}\n    Context: {desc}"
                )
            msg.text = (
                f"{msg.text or ''}\n\n[Received images:]\n" + "\n".join(desc_parts)
            ).strip()

    if overwrite is None:
        init = instance.bot.reply if msg.chat.type != "private" else instance.bot.send
        overwrite = await init(msg)
    reply = overwrite
    prev = ""
    try:
        async for agent, step, done, extra in instance.agent.chat(msg):
            if cancel_event.is_set():
                break
            if step != prev:
                prev = step
                await instance.bot.edit(
                    reply,
                    step,
                    final=done,
                    agent=agent,
                    model_text=extra.get("model_text", False),
                )
                if not done and not extra.get("model_text") and step[0] == "✅":
                    tool = extra.get("tool")
                    if tool and tool in instance.managers:
                        await instance.managers[tool].notify(
                            msg.chat.id, extra.get("output")
                        )
                elif not done and not extra.get("model_text") and step[0] == "❌":
                    await telegram_report_issue(
                        instance,
                        msg,
                        reply,
                        f"{agent} -> Tool error = {extra.get('tool')}",
                    )
            if not done:
                await sleep(0.5)  # No need to spam
            elif extra.get("images"):
                paths = [p for p in extra["images"] if await aiofiles.os.path.exists(p)]
                if paths:
                    await instance.bot.core.send_chat_action(
                        msg.chat.id, "upload_photo"
                    )
                    if len(paths) == 1:
                        async with aiofiles.open(paths[0], "rb") as f:
                            img_bytes = await f.read()
                        await instance.bot.core.send_photo(
                            msg.chat.id,
                            img_bytes,
                            show_caption_above_media=True,
                        )
                    else:
                        for i in range(0, len(paths), 10):
                            batch = paths[i : i + 10]
                            imgs = await gather(*(_read_image(p) for p in batch))
                            media = [
                                InputMediaPhoto(InputFile(BytesIO(b))) for b in imgs
                            ]
                            await instance.bot.core.send_media_group(msg.chat.id, media)
            # TTS: send audio of the final response if enabled
            if done and msg.from_user and instance.tts_enabled.get(msg.from_user.id):
                instance.log.info(f"[{msg.chat.id}] Generating TTS voice message...")
                await instance.bot.core.send_chat_action(msg.chat.id, "upload_voice")
                recording = await instance.bot.send(msg, "🎙️ I'm recording...")
                adapted = await LLM.tts_adapt(step)
                audio_bytes = await LLM.tts(adapted)
                if not audio_bytes:
                    instance.log.warning(
                        f"[{msg.chat.id}] TTS generation returned no audio"
                    )
                    await instance.bot.send(
                        msg, "🎙️ TTS failed — check logs for details."
                    )
                if audio_bytes:
                    # Telegram voice messages require OGG/OPUS
                    proc = await create_subprocess_exec(
                        "ffmpeg",
                        "-i",
                        "pipe:0",
                        "-c:a",
                        "libopus",
                        "-f",
                        "ogg",
                        "pipe:1",
                        stdin=PIPE,
                        stdout=PIPE,
                        stderr=DEVNULL,
                    )
                    ogg, _ = await proc.communicate(audio_bytes)
                    voice = ogg if proc.returncode == 0 and ogg else audio_bytes
                    await instance.bot.core.send_voice(
                        msg.chat.id, InputFile(BytesIO(voice), file_name="voice.ogg")
                    )
                    instance.log.info(f"[{msg.chat.id}] TTS voice message sent")
                await instance.bot.delete(recording)
    except Exception as e:
        print_exc()
        await telegram_report_issue(instance, msg, reply, e)
    finally:
        instance.cancel_events.pop(chat_id, None)
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
                msg.chat.id, str(getattr(msg.document, "file_name", "unknown"))
            )
            instance.log.warning("File: too big. Redirected to Docs UI.")
        else:
            await telegram_report_issue(instance, msg, msg, e)
            instance.log.exception("File handling error")


@handler
async def telegram_voice(instance: AgenticBot, msg: Message) -> None:
    """Handle voice messages: attach audio as media and process through agent."""
    reply = None
    try:
        voice = msg.voice
        if not voice:
            return
        # Rate limiting: reject early before expensive download/transcription
        if msg.chat.id in instance.cancel_events:
            await instance.bot.send(
                msg,
                "⏳ I'm still working on your previous message. Send /cancel to abort.",
            )
            return
        # Claim the slot immediately to prevent concurrent runs.
        cancel_event = Event()
        instance.cancel_events[msg.chat.id] = cancel_event
        # Send "I'm listening..." immediately, before download/transcription
        init = instance.bot.reply if msg.chat.type != "private" else instance.bot.send
        reply = await init(msg, "🔊 I'm listening...")
        file_info = await instance.bot.core.get_file(voice.file_id)
        audio = await instance.bot.core.download_file(file_info.file_path)
        media = [{"type": "media", "data": audio, "mime_type": "audio/ogg"}]
        if _is_multimodal():
            msg.media = media  # ty: ignore[unresolved-attribute]
            msg.text = "🎤 [voice message]"
        else:
            transcription = await _media_to_text(media)
            msg.text = f"🎤 [voice message]: {transcription}"
        # Replace "I'm listening..." with "I'm thinking..." and set up edit cache
        await instance.bot.edit(reply, instance.bot.waiting, replace=True)
        instance.bot.edit_cache[reply.id] = {  # ty: ignore[unresolved-attribute]
            "current": 0,
            "content": [instance.bot.waiting],
        }
        # telegram_chat will claim the slot we already set; pass overwrite so
        # it skips the init() call and reuses our reply.
        instance.cancel_events.pop(msg.chat.id, None)
        await telegram_chat(instance, msg, overwrite=reply)
    except Exception as e:
        print_exc()
        await telegram_report_issue(instance, msg, reply or msg, e)
    finally:
        instance.cancel_events.pop(msg.chat.id, None)


# Media group accumulation: {media_group_id: {"images": [], "msg": Message}}
_media_groups: dict[str, dict] = {}


@handler
async def telegram_image(instance: AgenticBot, msg: Message) -> None:
    """Handle image/photo messages: attach images as media and process through agent."""
    try:
        if not msg.photo:
            return
        # Rate limiting: reject early before expensive download
        if msg.chat.id in instance.cancel_events:
            await instance.bot.send(
                msg,
                "⏳ I'm still working on your previous message. Send /cancel to abort.",
            )
            return
        # Download highest resolution
        photo = msg.photo[-1]
        file_info = await instance.bot.core.get_file(photo.file_id)
        img_bytes = await instance.bot.core.download_file(file_info.file_path)
        img_path = _save_received_image(img_bytes)

        if msg.media_group_id:
            # Album: accumulate images, debounce processing
            group_id = msg.media_group_id
            if group_id not in _media_groups:
                _media_groups[group_id] = {"images": [], "msg": msg}
            _media_groups[group_id]["images"].append((img_bytes, img_path))
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
            images = [(img_bytes, img_path)]
            album_msg = msg

        caption = (album_msg.caption or "").strip()
        if caption:
            # Caption present: process immediately through agent.
            # Check rate limiting BEFORE storing pending media so we don't
            # leak orphaned images into pending_media if telegram_chat rejects.
            if album_msg.chat.id in instance.cancel_events:
                await instance.bot.send(
                    album_msg,
                    "⏳ I'm still working on your previous message. Send /cancel to abort.",
                )
                return
            instance.pending_media.setdefault(album_msg.chat.id, []).extend(images)
            album_msg.text = caption
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
