"""
Gemini Image Generation tool for the Visualizer and Dialogue Specialist agents.

Uses Gemini's native image generation via `generate_content` with
`response_modalities=["IMAGE"]` — the approach from the Google Cloud
Platform notebook (intro_gemini_3_image_gen.ipynb).

This replaces the deprecated `generate_images` / Imagen 3 API.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


async def generate_mood_board(scene_description: str, style_hints: str = "") -> str:
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

    Returns:
        JSON with the generated image path and metadata.
    """
    from config import settings

    # Build the prompt
    prompt = f"Generate a cinematic concept art image for a screenplay scene:\n\n{scene_description}"
    if style_hints:
        prompt += f"\n\nVisual style: {style_hints}"
    prompt += (
        "\n\nStyle: photorealistic cinematic concept art, film production mood board, "
        "dramatic lighting, professional cinematography, widescreen composition"
    )

    return await _generate_image_with_gemini(prompt, prefix="mood", settings=settings)


async def generate_scene_image(
    scene_description: str,
    dialogue_context: str = "",
    characters: str = "",
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
        characters: Optional character descriptions for visual accuracy.
                   Example: "Sarah: tall, red hair, leather jacket. Mike: stocky, bald, suit."

    Returns:
        JSON with the generated image path and metadata.
    """
    from config import settings

    # Build a rich scene-specific prompt
    prompt = f"Generate a cinematic film still capturing this screenplay moment:\n\n"
    prompt += f"Scene: {scene_description}\n"
    if characters:
        prompt += f"\nCharacters: {characters}\n"
    if dialogue_context:
        prompt += f"\nMoment: {dialogue_context}\n"
    prompt += (
        "\nStyle: cinematic film still, dramatic composition, professional lighting, "
        "movie production quality, atmospheric, widescreen frame"
    )

    return await _generate_image_with_gemini(prompt, prefix="scene", settings=settings)


async def _generate_image_with_gemini(prompt: str, prefix: str, settings) -> str:
    """
    Core image generation using Gemini's generate_content with response_modalities=["IMAGE"].

    This follows the pattern from the Google Cloud Platform notebook:
    https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/getting-started/intro_gemini_3_image_gen.ipynb

    Uses client.models.generate_content() with GenerateContentConfig(response_modalities=["IMAGE"])
    instead of the deprecated client.models.generate_images().
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )

        response = client.models.generate_content(
            model="gemini-3-pro-image",
            contents=prompt,
            config=types.GenerateContentConfig(
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

        if response.candidates and response.candidates[0].content.parts:
            # The API returns inline_data for IMAGE modality
            img_data = response.candidates[0].content.parts[0].inline_data.data
            ext = "jpg"
            output_dir = Path(settings.output_images_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = output_dir / filename


            with open(filepath, "wb") as f:
                f.write(img_data)

            logger.info(f"Generated {prefix} image: {filepath}")
            return json.dumps({
                "success": True,
                "image_path": str(filepath),
                "filename": filename,
                "url": f"/api/media/images/{filename}",
                "prompt_used": prompt[:200],
                "model": settings.gemini_image_model,
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
        logger.error(f"Image generation error: {e}")
        
        # GRACEFUL FALLBACK: If the user's GCP project doesn't have Vertex AI image 
        # models enabled (which causes a 404 NOT_FOUND), we return a beautiful 
        # placeholder image so the Multimodal Scene Experience UI doesn't break.
        output_dir = Path(settings.output_images_dir)
        placeholder_path = output_dir / "placeholder.jpg"
        
        if placeholder_path.exists():
            logger.info("Using placeholder image fallback due to API error.")
            return json.dumps({
                "success": True,
                "image_path": str(placeholder_path),
                "filename": "placeholder.jpg",
                "url": "/api/media/images/placeholder.jpg",
                "prompt_used": prompt[:200] + " (FALLBACK APPLIED DUE TO API ERROR)",
                "model": settings.gemini_image_model,
                "warning": "The Google Cloud project did not have access to the image model. A placeholder was used."
            })
            
        return json.dumps({
            "success": False,
            "error": str(e),
        })
