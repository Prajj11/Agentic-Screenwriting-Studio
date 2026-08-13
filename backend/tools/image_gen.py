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
            vertexai=True,
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

        # Generate the image using gemini-3-pro-image and generate_content
        response = client.models.generate_content(
            model="gemini-3-pro-image",
            contents=prompt,
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
            ),
        )

        # Save the image
        output_dir = Path(settings.output_images_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"mood_{uuid.uuid4().hex[:8]}.jpg"
        filepath = output_dir / filename

        image_data = None
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
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
            reason = "Unknown"
            if response.candidates and response.candidates[0].finish_reason:
                reason = response.candidates[0].finish_reason
            return json.dumps({
                "success": False,
                "error": f"No image was generated. Finish reason: {reason}. The prompt may have been filtered.",
            })

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "google-genai SDK not installed. Run: pip install google-genai",
        })
    except Exception as e:
        logger.warning(f"Vertex AI Imagen failed ({e}). Falling back to Pollinations API...")
        import urllib.request
        import urllib.parse
        
        try:
            # Build the prompt
            fallback_prompt = f"Cinematic concept art for a screenplay scene: {scene_description}"
            if style_hints:
                fallback_prompt += f", {style_hints}"
            
            safe_prompt = urllib.parse.quote(fallback_prompt)
            image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nologo=true"
            
            output_dir = Path(settings.output_images_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = f"mood_{uuid.uuid4().hex[:8]}.jpg"
            filepath = output_dir / filename
            
            req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                with open(filepath, "wb") as f:
                    f.write(response.read())
                    
            logger.info(f"Generated fallback mood board via Pollinations: {filepath}")
            return json.dumps({
                "success": True,
                "image_path": str(filepath),
                "filename": filename,
                "url": f"/api/media/images/{filename}",
                "prompt_used": fallback_prompt[:200],
                "note": "Generated using fallback API"
            })
        except Exception as fallback_e:
            logger.error(f"Fallback Image generation error: {fallback_e}")
            return json.dumps({
                "success": False,
                "error": f"Both primary and fallback image generation failed: {fallback_e}",
            })
