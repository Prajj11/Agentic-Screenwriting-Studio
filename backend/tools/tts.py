"""
Gemini TTS wrapper tool for the Table-Read Agent.

Generates multi-speaker audio performances of screenplay scenes
using Gemini's TTS models with distinct voices per character.
"""

from __future__ import annotations

import json
import logging
import uuid
import wave
import io
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Available voices for character assignment
# These are the Gemini TTS voice options
AVAILABLE_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir",
    "Aoede", "Leda", "Orus", "Vale",
]

# Track voice assignments per project to keep consistent
_voice_assignments: dict[str, dict[str, str]] = {}  # project_id → {character → voice}


def _assign_voice(project_id: str, character_name: str) -> str:
    """Assign a consistent voice to a character."""
    if project_id not in _voice_assignments:
        _voice_assignments[project_id] = {}

    assignments = _voice_assignments[project_id]
    if character_name not in assignments:
        used_voices = set(assignments.values())
        available = [v for v in AVAILABLE_VOICES if v not in used_voices]
        voice = available[0] if available else AVAILABLE_VOICES[len(assignments) % len(AVAILABLE_VOICES)]
        assignments[character_name] = voice

    return assignments[character_name]


async def perform_table_read(project_id: str, scene_json: str) -> str:
    """
    Generate a multi-speaker audio performance of a scene's dialogue.
    
    The Gemini TTS API supports max 2 speakers per call, so for scenes
    with 3+ characters, we batch into dialogue pairs and stitch the audio.
    
    Args:
        project_id: The project ID for consistent voice assignments.
        scene_json: JSON object with 'dialogue' array of {character, line, parenthetical}.
    
    Returns:
        JSON with the audio file path and metadata.
    """
    from config import settings

    try:
        from google import genai
        from google.genai import types

        scene_data = json.loads(scene_json)
        dialogue = scene_data.get("dialogue", [])

        if not dialogue:
            return json.dumps({
                "success": False,
                "error": "No dialogue found in the scene.",
            })

        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location
        )

        # Assign voices to all characters
        characters = list(set(dl.get("character", "") for dl in dialogue))
        voice_map = {}
        for char in characters:
            voice_map[char] = _assign_voice(project_id, char)

        # Build the dialogue text with speaker labels
        dialogue_text = ""
        for dl in dialogue:
            char = dl.get("character", "UNKNOWN")
            line = dl.get("line", "")
            parenthetical = dl.get("parenthetical", "")
            if parenthetical:
                dialogue_text += f"{char} {parenthetical}: {line}\n"
            else:
                dialogue_text += f"{char}: {line}\n"

        # Generate TTS — handle 2-speaker limit
        unique_chars = list(set(dl.get("character", "") for dl in dialogue))
        all_audio_data = []

        if len(unique_chars) <= 2:
            # Simple case: 2 or fewer speakers, single API call
            speaker_configs = []
            for char in unique_chars:
                speaker_configs.append(
                    types.SpeakerVoiceConfig(
                        speaker=char,
                        voice_name=voice_map[char],
                    )
                )

            speech_config = types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=speaker_configs,
                )
            )

            response = client.models.generate_content(
                model=settings.gemini_tts_model,
                contents=dialogue_text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=speech_config,
                ),
            )

            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        all_audio_data.append(part.inline_data.data)

        else:
            # Complex case: 3+ speakers — batch into sequential 2-speaker chunks
            # Group dialogue into segments where max 2 speakers appear
            segments = _split_dialogue_for_tts(dialogue, voice_map)

            for segment in segments:
                seg_chars = list(set(dl["character"] for dl in segment["lines"]))
                speaker_configs = [
                    types.SpeakerVoiceConfig(
                        speaker=char,
                        voice_name=voice_map.get(char, AVAILABLE_VOICES[0]),
                    )
                    for char in seg_chars[:2]
                ]

                seg_text = ""
                for dl in segment["lines"]:
                    seg_text += f"{dl['character']}: {dl['line']}\n"

                speech_config = types.SpeechConfig(
                    multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                        speaker_voice_configs=speaker_configs,
                    )
                )

                try:
                    response = client.models.generate_content(
                        model=settings.gemini_tts_model,
                        contents=seg_text,
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=speech_config,
                        ),
                    )

                    if response.candidates and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, "inline_data") and part.inline_data:
                                all_audio_data.append(part.inline_data.data)
                except Exception as e:
                    logger.warning(f"TTS segment failed: {e}")

        if not all_audio_data:
            return json.dumps({
                "success": False,
                "error": "No audio was generated. The TTS API may have filtered the content.",
            })

        # Combine all audio segments and save
        output_dir = Path(settings.output_audio_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"tableread_{uuid.uuid4().hex[:8]}.wav"
        filepath = output_dir / filename

        combined = b"".join(all_audio_data)
        # Write as WAV (assuming 24kHz, 16-bit mono from Gemini TTS)
        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(24000)  # 24kHz
            wf.writeframes(combined)

        logger.info(f"Generated table read: {filepath}")

        return json.dumps({
            "success": True,
            "audio_path": str(filepath),
            "filename": filename,
            "url": f"/api/media/audio/{filename}",
            "voice_assignments": voice_map,
            "duration_estimate_seconds": len(combined) / (24000 * 2),  # bytes / (sample_rate * bytes_per_sample)
            "character_count": len(characters),
        })

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "google-genai SDK not installed. Run: pip install google-genai",
        })
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return json.dumps({
            "success": False,
            "error": str(e),
        })


def _split_dialogue_for_tts(
    dialogue: list[dict],
    voice_map: dict[str, str],
) -> list[dict]:
    """
    Split dialogue into segments where each segment has at most 2 unique speakers.
    This handles the Gemini TTS 2-speaker limit.
    """
    segments = []
    current_segment = {"lines": [], "speakers": set()}

    for dl in dialogue:
        char = dl.get("character", "UNKNOWN")

        if char in current_segment["speakers"] or len(current_segment["speakers"]) < 2:
            current_segment["lines"].append(dl)
            current_segment["speakers"].add(char)
        else:
            # New speaker would exceed 2 — start a new segment
            if current_segment["lines"]:
                segments.append(current_segment)
            current_segment = {"lines": [dl], "speakers": {char}}

    if current_segment["lines"]:
        segments.append(current_segment)

    return segments
