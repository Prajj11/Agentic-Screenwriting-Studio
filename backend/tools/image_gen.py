"""
Gemini Image Generation tool for the Visualizer and Dialogue Specialist agents.

Uses Gemini's native image generation via `generate_content` with
`response_modalities=["IMAGE"]` — the approach from the Google Cloud
Platform notebook (intro_gemini_3_image_gen.ipynb).

This replaces the deprecated `generate_images` / Imagen 3 API.

CHARACTER VISUAL CONSISTENCY SYSTEM
────────────────────────────────────
Every image-generation function automatically:
  1. Reads the Character Bible's `visual_description` field for each
     character present in the scene.
  2. Injects those descriptions verbatim into the prompt as a
     "CHARACTER APPEARANCE SHEET" block so the AI model treats them
     as hard constraints rather than suggestions.
  3. Optionally loads reference portrait images and feeds them as
     multimodal context (when available) so the model can "see"
     what the character looks like.

This ensures that a character's hair color, build, clothing, scars, etc.
remain identical in Scene 1, Scene 5, and Scene 20.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Helper: build character appearance sheet ──────────────────────────

def _build_character_appearance_block(characters_json: str) -> str:
    """
    Build a structured CHARACTER APPEARANCE SHEET from a characters JSON string
    (as returned by get_character_visuals_for_scene or get_character_bible).

    This block is injected into every image-generation prompt to enforce
    visual consistency across scenes.
    """
    if not characters_json:
        return ""

    try:
        data = json.loads(characters_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    # Handle both raw character bible format and visual-summary format
    chars = data.get("characters", data) if isinstance(data, dict) else {}
    if not chars:
        return ""

    lines = [
        "\n═══ CHARACTER APPEARANCE SHEET (MANDATORY — DO NOT DEVIATE) ═══",
        "Depict each character EXACTLY as described below. Do NOT change any",
        "physical attribute (hair, skin, build, age, clothing, scars, etc.).\n",
    ]

    for name, info in chars.items():
        if isinstance(info, dict):
            vis = info.get("visual_description", "")
        elif isinstance(info, str):
            vis = info
        else:
            continue
        if vis:
            lines.append(f"  ▸ {name.upper()}: {vis}")

    lines.append("\n═══ END CHARACTER APPEARANCE SHEET ═══\n")
    return "\n".join(lines)


def _load_reference_portraits(characters_json: str) -> list:
    """
    Load reference portrait image bytes for characters that have one.
    Returns a list of (name, image_bytes) tuples.
    """
    if not characters_json:
        return []

    try:
        data = json.loads(characters_json)
    except (json.JSONDecodeError, TypeError):
        return []

    chars = data.get("characters", data) if isinstance(data, dict) else {}
    portraits = []

    for name, info in chars.items():
        if not isinstance(info, dict):
            continue
        portrait_path = info.get("reference_portrait")
        if not portrait_path:
            continue
        # Resolve the path — could be a relative URL or absolute path
        if portrait_path.startswith("/api/media/images/"):
            # Convert API URL to filesystem path
            from config import settings
            filename = portrait_path.split("/")[-1]
            filepath = Path(settings.output_images_dir) / filename
        else:
            filepath = Path(portrait_path)

        if filepath.exists():
            try:
                img_bytes = filepath.read_bytes()
                portraits.append((name, img_bytes))
                logger.info(f"Loaded reference portrait for '{name}' ({len(img_bytes)} bytes)")
            except Exception as e:
                logger.warning(f"Could not load reference portrait for '{name}': {e}")

    return portraits


# ── Public API ────────────────────────────────────────────────────────

async def generate_character_portrait(
    character_name: str,
    visual_description: str,
    style_hints: str = "photorealistic headshot, neutral studio lighting, clean background",
) -> str:
    """
    Generate a canonical reference portrait for a character.

    This should be called ONCE per character, ideally right after the
    StoryArchitect creates the character bible entry. The resulting image
    becomes the "ground truth" for how the character looks and is fed as
    visual context into all subsequent scene-image generations.

    Args:
        character_name: The character's name (for labelling the output).
        visual_description: The character's FULL visual_description from the
            Character Bible (age, ethnicity, face, hair, eyes, build, wardrobe, etc.).
        style_hints: Optional style overrides. Defaults to a clean studio headshot.

    Returns:
        JSON with the generated portrait path, URL, and metadata.
    """
    from config import settings

    prompt = (
        f"Generate a photorealistic character portrait for a screenplay character.\n\n"
        f"CHARACTER: {character_name}\n"
        f"APPEARANCE: {visual_description}\n\n"
        f"Requirements:\n"
        f"- Head-and-shoulders portrait, facing slightly toward camera\n"
        f"- Neutral expression showing character personality\n"
        f"- Clean, uncluttered background (studio or simple environment)\n"
        f"- Sharp focus on face and distinctive features\n"
        f"- {style_hints}\n"
        f"- Do NOT include text, labels, watermarks, or UI elements\n"
        f"- This portrait will be used as a reference for depicting this character\n"
        f"  consistently across multiple scenes — capture ALL the described features\n"
        f"  clearly and accurately."
    )

    return await _generate_image_with_gemini(
        prompt,
        prefix=f"portrait_{character_name.lower().replace(' ', '_')}",
        settings=settings,
    )


async def generate_mood_board(
    scene_description: str,
    style_hints: str = "",
    character_visuals: str = "",
) -> str:
    """
    Generate a concept art / mood board image for a scene.

    Uses Gemini's generate_content API with response_modalities=["IMAGE"]
    as shown in the Google Cloud Platform notebook.

    Args:
        scene_description: Description of the scene's setting, mood, and visual elements.
                          Example: "A dimly lit 1920s speakeasy. Smoke curls through amber light.
                          Jazz musicians play in the corner. A lone detective sits at the bar."
        style_hints: Optional style directions.
                    Example: "Film noir, high contrast, moody lighting, cinematic"
        character_visuals: JSON string of character visual data (from get_character_visuals_for_scene).
                          When provided, character appearance descriptions are injected into the prompt
                          to ensure visual consistency across scenes.

    Returns:
        JSON with the generated image path and metadata.
    """
    from config import settings

    # Build the prompt with character consistency block
    prompt = f"Generate a cinematic concept art image for a screenplay scene:\n\n{scene_description}"

    # Inject character appearance sheet if available
    appearance_block = _build_character_appearance_block(character_visuals)
    if appearance_block:
        prompt += f"\n{appearance_block}"

    if style_hints:
        prompt += f"\n\nVisual style: {style_hints}"
    prompt += (
        "\n\nStyle: photorealistic cinematic concept art, film production mood board, "
        "dramatic lighting, professional cinematography, widescreen composition"
    )

    # Load reference portraits for multimodal context
    portraits = _load_reference_portraits(character_visuals) if character_visuals else []

    return await _generate_image_with_gemini(
        prompt,
        prefix="mood",
        settings=settings,
        reference_images=portraits,
    )


async def generate_scene_image(
    scene_description: str,
    dialogue_context: str = "",
    characters: str = "",
    character_visuals: str = "",
) -> str:
    """
    Generate a visual illustration for a specific scene moment or dialogue beat.

    Creates a cinematic still/frame that captures a key moment from the scene —
    perfect for visualizing character interactions, dramatic moments, or
    establishing shots during the screenwriting process.

    Args:
        scene_description: The scene setting and action being depicted.
                          Example: "Two detectives face each other across a rain-soaked
                          rooftop at night. City lights glow below."
        dialogue_context: Optional key dialogue or emotional beat being depicted.
                         Example: "'I know what you did last summer,' she whispers."
        characters: Optional character descriptions for visual accuracy (legacy fallback).
                   Example: "Sarah: tall, red hair, leather jacket. Mike: stocky, bald, suit."
        character_visuals: JSON string of character visual data (from get_character_visuals_for_scene).
                          This is the PREFERRED way to pass character appearance data for
                          cross-scene consistency. When provided, overrides the `characters` arg.

    Returns:
        JSON with the generated image path and metadata.
    """
    from config import settings

    # Build a rich scene-specific prompt
    prompt = f"Generate a cinematic film still capturing this screenplay moment:\n\n"
    prompt += f"Scene: {scene_description}\n"

    # Inject character appearance sheet (preferred over raw `characters` string)
    appearance_block = _build_character_appearance_block(character_visuals)
    if appearance_block:
        prompt += appearance_block
    elif characters:
        # Legacy fallback: use the raw characters string
        prompt += f"\nCharacters: {characters}\n"

    if dialogue_context:
        prompt += f"\nMoment: {dialogue_context}\n"
    prompt += (
        "\nStyle: cinematic film still, dramatic composition, professional lighting, "
        "movie production quality, atmospheric, widescreen frame"
    )

    # Load reference portraits for multimodal context
    portraits = _load_reference_portraits(character_visuals) if character_visuals else []

    return await _generate_image_with_gemini(
        prompt,
        prefix="scene",
        settings=settings,
        reference_images=portraits,
    )


async def _generate_image_with_gemini(
    prompt: str,
    prefix: str,
    settings,
    reference_images: list | None = None,
) -> str:
    """
    Core image generation using Gemini's generate_content with response_modalities=["IMAGE"].

    This follows the pattern from the Google Cloud Platform notebook:
    https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/getting-started/intro_gemini_3_image_gen.ipynb

    Uses client.models.generate_content() with GenerateContentConfig(response_modalities=["IMAGE"])
    instead of the deprecated client.models.generate_images().

    Args:
        prompt: The text prompt for image generation.
        prefix: Filename prefix (e.g. "mood", "scene", "portrait_jake").
        settings: The application settings object.
        reference_images: Optional list of (name, bytes) tuples — reference portrait
            images that are sent as multimodal context so the model can "see"
            what characters look like and reproduce their appearance.
    """
    # Determine which model to use — prefer the configured one, fall back to known-good
    image_model = getattr(settings, "gemini_image_gen_model", None) or "gemini-2.5-flash-image"

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )

        # Build contents: plain string when no reference images (most common),
        # or multimodal list with reference portraits + text prompt.
        if reference_images:
            contents = []
            for char_name, img_bytes in reference_images:
                contents.append(
                    types.Part.from_text(
                        text=(
                            f"Reference portrait of {char_name} — "
                            f"depict this character with EXACTLY this appearance in the generated image:"
                        )
                    )
                )
                contents.append(
                    types.Part.from_bytes(
                        data=img_bytes,
                        mime_type="image/jpeg",
                    )
                )
            contents.append(types.Part.from_text(text=prompt))
        else:
            # No reference images — pass as plain string (the original working approach)
            contents = prompt

        logger.info(f"Generating image with model={image_model}, prompt={prompt[:80]}...")

        response = client.models.generate_content(
            model=image_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="16:9",
                ),
                safety_settings=[
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    ),
                ]
            )
        )

        # Extract image data from response
        image_data = None
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_data = part.inline_data.data
                    break

        if image_data:
            ext = "jpg"
            output_dir = Path(settings.output_images_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = output_dir / filename

            with open(filepath, "wb") as f:
                f.write(image_data)

            logger.info(f"Generated {prefix} image via {image_model}: {filepath}")
            return json.dumps({
                "success": True,
                "image_path": str(filepath),
                "filename": filename,
                "url": f"/api/media/images/{filename}",
                "prompt_used": prompt[:200],
                "model": image_model,
                "reference_portraits_used": len(reference_images) if reference_images else 0,
            })
        else:
            reason = "Unknown"
            if response.candidates and response.candidates[0].finish_reason:
                reason = response.candidates[0].finish_reason
            return json.dumps({
                "success": False,
                "error": f"No image was generated. Finish reason: {reason}. The prompt may have been filtered.",
            })

    except Exception as e:
        logger.warning(f"Vertex AI image generation failed ({e}). Falling back to Pollinations API...")

        # ── Pollinations.ai free fallback ─────────────────────────────
        # If the GCP project doesn't have access to the image model,
        # we fall back to the free Pollinations.ai API to ensure the
        # user always gets a real generated image (not just a placeholder).
        import urllib.request
        import urllib.parse

        try:
            safe_prompt = urllib.parse.quote(prompt[:500])
            image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nologo=true"

            output_dir = Path(settings.output_images_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{prefix}_{uuid.uuid4().hex[:8]}.jpg"
            filepath = output_dir / filename

            req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(filepath, "wb") as f:
                    f.write(resp.read())

            logger.info(f"Generated {prefix} image via Pollinations fallback: {filepath}")
            return json.dumps({
                "success": True,
                "image_path": str(filepath),
                "filename": filename,
                "url": f"/api/media/images/{filename}",
                "prompt_used": prompt[:200],
                "model": "pollinations-fallback",
                "note": "Generated successfully using the backup image pipeline.",
                "reference_portraits_used": len(reference_images) if reference_images else 0,
            })
        except Exception as fallback_e:
            logger.error(f"Fallback image generation also failed: {fallback_e}")
            return json.dumps({
                "success": False,
                "error": f"Both primary ({image_model}) and backup image generation failed: {e} / {fallback_e}",
            })
