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
                "A single highly detailed, structured JSON string describing the "
                "image to generate. The model has a strong default aesthetic (warm, "
                "soft, glossy, 'nano banana' look) — you MUST explicitly override "
                "every visual axis (style, lighting, color, composition, texture) to "
                "prevent that default from leaking in. Never rely on the model's "
                "implicit style; define it precisely.\n\n"
                "Build the schema DYNAMICALLY from the request: include only the keys "
                "that matter and adapt naming to the domain. Be exhaustive and "
                "specific — every visual decision should be a deliberate choice.\n\n"
                "Recommended top-level keys when relevant: `aspect_ratio`, `format`, "
                "`subject` (with nested attributes), `composition` (framing, "
                "shot_type, camera_angle, subject_position, pose, crop_rule), "
                "`environment`, `camera` (capture_style, lens_feel, focus, "
                "depth_of_field), `lighting` (main_source, exposure, shadow, "
                "contrast), `color_treatment` (contrast, saturation, palette), "
                "`style_tags`, and `constraints` (`keep` / `avoid` lists).\n\n"
                "ALWAYS include a `prompt` key holding a rich natural-language "
                "paragraph that synthesizes all fields, and a `negative_prompt` key "
                "listing comma-separated traits to exclude.\n\n"
                "DOMAIN-SPECIFIC STYLE GUIDANCE — pick the right category and apply "
                "its conventions:\n"
                "• Artistic / illustration: define art style, medium, brushwork, "
                "line quality, color palette, mood, lighting setup, composition. "
                "Specify whether it's anime, painting, 3D render, pixel art, etc. "
                'Example: {"aspect_ratio":"9:16","format":"still image",'
                '"subject":{"type":"anime rabbit girl","build":"slim",'
                '"hair":{"color":"white","length":"very long"},'
                '"face":{"expression":"blank","eyes":"empty unfocused '
                'stare"}},"composition":{"framing":"vertical portrait",'
                '"shot_type":"three-quarter to full-body",'
                '"camera_angle":"straight-on","subject_position":"centered"},'
                '"environment":{"location":"empty indoor room",'
                '"surface_colors":["dirty off-white","faded gray"]},'
                '"camera":{"capture_style":"direct flash snapshot",'
                '"focus":"sharp on subject"},'
                '"lighting":{"main_source":"strong on-camera flash",'
                '"shadow":{"visibility":"strong","quality":"hard-edged"}},'
                '"color_treatment":{"contrast":"high","saturation":"low",'
                '"palette":["chalky white","faded gray"]},'
                '"style_tags":["dreamcore","liminal","flash photography"],'
                '"constraints":{"keep":["empty gaze","overexposed subject"],'
                '"avoid":["warm cozy atmosphere","busy background",'
                '"extra characters"]},'
                '"prompt":"Create a 9:16 dreamcore flash snapshot of a long '
                "white-haired anime rabbit girl standing in an empty uncanny room, "
                "overexposed by a harsh on-camera flash with a heavy hard-edged "
                'cast shadow.",'
                '"negative_prompt":"smile, warm lighting, cozy room, extra '
                'people, realistic rabbit body, low contrast, blurry subject"}\n'
                "• Technical / diagram: specify diagram type, view/projection "
                "(top, isometric, cross-section), line_weights, stroke style, "
                "label_placement, annotations, dimensions, scale bars, grid, "
                "materials. Use keys like `dimensions`, `labels`, `annotations`, "
                "`view`, `projection`, `scale`, `materials`, `line_weights`.\n"
                "• Report / research / data visualization: professional, clean, "
                "dark-mode aesthetic. Define chart type, data structure, axis "
                "labels, legend style, color scheme (dark background with "
                "high-contrast accent colors), typography (sans-serif, "
                "monospace for data), grid lines, spacing, padding. Use keys "
                "like `chart_type`, `data_layers`, `axes`, `legend`, "
                '`typography`, `background` (e.g. "#0d1117"), '
                "`accent_colors`, `grid_style`.\n"
                "• Photographic: specify camera, lens, focal length, aperture, "
                "film stock or digital sensor character, lighting setup "
                "(key/fill/rim), color grading, grain, depth of field.\n"
                "• Logo / branding: specify geometric construction, vector "
                "style, color palette (hex), negative space, symmetry, "
                "stroke vs fill, scalability constraints.\n\n"
                "In `negative_prompt`, ALWAYS include at minimum: "
                '"default gemini style, nano banana aesthetic, soft glossy '
                'render, warm auto lighting, generic stock photo look" plus '
                "any traits contradictory to the requested style."
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
