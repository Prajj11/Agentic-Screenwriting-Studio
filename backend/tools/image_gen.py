"""
Imagen 3 wrapper tool for the Visualizer Agent.

Generates concept art / mood board images from scene descriptions
using Google's Imagen 3 image generation model.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


async def generate_mood_board(scene_description: str, style_hints: str = "") -> str:
    """
    Generate a concept art / mood board image for a scene.
    
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

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            enterprise=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location
        )

        # Build the prompt
        prompt = f"Cinematic concept art for a screenplay scene: {scene_description}"
        if style_hints:
            prompt += f"\nVisual style: {style_hints}"
        prompt += (
            "\nStyle: photorealistic cinematic concept art, film production mood board, "
            "dramatic lighting, professional cinematography, widescreen aspect ratio"
        )

        # Generate the image
        response = client.models.generate_content(
            model=settings.gemini_image_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                image_config=types.ImageConfig(
                    aspect_ratio="16:9",
                ),
            ),
        )

        # Save the image
        output_dir = Path(settings.output_images_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"mood_{uuid.uuid4().hex[:8]}.jpg"
        filepath = output_dir / filename

        image_data = None
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if getattr(part, "thought", None):
                    continue
                if part.inline_data:
                    image_data = part.inline_data.data
                    break

        if image_data:
            with open(filepath, "wb") as f:
                f.write(image_data)

            logger.info(f"Generated mood board: {filepath}")
            return json.dumps({
                "success": True,
                "image_path": str(filepath),
                "filename": filename,
                "url": f"/api/media/images/{filename}",
                "prompt_used": prompt[:200],
            })
        else:
            return json.dumps({
                "success": False,
                "error": "No image was generated. The prompt may have been filtered.",
            })

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "google-genai SDK not installed. Run: pip install google-genai",
        })
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return json.dumps({
            "success": False,
            "error": str(e),
        })
