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
# These are the valid Gemini TTS voice options
AVAILABLE_VOICES = [
    "Aoede", "Charon", "Fenrir", "Kore", "Puck",
]

# Track voice assignments per project to keep consistent
_voice_assignments: dict[str, dict[str, str]] = {}  # project_id → {character → voice}


async def _assign_voice(project_id: str, character_name: str) -> str:
    """Assign a consistent voice to a character, prioritizing their Character Bible voice_notes."""
    if project_id not in _voice_assignments:
        _voice_assignments[project_id] = {}

    assignments = _voice_assignments[project_id]
    if character_name not in assignments:
        # First, try to get the voice from the character bible
        from tools.script_state import _get_state
        state = await _get_state(project_id)
        char = state.characters.get(character_name)
        
        chosen_voice = None
        if char and char.voice_notes:
            notes = char.voice_notes.lower()
            for v in AVAILABLE_VOICES:
                if v.lower() in notes:
                    chosen_voice = v
                    break

        # Fallback to a random unassigned voice
        if not chosen_voice:
            used_voices = set(assignments.values())
            available = [v for v in AVAILABLE_VOICES if v not in used_voices]
            chosen_voice = available[0] if available else AVAILABLE_VOICES[len(assignments) % len(AVAILABLE_VOICES)]
            
        assignments[character_name] = chosen_voice

    return assignments[character_name]


async def perform_per_speaker_dialogue_tts(
    project_id: str,
    dialogue: list[dict],
    scene_number: int = 1,
) -> list[dict]:
    """
    Generate distinct audio clips for each individual dialogue line using Gemini 3.1 Flash TTS.
    
    Returns a list of segment dicts:
      [
        {
          "character": "DR. JULIAN VANCE",
          "line": "Elena, do you know where you are?",
          "audio_path": "/path/to/tableread_scene_1_shot_0.wav",
          "audio_url": "/api/media/audio/tableread_scene_1_shot_0.wav",
          "duration": 3.5,
          "audio_bytes": b"..."
        },
        ...
      ]
    """
    from config import settings
    from google import genai
    from google.genai import types

    output_dir = Path(settings.output_audio_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location
    )

    # Assign consistent voices
    voice_map = {}
    for dl in dialogue:
        char = dl.get("character", "UNKNOWN")
        if char not in voice_map:
            voice_map[char] = await _assign_voice(project_id, char)

    segments = []
    for idx, dl in enumerate(dialogue):
        char = dl.get("character", "UNKNOWN")
        line = dl.get("line", "")
        parenthetical = dl.get("parenthetical", "")

        if not line:
            continue

        prompt_line = f"Perform with high emotion and dramatic acting. {char}"
        if parenthetical:
            prompt_line += f" ({parenthetical}): {line}"
        else:
            prompt_line += f": {line}"

        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_map.get(char, "Aoede"),
                )
            )
        )

        line_audio_bytes = None
        try:
            response = client.models.generate_content(
                model=settings.gemini_tts_model,
                contents=prompt_line,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=speech_config,
                ),
            )

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        line_audio_bytes = part.inline_data.data
                        break
        except Exception as tts_err:
            logger.warning(f"[TTS] Line {idx+1} generation error: {tts_err}")

        # Fallback synthetic sound if API filtered
        if not line_audio_bytes:
            # Generate 2.5s silent/ambient tone so timeline alignment doesn't break
            sample_rate = 24000
            duration = max(2.0, len(line.split()) * 0.35)
            total_samples = int(sample_rate * duration)
            line_audio_bytes = b"\x00\x00" * total_samples

        duration = max(1.5, len(line_audio_bytes) / (24000 * 2))
        filename = f"tableread_scene_{scene_number}_shot_{idx}_{uuid.uuid4().hex[:6]}.wav"
        filepath = output_dir / filename

        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(line_audio_bytes)

        segments.append({
            "character": char,
            "line": line,
            "parenthetical": parenthetical,
            "audio_path": str(filepath),
            "audio_url": f"/api/media/audio/{filename}",
            "duration": duration,
            "audio_bytes": line_audio_bytes,
        })
        logger.info(f"[TTS] Generated Shot {idx+1} for {char} ({duration:.1f}s): {filepath.name}")

    return segments


