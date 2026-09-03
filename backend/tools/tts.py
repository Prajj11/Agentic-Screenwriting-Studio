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

import re
from typing import Optional, Any, Tuple

# Available voices for character assignment
# Valid Gemini TTS voice options classified by voice characteristics
FEMALE_VOICES = ["Aoede", "Kore"]
MALE_VOICES = ["Charon", "Fenrir", "Puck"]
AVAILABLE_VOICES = FEMALE_VOICES + MALE_VOICES

# Track voice assignments per project in memory
_voice_assignments: dict[str, dict[str, str]] = {}  # project_id → {character → voice}


def normalize_character_name(name: str) -> str:
    """
    Normalizes a dialogue character name by removing parentheticals,
    voice-over notations, off-screen markers, and trailing numbers.
    E.g.:
      "OPERATIVE KAI (V.O.)" -> "OPERATIVE KAI"
      "ELENA (CONT'D)" -> "ELENA"
      "GUARD #1 (O.S.)" -> "GUARD #1"
      "ELENA VANCE" -> "ELENA VANCE"
    """
    if not name:
        return ""
    cleaned = re.sub(r"\s*\([^)]*\)", "", name).strip()
    return cleaned.upper()


def find_matching_character(cleaned_name: str, characters: dict[str, Any]) -> Tuple[Optional[str], Optional[Any]]:
    """
    Finds a Character object in the Character Bible using token matching.
    Returns (canon_name, Character).
    """
    if not cleaned_name or not characters:
        return None, None

    # 1. Exact match
    if cleaned_name in characters:
        return cleaned_name, characters[cleaned_name]

    # 2. Case-insensitive match
    for cname, cobj in characters.items():
        if cname.upper() == cleaned_name.upper():
            return cname, cobj

    # 3. Token containment (e.g. "ELENA" in "ELENA VANCE", or "KAI" in "OPERATIVE KAI")
    cleaned_tokens = set(re.findall(r"\w+", cleaned_name.upper()))
    for cname, cobj in characters.items():
        bible_tokens = set(re.findall(r"\w+", cname.upper()))
        if cleaned_tokens.issubset(bible_tokens) or bible_tokens.issubset(cleaned_tokens):
            return cname, cobj

    # 4. Substring match
    for cname, cobj in characters.items():
        if cleaned_name.upper() in cname.upper() or cname.upper() in cleaned_name.upper():
            return cname, cobj

    return None, None


def infer_character_gender(char_name: str, char_obj: Optional[Any] = None) -> str:
    """
    Infers gender ('female' or 'male') from Character Bible or name heuristics.
    """
    if char_obj:
        if getattr(char_obj, "gender", None):
            g = str(char_obj.gender).lower()
            if "fem" in g or "woman" in g or "girl" in g:
                return "female"
            if "male" in g or "man" in g or "boy" in g:
                return "male"

        text_corpus = " ".join([
            getattr(char_obj, "visual_description", "") or "",
            getattr(char_obj, "description", "") or "",
            getattr(char_obj, "voice_notes", "") or "",
            " ".join(getattr(char_obj, "traits", []) or []),
        ]).lower()

        female_signals = len(re.findall(r"\b(she|her|hers|woman|female|girl|mother|daughter|sister|heroine|lady|actress)\b", text_corpus))
        male_signals = len(re.findall(r"\b(he|him|his|man|male|guy|father|son|brother|hero|gentleman|operative|detective|actor)\b", text_corpus))

        if female_signals > male_signals:
            return "female"
        elif male_signals > female_signals:
            return "male"

    lower = char_name.lower()
    female_names = {"elena", "sarah", "mary", "anna", "kate", "lucy", "jane", "clara", "maria", "emma", "olivia", "eva", "sophia", "mia", "isabella", "woman", "girl"}
    male_names = {"kai", "john", "david", "silas", "mark", "james", "michael", "william", "alex", "robert", "thomas", "julian", "vance", "operator", "operative", "man", "guy"}

    tokens = set(re.findall(r"\w+", lower))
    if tokens & female_names:
        return "female"
    if tokens & male_names:
        return "male"

    return "male"


