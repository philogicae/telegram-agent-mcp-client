"""Image generation and editing tools using Google Gemini (Nano Banana)."""

from base64 import b64decode, b64encode
from datetime import datetime
from mimetypes import guess_type
from os import getenv
from pathlib import Path
from typing import Annotated, Any
from urllib.request import urlopen

from dotenv import load_dotenv
from langchain.tools import tool
from langchain_core.messages import HumanMessage
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    HarmBlockThreshold,
    HarmCategory,
    Modality,
)
from pydantic import Field

load_dotenv()

_API_KEY = getenv("GEMINI_API_KEY", "")
_MODEL = getenv("GEMINI_API_IMAGE_MODEL", "gemini-3.1-flash-image")

_DATA_DIR = Path(getenv("DATA_DIR", "./data")) / "image_generation"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

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

_llm: ChatGoogleGenerativeAI | None = (
    ChatGoogleGenerativeAI(
        api_key=_API_KEY,
        model=_MODEL,
        response_modalities=[Modality.IMAGE],
        safety_settings=_SAFETY_SETTINGS,
        disable_streaming="tool_calling",
    )
    if _API_KEY and _MODEL
    else None
)


_PROMPT_DESCRIPTION = """\
A single structured JSON string describing the image to generate. The model \
has a strong default aesthetic (warm, soft, glossy) — explicitly override \
every visual axis (style, lighting, color, composition) to prevent it.

NO TEXT ON IMAGE unless explicitly requested: the image must never contain \
rendered text, hex codes, labels, or watermarks. Describe colors with \
natural-language names ('deep navy blue'), never hex. If text is genuinely \
needed (logo, poster, diagram), specify exact content and typography.

Build the schema dynamically from the request. Recommended keys when \
relevant: `aspect_ratio`, `subject` (nested attributes), `composition` \
(framing, shot_type, camera_angle, focal_region), `environment`, `camera` \
(lens_feel, focus, depth_of_field), `lighting` (main_source, shadow, \
contrast), `color_treatment` (palette with descriptive names), `style_tags`.

COHESION RULES — apply unless the request says otherwise:
• Color field: unify sky, ground, water, and atmosphere through ONE dominant \
color family; supporting elements echo it. Avoid scattered decorative accents \
of unrelated colors.
• Focal accent: if a contrasting accent is used, give it exactly one carrier \
(garment, light source, fruit, reflection, sign...) with a physical cause \
and material — no random glows or generic highlights.
• Scale and spacing: relative sizes must serve a function (shelter, use, \
protection, emphasis). Supporting elements should prove the subject's role \
via gaze, spacing, contact, or repetition — never distort scale for novelty.
• Composition: one primary focal region and one substantial quiet field \
(empty space that lets the subject breathe).

LANGUAGE RULES: use concrete nouns and active verbs. No mood labels, praise, \
prestige terms ('masterpiece', 'stunning'), fake technical detail, or \
unresolved alternatives — every visual decision must be stated as a fact.

Match the domain conventions: illustration (art style, medium, palette, \
surface texture), diagram (view/projection, labels, line_weights), data viz \
(chart_type, axes, dark background, high-contrast accents), photographic \
(camera, lens, aperture, lighting setup, grain), logo (vector style, negative \
space, symmetry, exact text if needed).

ALWAYS include: a `prompt` key with a rich, self-contained natural-language \
paragraph synthesizing all fields, and a `negative_prompt` key that at \
minimum contains: "default gemini style, soft glossy render, warm auto \
lighting, generic stock photo look, text, color codes, labels, watermarks" \
plus traits contradicting the requested style.

Example: {"aspect_ratio":"9:16","format":"still image","subject":{"type":\
"anime rabbit girl","build":"slim","hair":{"color":"white","length":\
"very long"},"face":{"expression":"blank","eyes":"empty unfocused stare"},\
"clothing":"oversized faded gray hoodie"},"composition":{"framing":\
"vertical portrait","shot_type":"full-body","camera_angle":"straight-on",\
"subject_position":"centered","focal_region":"subject's face",\
"quiet_field":"bare wall filling the upper half of the frame"},\
"environment":{"location":"empty indoor room","surfaces":["dirty off-white \
wall","faded gray floor"],"props":"none"},"camera":{"capture_style":\
"direct flash snapshot","focus":"sharp on subject","depth_of_field":\
"flat"},"lighting":{"main_source":"strong on-camera flash","shadow":\
{"visibility":"strong","quality":"hard-edged"},"contrast":"high"},\
"color_treatment":{"dominant_family":"cool desaturated grays",\
"palette":["chalky white","faded gray","dusty beige"],"focal_accent":\
{"color":"deep amber","carrier":"small plastic hair clip","cause":\
"one warm object the subject wears","material":"glossy plastic"},\
"saturation":"low"},"style_tags":["dreamcore","liminal","flash \
photography"],"constraints":{"keep":["empty gaze","overexposed subject",\
"single amber accent"],"avoid":["warm cozy atmosphere","busy background",\
"extra characters","decorative colored accents"]},"prompt":"Create a 9:16 \
dreamcore flash snapshot of a slim anime rabbit girl with very long white \
hair and an oversized faded gray hoodie standing centered in an empty \
uncanny room with a dirty off-white wall. A harsh on-camera flash \
overexposes her body and throws a heavy hard-edged shadow behind her. Her \
empty unfocused stare is the single focal region; the bare upper wall \
stays quiet. The entire scene stays in chalky whites and faded grays, \
except one glossy deep amber hair clip catching the flash.","negative_prompt":\
"default gemini style, soft glossy render, warm auto lighting, generic \
stock photo look, text, color codes, labels, watermarks, smile, warm cozy \
room, extra people, colorful decorations, blurry subject"}\
"""


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
        Field(description=_PROMPT_DESCRIPTION),
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


