"""Image generation tool using Google Gemini (Nano Banana)."""

from base64 import b64decode
from datetime import datetime
from os import getenv
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from langchain.tools import tool
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI, Modality
from pydantic import Field

load_dotenv()

_API_KEY = getenv("GEMINI_API_KEY", "")
_MODEL = getenv("GEMINI_API_IMAGE_MODEL", "gemini-3.1-flash-image")

_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "image_generation"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_llm: ChatGoogleGenerativeAI | None = (
    ChatGoogleGenerativeAI(
        api_key=_API_KEY,
        model=_MODEL,
        response_modalities=[Modality.IMAGE],
        disable_streaming="tool_calling",
    )
    if _API_KEY and _MODEL
    else None
)


def _extract_image_bytes(content: Any) -> bytes | None:
    """Extract raw image bytes from an AIMessage content."""
    if isinstance(content, str):
        return None
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "image_url":
            continue
        url = block.get("image_url", {}).get("url", "")
        if url.startswith("data:"):
            _, _, b64 = url.partition(",")
            return b64decode(b64)
    return None


@tool
def generate_image(
    prompt: Annotated[
        str,
        Field(
            description=(
                "Detailed text description of the image to generate. "
                "Include subject, style, lighting, composition, colors, "
                "and any other relevant visual details."
            ),
        ),
    ],
) -> dict[str, Any]:
    """
    Generate an image from a detailed text prompt using Google Gemini (Nano Banana).

    Returns {image_path, model_name} on success, or {error} on failure.
    The generated image is saved as a PNG file and its path is returned in
    `image_path` so the caller can display it.
    """
    if _llm is None:
        return {"error": "GEMINI_API_KEY or GEMINI_API_IMAGE_MODEL is not set."}

    try:
        response = _llm.invoke([HumanMessage(prompt)])
        image_bytes = _extract_image_bytes(response.content)
    except Exception as e:
        return {"error": f"Gemini API error: {e}"}

    if not image_bytes:
        return {"error": "No image was returned by the model."}

    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    path = _DATA_DIR / f"img_{timestamp}.png"
    path.write_bytes(image_bytes)
    return {"image_path": str(path), "model_name": _MODEL}