async def _assign_voice(project_id: str, character_name: str) -> str:
    """
    Assign a consistent, gender-appropriate voice to a character,
    prioritizing Character Bible voice notes, and persistently storing in SQLite.
    """
    norm_name = normalize_character_name(character_name)

    state = None
    if project_id:
        from tools.script_state import _get_state, _save_state
        try:
            state = await _get_state(project_id)
            if state.voice_assignments is None:
                state.voice_assignments = {}
        except Exception as e:
            logger.warning(f"[TTS] Could not load state for project {project_id}: {e}")

    # 1. Check persistent state voice assignments first
    if state and state.voice_assignments:
        if character_name in state.voice_assignments:
            return state.voice_assignments[character_name]
        if norm_name in state.voice_assignments:
            return state.voice_assignments[norm_name]

    # 2. Check in-memory fallback
    if project_id in _voice_assignments:
        if character_name in _voice_assignments[project_id]:
            return _voice_assignments[project_id][character_name]
        if norm_name in _voice_assignments[project_id]:
            return _voice_assignments[project_id][norm_name]
    else:
        _voice_assignments[project_id] = {}

    # 3. Match against Character Bible
    char_obj = None
    canon_name = None
    if state and state.characters:
        canon_name, char_obj = find_matching_character(norm_name, state.characters)
        if canon_name and canon_name in state.voice_assignments:
            voice = state.voice_assignments[canon_name]
            state.voice_assignments[character_name] = voice
            state.voice_assignments[norm_name] = voice
            _voice_assignments[project_id][character_name] = voice
            _voice_assignments[project_id][norm_name] = voice
            await _save_state(project_id)
            return voice

    # 4. Check explicit voice notes in bible
    chosen_voice = None
    if char_obj and char_obj.voice_notes:
        notes = char_obj.voice_notes.lower()
        for v in AVAILABLE_VOICES:
            if v.lower() in notes:
                chosen_voice = v
                break

    # 5. Determine gender and select appropriate voice pool
    gender = infer_character_gender(norm_name, char_obj)
    gender_pool = FEMALE_VOICES if gender == "female" else MALE_VOICES

    if not chosen_voice:
        used_voices = set()
        if state and state.voice_assignments:
            used_voices.update(state.voice_assignments.values())
        if project_id in _voice_assignments:
            used_voices.update(_voice_assignments[project_id].values())

        available_in_pool = [v for v in gender_pool if v not in used_voices]
        if available_in_pool:
            chosen_voice = available_in_pool[0]
        else:
            count_gender = sum(1 for v in used_voices if v in gender_pool)
            chosen_voice = gender_pool[count_gender % len(gender_pool)]

    # 6. Save and persist assignment
    if state:
        state.voice_assignments[character_name] = chosen_voice
        state.voice_assignments[norm_name] = chosen_voice
        if canon_name:
            state.voice_assignments[canon_name] = chosen_voice
        try:
            await _save_state(project_id)
        except Exception as se:
            logger.warning(f"[TTS] Failed to persist voice assignment to state: {se}")

    _voice_assignments[project_id][character_name] = chosen_voice
    _voice_assignments[project_id][norm_name] = chosen_voice
    if canon_name:
        _voice_assignments[project_id][canon_name] = chosen_voice

    logger.info(f"[TTS] Assigned voice '{chosen_voice}' ({gender}) to character '{character_name}' (canon: '{canon_name}')")
    return chosen_voice


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

        audio_url = f"/api/media/audio/{filename}"
        if project_id and scene_number:
            try:
                from tools.script_state import attach_media_to_scene
                await attach_media_to_scene(project_id, scene_number, "table_read_audio", audio_url)
            except Exception as att_err:
                logger.warning(f"[TTS] Could not attach table_read_audio to scene: {att_err}")

        return json.dumps({
            "success": True,
            "audio_path": str(filepath),
            "filename": filename,
            "url": audio_url,
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
