"""
Gemini Multimodal Video Analyzer tool.

Analyzes uploaded reference videos, extract spoken dialogue transcript with timestamps
and speaker identification, visual events timeline, and overall scene/environment details.

Based on the Google Cloud multimodal video transcription reference:
https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/use-cases/video-analysis/multimodal_video_transcription.ipynb
"""

from __future__ import annotations

import json
import logging
import mimetypes
import time
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


VIDEO_ANALYSIS_PROMPT = """You are a professional film/video analysis AI assistant.
Analyze this video clip thoroughly for a screenplay production workflow.

Provide:
1. A overall VIDEO SUMMARY.
2. A complete spoken TRANSCRIPT broken into timestamped chunks with speaker labels (e.g. 'Speaker 1', 'Speaker 2', or character names if stated).
   - If speaker identity cannot be determined, use 'Speaker 1', 'Speaker 2', etc. Do NOT guess specific character names unless explicitly spoken or identified.
3. A VISUAL EVENTS timeline with timestamps describing key visual actions, camera movements, entry/exits, and environment changes.

Return your analysis strictly in the following JSON structure:
{
  "video_summary": "Concise 2-3 sentence overview of the clip's story, setting, and contents",
  "transcript": [
    {
      "timestamp": "00:00–00:08",
      "speaker": "Speaker 1",
      "dialogue": "Transcribed spoken text here"
    }
  ],
  "visual_events": [
    {
      "timestamp": "00:03",
      "description": "Visual event description, camera movement, character action"
    }
  ],
  "environmental_details": "Description of lighting, setting, sound design notes, or location details observed in video"
}
"""


async def analyze_video(
    video_path: str,
    custom_prompt: str = "",
) -> str:
    """
    Analyze a video using Gemini multimodal video understanding.

    Extracts transcript with timestamps and speakers, visual events timeline,
    and scene details.

    Args:
        video_path: File path or relative URL to the video file.
        custom_prompt: Optional specific questions or focus for the video analysis.

    Returns:
        JSON string containing the structured video analysis.
    """
    try:
        # Resolve file path
        filepath = Path(video_path)
        if not filepath.is_absolute():
            if video_path.startswith("/api/media/"):
                filename = video_path.split("/")[-1]
                filepath = Path(settings.output_images_dir).parent / "videos" / filename
                if not filepath.exists():
                    filepath = Path(settings.sqlite_db_path).parent / "uploads" / filename
            else:
                filepath = Path(settings.sqlite_db_path).parent / "uploads" / video_path

        if not filepath.exists():
            return json.dumps({
                "success": False,
                "error": f"Video file not found at path: {video_path}"
            })

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

        # Determine video mime type
        mime_type, _ = mimetypes.guess_type(str(filepath))
        if not mime_type or not mime_type.startswith("video/"):
            mime_type = "video/mp4"

        logger.info(f"Uploading video for Gemini multimodal analysis: {filepath.name}")

        uploaded_file = None
        contents = []

        try:
            # Attempt uploading via File API (recommended for video)
            uploaded_file = client.files.upload(file=filepath)
            
            # Wait for file processing if needed
            max_wait = 120
            elapsed = 0
            while hasattr(uploaded_file, "state") and getattr(uploaded_file.state, "name", "") == "PROCESSING":
                if elapsed >= max_wait:
                    break
                time.sleep(3)
                elapsed += 3
                uploaded_file = client.files.get(name=uploaded_file.name)

            contents.append(uploaded_file)
        except Exception as upload_err:
            logger.warning(f"Files API upload failed ({upload_err}), reading video bytes directly...")
            video_bytes = filepath.read_bytes()
            contents.append(types.Part.from_bytes(data=video_bytes, mime_type=mime_type))

        full_prompt = VIDEO_ANALYSIS_PROMPT
        if custom_prompt:
            full_prompt += f"\n\nSpecific Filmmaker Focus:\n{custom_prompt}"

        contents.append(types.Part.from_text(text=full_prompt))

        logger.info(f"Executing video analysis with model={model_name}...")

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            )
        )

        # Cleanup uploaded file if created
        if uploaded_file and hasattr(uploaded_file, "name"):
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

        raw_text = response.text or ""
        try:
            structured = json.loads(raw_text)
        except json.JSONDecodeError:
            structured = {
                "video_summary": raw_text[:300],
                "transcript": [],
                "visual_events": [],
                "environmental_details": ""
            }

        return json.dumps({
            "success": True,
            "filename": filepath.name,
            "structured_description": structured,
            "summary": structured.get("video_summary", ""),
            "transcript": structured.get("transcript", []),
            "visual_events": structured.get("visual_events", []),
            "model_used": model_name,
        })

    except Exception as e:
        logger.error(f"Video analysis failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": f"Unable to analyze this video: {str(e)}",
            "technical_details": str(e),
        })
