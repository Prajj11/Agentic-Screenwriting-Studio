"""
Lyria 3 wrapper tool for generating music tracks and clips.
Generates full tracks or 30-second clips from text prompts or image inputs.
"""

from __future__ import annotations

import json
import logging
import uuid
import mimetypes
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

async def generate_music(prompt: str, is_clip: bool = False, image_path: Optional[str] = None) -> str:
    """
    Generate a music track or clip from a text prompt and optional image.
    
    Args:
        prompt: Description of the music (genre, tempo, style, vocals, lyrics).
        is_clip: If True, generates a 30-second clip instead of a full track.
        image_path: Optional path to an image for generating music from image.
    
    Returns:
        JSON string with audio path and metadata.
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
        
        model_id = settings.lyria_music_clip_model if (is_clip or image_path) else settings.lyria_music_model
        
        contents = []
        if image_path:
            import os
            if not os.path.exists(image_path):
                return json.dumps({
                    "success": False, 
                    "error": f"Image path not found: {image_path}"
                })
            
            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type:
                mime_type = "image/png"
                
            with open(image_path, "rb") as f:
                image_bytes = f.read()
                
            contents.append(types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type,
            ))
            
        contents.append(prompt)
        
        response = client.models.generate_content(
            model=model_id,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO", "TEXT"]
            )
        )
        
        audio_data = None
        lyrics_or_text = ""
        mime_type_from_response = "audio/mp3"  # default
        
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if getattr(part, "thought", None):
                    continue
                if part.text:
                    lyrics_or_text += part.text + "\n"
                if part.inline_data:
                    audio_data = part.inline_data.data
                    if part.inline_data.mime_type:
                        mime_type_from_response = part.inline_data.mime_type

        if audio_data:
            output_dir = Path(settings.output_audio_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Determine extension
            ext = ".mp3"
            if "wav" in mime_type_from_response.lower():
                ext = ".wav"
            elif "ogg" in mime_type_from_response.lower():
                ext = ".ogg"
            elif "m4a" in mime_type_from_response.lower():
                ext = ".m4a"
            
            filename = f"music_{uuid.uuid4().hex[:8]}{ext}"
            filepath = output_dir / filename
            
            with open(filepath, "wb") as f:
                f.write(audio_data)
                
            logger.info(f"Generated music track: {filepath}")
            return json.dumps({
                "success": True,
                "audio_path": str(filepath),
                "filename": filename,
                "url": f"/api/media/audio/{filename}",
                "text_output": lyrics_or_text.strip(),
                "is_clip": bool(is_clip or image_path)
            })
        else:
            return json.dumps({
                "success": False,
                "error": "No audio was generated.",
                "text_output": lyrics_or_text.strip()
            })
            
    except ImportError:
        return json.dumps({
            "success": False,
            "error": "google-genai SDK not installed. Run: pip install google-genai"
        })
    except Exception as e:
        logger.error(f"Music generation error: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })
