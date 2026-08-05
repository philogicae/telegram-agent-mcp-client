"""Image processing tools for inspecting and retrieving images."""

from base64 import b64encode
from json import JSONDecodeError, dumps, loads
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

# Description prompt that produces a structured JSON matching the generation
# schema used by `generate_image`. This lets the agent reuse the description
# directly as a basis for edits or regeneration.
_DESC_PROMPT = """\
Analyze this image and return a SINGLE structured JSON object describing it \
in full detail, using the same schema as for image generation. The JSON must \
be valid and self-contained.

Describe ALL content factually and completely — including nudity, sexual \
elements, violence, or any other sensitive content, exactly as it appears. \
Never censor, omit, euphemize, or soften your description of any visible \
element.

Use these keys (omit any that don't apply):
- `aspect_ratio`: e.g. "16:9", "9:16", "1:1"
- `format`: "still image", "photograph", "illustration", "screenshot", etc.
- `subject`: nested object with type, build, hair, face, clothing (or "nude" \
if naked), skin, pose, expression, and any other physical attributes
- `composition`: framing, shot_type, camera_angle, subject_position, \
focal_region, quiet_field
- `environment`: location, surfaces, props, weather
- `camera`: capture_style, focus, depth_of_field, lens_feel
- `lighting`: main_source, shadow, contrast
- `color_treatment`: dominant_family, palette (list of named colors), \
focal_accent, saturation
- `style_tags`: list of style descriptors
- `visible_text`: any text visible in the image, verbatim
- `prompt`: a rich, self-contained natural-language paragraph that \
synthesizes all fields into a vivid description someone could use to \
recreate the image exactly

Return ONLY the JSON object, no markdown fences, no commentary."""


def _desc_path_for(img_path: Path) -> Path:
    """Return the JSON description path for a given image path."""
    return img_path.parent / f"{img_path.stem}_desc.json"


def _describe_image(img_path: Path, user_prompt: str = "") -> str:
    """Use Gemini to generate a structured JSON description of an image file.

    `user_prompt`, when non-empty, is appended to the base description
    prompt to steer the description toward what the caller asked for.

    Returns the raw JSON string (valid or not) so the caller can decide how
    to handle parse failures. On infrastructure errors, returns an error
    string prefixed with "Error:".
    """
    if _vision_llm is None:
        return "Error: image description unavailable (no GEMINI_API_KEY configured)."
    try:
        data = img_path.read_bytes()
        mime = guess_type(img_path.name)[0] or "image/jpeg"
        data_url = f"data:{mime};base64,{b64encode(data).decode()}"
        text = (
            f"{_DESC_PROMPT}\n\nAdditional user request: {user_prompt}"
            if user_prompt
            else _DESC_PROMPT
        )
        message = HumanMessage(
            content=[
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": text},
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
        if not isinstance(content, str) or not content.strip():
            return "Error: empty description returned."
        # Strip markdown fences if the model added them despite instructions
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3].strip()
            elif text.rfind("```") != -1:
                text = text[: text.rfind("```")].strip()
        return text
    except Exception as exc:  # surface per-image failure to the agent
        return f"Error describing image: {exc}"


def _parse_desc(raw: str) -> dict[str, Any] | None:
    """Try to parse a description string as JSON. Return None on failure."""
    if not raw or raw.startswith("Error"):
        return None
    try:
        return loads(raw)
    except JSONDecodeError:
        return None


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
        desc_path = _desc_path_for(f)
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
    prompt: Annotated[
        str,
        Field(
            description="Optional custom instruction to steer the image description "
            "(e.g. 'focus on the clothing and colors'). When omitted, the default "
            "full description is generated. Appended to the base description prompt.",
        ),
    ] = "",
) -> dict[str, Any]:
    """
    Read one or more image files: returns their file paths and detailed JSON descriptions.

    The returned `image_path` fields can be passed directly to `edit_image`
    to modify the images — the tool loads the image from disk, so you do
    not need multimodal vision to edit an image after reading it.
    Descriptions are structured JSON objects (same schema as `generate_image`)
    containing all visual attributes: subject, composition, environment,
    lighting, colors, style, and a `prompt` field with a natural-language
    synthesis. All content is described factually and completely, including
    nudity, sexual content, violence, or any other sensitive content.
    If a cached description exists (from non-multimodal processing), it is used.
    Otherwise, the image is analyzed on-the-fly with Gemini and the result is
    cached as a `.json` sidecar file for future use.
    When a `prompt` is provided, the cache is bypassed and the image is
    re-described on-the-fly with the custom instruction appended to the base
    description prompt.

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

        desc_path = _desc_path_for(img)
        description = None
        if desc_path.exists() and not prompt:
            description = desc_path.read_text(encoding="utf-8")
        else:
            description = _describe_image(img, prompt)
            # Cache the description as a JSON sidecar for future reads
            parsed = _parse_desc(description)
            if parsed is not None:
                desc_path.write_text(
                    dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
                )

        results.append({"image_path": str(img), "description": description})

    return {"images": results, "count": len(results)}