async def perform_table_read(project_id: str, scene_json: str) -> str:
    """
    Generate a multi-speaker audio performance of a scene's dialogue.
    
    Generates per-line character voice tracks using Gemini 3.1 Flash TTS,
    combines them into a master scene performance, and synchronizes with
    the scene video.
    
    Args:
        project_id: The project ID for consistent voice assignments.
        scene_json: JSON object with 'dialogue' array of {character, line, parenthetical}.
    
    Returns:
        JSON with the audio file path, per-line segments metadata, and master URL.
    """
    from config import settings

    try:
        scene_data = json.loads(scene_json)
        dialogue = scene_data.get("dialogue", [])
        scene_number = scene_data.get("scene_number", 1)

        if not dialogue:
            return json.dumps({
                "success": False,
                "error": "No dialogue found in the scene.",
            })

        # Generate individual speaker turns for shot-by-shot alignment
        segments = await perform_per_speaker_dialogue_tts(project_id, dialogue, scene_number)

        if not segments:
            return json.dumps({
                "success": False,
                "error": "No audio segments were generated.",
            })

        output_dir = Path(settings.output_audio_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"tableread_scene_{scene_number}_{uuid.uuid4().hex[:8]}.wav"
        filepath = output_dir / filename

        combined_bytes = b"".join(seg["audio_bytes"] for seg in segments)

        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(combined_bytes)

        total_duration = len(combined_bytes) / (24000 * 2)
        logger.info(f"Generated master table read: {filepath} ({total_duration:.1f}s across {len(segments)} lines)")

        # Unique voice assignments map
        voice_map = {}
        for s in segments:
            c = s["character"]
            if c not in voice_map:
                voice_map[c] = await _assign_voice(project_id, c)

        logger.info(f"Generated table read: {filepath}")

        # If this scene already has a concept video generated, auto-merge the new dialogue audio!
        scene_number = scene_data.get("scene_number")
        if scene_number and project_id:
            try:
                from tools.script_state import _get_state, attach_media_to_scene
                from tools.video_gen import merge_video_with_audio
                state = await _get_state(project_id)
                scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
                if scene and scene.concept_video:
                    v_fname = scene.concept_video.split("/")[-1]
                    v_path = Path(settings.output_videos_dir) / v_fname
                    if v_path.exists():
                        merged_v_path = Path(settings.output_videos_dir) / f"scene_{scene_number}_voiced_{uuid.uuid4().hex[:8]}.mp4"
                        
                        soundtrack_path = None
                        if scene.soundtrack_audio:
                            sfname = scene.soundtrack_audio.split("/")[-1]
                            scandidate = Path(settings.output_audio_dir) / sfname
                            if scandidate.exists():
                                soundtrack_path = scandidate

                        res_path = merge_video_with_audio(
                            video_path=v_path,
                            audio_path=filepath,
                            output_path=merged_v_path,
                            soundtrack_path=soundtrack_path,
                        )
                        if res_path and res_path.exists():
                            new_v_url = f"/api/media/videos/{res_path.name}"
                            await attach_media_to_scene(project_id, scene_number, "concept_video", new_v_url)
                            logger.info(f"[TTS] Automatically updated existing scene video with dialogue: {new_v_url}")
            except Exception as auto_v_err:
                logger.warning(f"[TTS] Auto-merge into existing video skipped: {auto_v_err}")

        return json.dumps({
            "success": True,
            "audio_path": str(filepath),
            "filename": filename,
            "url": f"/api/media/audio/{filename}",
            "voice_assignments": voice_map,
            "duration_estimate_seconds": total_duration,
            "character_count": len(voice_map),
            "segments_count": len(segments),
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
