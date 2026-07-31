"""Image processing tools for inspecting and retrieving images."""

from base64 import b64encode
from mimetypes import guess_type
from os import getenv
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from langchain.tools import tool
from langchain_core.messages import HumanMessage
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    HarmBlockThreshold,
    HarmCategory,
)
from pydantic import Field

load_dotenv()

_API_KEY = getenv("GEMINI_API_KEY", "")
_MODEL_SMALL = getenv("GEMINI_API_MODEL_SMALL", "gemini-2.5-flash")

_DATA_DIR = Path(getenv("DATA_DIR", "./data"))
_IMAGE_DIRS = {
    "received": _DATA_DIR / "image_received",
    "generated": _DATA_DIR / "image_generation",
}
_IMAGE_EXTS = (".jpg", ".png", ".jpeg")

_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_IMAGE_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_IMAGE_HATE: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_IMAGE_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_IMAGE_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

_vision_llm: ChatGoogleGenerativeAI | None = (
    ChatGoogleGenerativeAI(
        api_key=_API_KEY,
        model=_MODEL_SMALL,
        safety_settings=_SAFETY_SETTINGS,
    )
    if _API_KEY and _MODEL_SMALL
    else None
)

_DESC_PROMPT = (
    "Describe this image with enough detail that someone could recreate or identify it. "
    "Cover: the medium (photo, screenshot, drawing, diagram, chart, meme, etc.), "
    "all visible text verbatim, the scene layout and composition, "
    "colors and lighting, objects and their positions, people (appearance, clothing, pose, expression), "
    "background and setting, and any notable style or aesthetic. "
    "Be thorough — omit nothing visible."
)


def _describe_image(img_path: Path) -> str:
    """Use Gemini to generate a text description of an image file.

    Returns an error string (rather than raising or returning None) so the
    caller can include it per-image without failing the whole batch.
    """
    if _vision_llm is None:
        return "Error: image description unavailable (no GEMINI_API_KEY configured)."
    try:
        data = img_path.read_bytes()
        mime = guess_type(img_path.name)[0] or "image/jpeg"
        data_url = f"data:{mime};base64,{b64encode(data).decode()}"
        message = HumanMessage(
            content=[
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": _DESC_PROMPT},
            ]
        )
        response = _vision_llm.invoke([message])
        content = response.content
        if isinstance(content, list):
            content = " ".join(
                part["text"]
                for part in content
                if isinstance(part, dict) and "text" in part
            )
        return (
            content.strip()
            if isinstance(content, str)
            else "Error: empty description returned."
        )
    except Exception as exc:  # surface per-image failure to the agent
        return f"Error describing image: {exc}"


@tool
def list_images(
    limit: Annotated[
        int,
        Field(
            description="Number of images per page (default 20). Set to 0 for all.",
        ),
    ] = 20,
    page: Annotated[
        int,
        Field(
            description="Page number (1-indexed). Default 1. "
            "Used with limit for pagination — e.g. limit=10&page=2 returns "
            "images 11-20.",
        ),
    ] = 1,
) -> dict[str, Any]:
    """
    List all images on disk (received from users and generated), sorted newest first.

    Supports pagination via limit and page parameters.

    Returns {images: [{path, source, description_path, has_description}], count, page, limit, total} on success,
    or {error} if no image directories exist.
    """
    files: list[tuple[str, Path]] = []
    for source, dir_path in _IMAGE_DIRS.items():
        if dir_path.exists():
            files.extend(
                (source, f) for f in dir_path.iterdir() if f.suffix in _IMAGE_EXTS
            )

    if not files:
        return {"error": "No images found."}

    files.sort(key=lambda item: item[1].stat().st_mtime, reverse=True)
    total = len(files)

    if limit and limit > 0:
        offset = (page - 1) * limit if page > 1 else 0
        files = files[offset : offset + limit]
    else:
        page = 1
        limit = total

    images = []
    for source, f in files:
        desc_path = f.parent / f"{f.stem}_desc.txt"
        images.append(
            {
                "path": str(f),
                "source": source,
                "description_path": str(desc_path) if desc_path.exists() else None,
                "has_description": desc_path.exists(),
            }
        )
    return {
        "images": images,
        "count": len(images),
        "page": page,
        "limit": limit,
        "total": total,
    }


@tool
def read_images(
    image_paths: Annotated[
        list[str],
        Field(
            description="List of image file paths to read (e.g. as returned by "
            "list_images, generate_image, or shown in [Received image files:]). "
            "Works with any local image files.",
        ),
    ],
) -> dict[str, Any]:
    """
    Read one or more image files: returns their file paths and detailed text descriptions.

    The image paths can be passed to `edit_image` to modify the images.
    Descriptions are detailed text transcriptions of the image contents.
    If a cached description exists (from non-multimodal processing), it is used.
    Otherwise, the image is analyzed on-the-fly with Gemini.

    Returns {images: [{image_path, description}], count} on success.
    Individual errors are included per-image without failing the batch.
    """
    results = []
    for path_str in image_paths:
        img = Path(path_str)
        if not img.exists():
            results.append(
                {"image_path": path_str, "error": f"Image not found: {path_str}"}
            )
            continue

        desc_path = img.parent / f"{img.stem}_desc.txt"
        description = None
        if desc_path.exists():
            description = desc_path.read_text(encoding="utf-8")
        else:
            description = _describe_image(img)

        results.append({"image_path": str(img), "description": description})

    return {"images": results, "count": len(results)}
