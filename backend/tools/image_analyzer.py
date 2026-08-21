"""
Gemini Multimodal Image Analyzer tool.

Analyzes uploaded reference images, storyboards, concept art, or character images
and extracts structured information (Setting, Environment, Characters, Action,
Mood, Lighting, Visual Details, Visible Text).

Based on the Google Cloud multimodal captioning & data curation reference:
https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/use-cases/multimodal-data-curation/captioning.ipynb
"""

from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


IMAGE_ANALYSIS_PROMPT = """Analyze this reference image for a film/screenplay production.
Provide a detailed, objective, and structured visual analysis.

Do NOT invent details that cannot reasonably be observed in the image.

Return your response strictly in the following JSON structure:
{
  "setting": "Description of the overarching setting/location",
  "environment": "Details about the environment, architecture, interior/exterior elements",
  "characters": "Description of visible characters, their appearance, clothing, approximate age, gender, positioning",
  "action": "What is happening visually in the frame",
  "mood": "Atmosphere and emotional tone conveyed by the image",
  "lighting": "Lighting setup, key/fill lights, shadows, color temperature, direction",
  "important_visual_details": "Distinctive props, composition features, camera angle, depth of field",
  "visible_text": "Any readable text, signs, logos, or writing visible in the image (or 'None')",
  "summary": "A concise 1-2 sentence summary of the image for screenplay reference"
}
"""


async def analyze_image(
    image_path: str,
    custom_prompt: str = "",
) -> str:
    """
    Analyze an image using Gemini multimodal vision and return a structured visual breakdown.

    Args:
        image_path: File path or relative URL to the image file.
        custom_prompt: Optional custom instructions or focus areas for the analysis.

    Returns:
        JSON string containing the structured image analysis.
    """
    try:
        # Resolve file path
        filepath = Path(image_path)
        if not filepath.is_absolute():
            if image_path.startswith("/api/media/"):
                filename = image_path.split("/")[-1]
                filepath = Path(settings.output_images_dir) / filename
                if not filepath.exists():
                    filepath = Path(settings.sqlite_db_path).parent / "uploads" / filename
            else:
                filepath = Path(settings.sqlite_db_path).parent / "uploads" / image_path

        if not filepath.exists():
            return json.dumps({
                "success": False,
                "error": f"Image file not found at path: {image_path}"
            })

        # Read image bytes & determine mime type
        img_bytes = filepath.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(filepath))
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/jpeg"

        # Initialize Gemini Client via Google GenAI SDK
        from google import genai
        from google.genai import types

        import os
        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0423661956"),
            location=settings.gcp_location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )

        model_name = settings.gemini_main_model or "gemini-2.5-flash"

        full_prompt = IMAGE_ANALYSIS_PROMPT
        if custom_prompt:
            full_prompt += f"\n\nAdditional Writer Focus / Questions:\n{custom_prompt}"

        contents = [
            types.Part.from_bytes(data=img_bytes, mime_type=mime_type),
            types.Part.from_text(text=full_prompt),
        ]

        logger.info(f"Running multimodal image analysis with model={model_name} on {filepath.name}")

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            )
        )

        raw_text = response.text or ""
        try:
            structured = json.loads(raw_text)
        except json.JSONDecodeError:
            # Fallback if raw text wasn't strict JSON
            structured = {
                "setting": "Observed image setting",
                "environment": "",
                "characters": "",
                "action": "",
                "mood": "",
                "lighting": "",
                "important_visual_details": "",
                "visible_text": "None",
                "summary": raw_text[:300]
            }

        return json.dumps({
            "success": True,
            "filename": filepath.name,
            "structured_description": structured,
            "summary": structured.get("summary", ""),
            "model_used": model_name,
        })

    except Exception as e:
        logger.error(f"Image analysis failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": f"Unable to analyze this image: {str(e)}",
            "technical_details": str(e),
        })