def _load_image_data_url(image: str) -> str | dict[str, str]:
    """Load a local path or http(s) URL into a base64 data URL."""
    try:
        if image.startswith(("http://", "https://")):
            with urlopen(image, timeout=30) as resp:  # noqa: S310
                data = resp.read()
            mime = resp.headers.get_content_type()
        else:
            path = Path(image).expanduser()
            data = path.read_bytes()
            mime = guess_type(path.name)[0]
    except Exception as e:
        return {"error": f"Could not load image '{image}': {e}"}
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    return f"data:{mime};base64,{b64encode(data).decode()}"


@tool
def edit_image(
    image: Annotated[
        str,
        Field(
            description="Local file path or http(s) URL of the source image to edit.",
        ),
    ],
    prompt: Annotated[
        str,
        Field(
            description=(
                "Natural-language instruction describing the edit to apply to "
                "the source image (e.g. 'remove the background', 'make it black "
                "and white', 'add a sunset sky'). Be specific about what to "
                "change, and state explicitly that everything not mentioned "
                "(subject, count, identity, action, setting, objects, colors, "
                "text, aspect ratio) must be preserved exactly."
            ),
        ),
    ],
) -> dict[str, Any]:
    """
    Edit an existing image (local path or URL) with Google Gemini (Nano Banana).

    Returns {image_path, model_name} on success, or {error} on failure.
    The edited image is saved as a PNG file and its path is returned in
    `image_path` so the caller can display it.
    """
    if _llm is None:
        return {"error": "GEMINI_API_KEY or GEMINI_API_IMAGE_MODEL is not set."}

    data_url = _load_image_data_url(image)
    if isinstance(data_url, dict):
        return data_url

    message = HumanMessage(
        content=[
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": prompt},
        ]
    )
    try:
        response = _llm.invoke([message])
        image_bytes = _extract_image_bytes(response.content)
    except Exception as e:
        return {"error": f"Gemini API error: {e}"}

    if not image_bytes:
        return {"error": "No image was returned by the model."}

    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    path = _DATA_DIR / f"edit_{timestamp}.png"
    path.write_bytes(image_bytes)
    return {"image_path": str(path), "model_name": _MODEL}
