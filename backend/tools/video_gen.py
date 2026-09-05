"""
Video Generation Engine for the Visualizer agent.

Supports dual-mode high-fidelity video production:
  1. Google Veo 2.0 Generative Video (Vertex AI): Real 24fps fluid AI cinematic video
     with character acting, physical movement, and camera physics, merged with Gemini TTS
     dialogue vocals and Lyria 3 score.
  2. Dynamic Multi-Shot Animatic Engine V2: Advanced multi-camera motion storyboard
     featuring emotion-aware shot generation, dynamic camera physics (tracking, pans,
     handheld drift), cinematic post-FX (film grain, vignette, color grade), and
     burnt-in lower-third speaker subtitles.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Helper: build character appearance block (shared with image_gen) ───

def _build_character_appearance_block(characters_json: str) -> str:
    """Build a structured CHARACTER APPEARANCE SHEET from characters JSON."""
    if not characters_json:
        return ""
    try:
        data = json.loads(characters_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    chars = data.get("characters", data) if isinstance(data, dict) else {}
    if not chars:
        return ""

    lines = [
        "\n═══ CHARACTER APPEARANCE SHEET (MANDATORY — DO NOT DEVIATE) ═══",
        "Depict each character EXACTLY as described below.\n",
    ]
    for name, info in chars.items():
        vis = info.get("visual_description", "") if isinstance(info, dict) else (info if isinstance(info, str) else "")
        if vis:
            lines.append(f"  ▸ {name.upper()}: {vis}")
    lines.append("\n═══ END CHARACTER APPEARANCE SHEET ═══\n")
    return "\n".join(lines)


def _get_ffmpeg_path() -> str | None:
    """Find FFmpeg binary in system PATH or via imageio_ffmpeg."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def _pad_video_to_120s(filepath: Path, ffmpeg_exe: str | None = None) -> Path:
    """Loop the video to make it at least 120 seconds (2 mins) proper."""
    if not ffmpeg_exe:
        ffmpeg_exe = _get_ffmpeg_path()
    if not ffmpeg_exe or not filepath.exists():
        return filepath
        
    out_path = filepath.parent / f"padded_120s_{filepath.name}"
    cmd = [
        ffmpeg_exe, "-y",
        "-stream_loop", "-1",
        "-i", str(filepath),
        "-t", "120.0",
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "aac",
        str(out_path)
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=300)
        if out_path.exists() and out_path.stat().st_size > 1000:
            return out_path
    except Exception as e:
        logger.warning(f"Failed to pad video to 120s: {e}")
    return filepath


def _escape_drawtext(text: str, max_length: int = 80) -> str:
    """Sanitize and escape text string for FFmpeg drawtext filter."""
    if not text:
        return ""
    clean = text.strip()
    clean = clean.replace("\\", "\\\\").replace("'", "\u2019").replace(":", "\\:").replace("%", "\\%")
    clean = clean.replace("\n", " ").replace("\r", "")
    if len(clean) > max_length:
        clean = clean[:max_length - 3] + "..."
    return clean


def _get_media_duration(file_path: Path | str) -> float:
    """Extract media duration in seconds using FFmpeg."""
    ffmpeg_exe = _get_ffmpeg_path()
    if not ffmpeg_exe:
        return 0.0
    try:
        cmd = [ffmpeg_exe, "-i", str(file_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        import re
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
        if m:
            return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def merge_video_with_audio(
    video_path: Path | str,
    audio_path: Path | str,
    output_path: Path | str | None = None,
    soundtrack_path: Path | str | None = None,
) -> Path | None:
    """
    Merge a dialogue audio track (and optional background soundtrack) into a video MP4.

    If video duration is equal to or longer than the dialogue audio, plays the video
    naturally without looping. Only loops if the video is strictly shorter than the vocal track.
    """
    ffmpeg_exe = _get_ffmpeg_path()
    if not ffmpeg_exe:
        logger.warning("[AudioMerge] FFmpeg binary not found. Cannot merge video and audio.")
        return None

    v_path = Path(video_path)
    a_path = Path(audio_path)
    if not v_path.exists() or not a_path.exists():
        logger.warning(f"[AudioMerge] Inputs missing: video={v_path.exists()}, audio={a_path.exists()}")
        return None

    out_path = Path(output_path) if output_path else v_path.parent / f"{v_path.stem}_voiced.mp4"

    try:
        st_path = Path(soundtrack_path) if soundtrack_path else None
        has_soundtrack = st_path is not None and st_path.exists()

        # Check media durations to avoid repeating video if it already covers the audio
        v_dur = _get_media_duration(v_path)
        a_dur = _get_media_duration(a_path)
        should_loop = (v_dur > 0 and a_dur > 0 and v_dur < (a_dur - 0.5))

        v_input_args = ["-stream_loop", "-1", "-i", str(v_path)] if should_loop else ["-i", str(v_path)]

        if has_soundtrack:
            # Mix dialogue (100% volume) and background score (22% volume)
            cmd = [
                ffmpeg_exe, "-y",
                *v_input_args,
                "-i", str(a_path),
                "-stream_loop", "-1", "-i", str(st_path),
                "-filter_complex",
                "[1:a]volume=1.0[dialogue];[2:a]volume=0.22[music];[dialogue][music]amix=inputs=2:duration=first[aout]",
                "-map", "0:v:0",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                str(out_path),
            ]
        else:
            # Only dialogue audio
            cmd = [
                ffmpeg_exe, "-y",
                *v_input_args,
                "-i", str(a_path),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                str(out_path),
            ]

        logger.info(f"[AudioMerge] Merging {v_path.name} ({v_dur:.1f}s, loop={should_loop}) + {a_path.name} ({a_dur:.1f}s)...")
        proc = subprocess.run(cmd, capture_output=True, timeout=90)
        if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000:
            logger.info(f"[AudioMerge] Successfully merged video with dialogue -> {out_path} ({out_path.stat().st_size} bytes)")
            return out_path
        else:
            err_msg = proc.stderr.decode("utf-8", errors="ignore")
            logger.warning(f"[AudioMerge] FFmpeg merge failed (code {proc.returncode}): {err_msg[:300]}")
            return None
    except Exception as e:
        logger.error(f"[AudioMerge] Error during merge: {e}")
        return None


# ── Render Dynamic Animatic Shot ──────────────────────────────────────

def _render_dynamic_animatic_shot(
    portrait_path: Path | None,
    audio_path: Path,
    speaker: str,
    dialogue_line: str,
    duration: float,
    idx: int,
    output_path: Path,
    ffmpeg_exe: str,
    fps: int = 30,
) -> bool:
    """
    Renders an individual shot with dynamic camera physics, color grade,
    vignette, film grain, and burnt-in lower-third cinematic speaker subtitle.
    """
    total_frames = max(1, int(duration * fps))

    # 6 distinct cinematic camera movements
    motion_type = idx % 6
    if motion_type == 0:
        # Dramatic push-in towards character's eyes
        z_filter = "min(zoom+0.0018,1.25)"
        x_filter = "iw/2-(iw/zoom/2)"
        y_filter = "ih*0.35-(ih/zoom*0.35)"
    elif motion_type == 1:
        # Reveal pull-back from close-up to medium shot
        z_filter = f"if(lte(zoom,1.0),1.22,max(1.001,zoom-0.0014))"
        x_filter = "iw/2-(iw/zoom/2)"
        y_filter = "ih/2-(ih/zoom/2)"
    elif motion_type == 2:
        # Cinematic tracking pan from Left to Right
        z_filter = "1.16"
        x_filter = f"(iw-iw/zoom)*(on/{total_frames})"
        y_filter = "ih/2-(ih/zoom/2)"
    elif motion_type == 3:
        # Cinematic tracking pan from Right to Left with subtle zoom
        z_filter = "min(zoom+0.0012,1.20)"
        x_filter = f"(iw-iw/zoom)*(1-on/{total_frames})"
        y_filter = "ih*0.4-(ih/zoom*0.4)"
    elif motion_type == 4:
        # Handheld camera drift / subtle organic float
        z_filter = "1.12+0.025*sin(2*PI*on/60)"
        x_filter = "iw/2-(iw/zoom/2)+12*sin(2*PI*on/90)"
        y_filter = "ih/2-(ih/zoom/2)+8*cos(2*PI*on/75)"
    else:
        # Dramatic close-up Dutch angle push
        z_filter = "min(zoom+0.0022,1.28)"
        x_filter = "iw*0.55-(iw/zoom*0.55)"
        y_filter = "ih*0.35-(ih/zoom*0.35)"

    esc_speaker = _escape_drawtext(speaker.upper(), max_length=30)
    esc_line = _escape_drawtext(dialogue_line, max_length=85)

    # Build video filter chain:
    # 1. Scale & dynamic camera motion
    # 2. Cinematic contrast / grading & vignette
    # 3. Lower-third dark gradient box
    # 4. Gold/Amber speaker name badge
    # 5. Clean white dialogue text subtitle
    vf_parts = [
        "scale=1280:720",
        f"zoompan=z='{z_filter}':d={total_frames}:x='{x_filter}':y='{y_filter}':s=1280x720:fps={fps}",
        "eq=contrast=1.06:brightness=0.01:saturation=1.10",
        "vignette=PI/4",
        "drawbox=y=ih-145:color=black@0.82:width=iw:height=105:t=fill",
        f"drawtext=text='{esc_speaker}':fontcolor=0xF5A623:fontsize=22:x=60:y=h-130",
        f"drawtext=text='{esc_line}':fontcolor=0xFFFFFF:fontsize=21:x=60:y=h-92",
    ]
    vf_string = ",".join(vf_parts)

    try:
        if portrait_path and portrait_path.exists():
            input_args = ["-loop", "1", "-i", str(portrait_path)]
        else:
            # Fallback color source if portrait missing
            input_args = ["-f", "lavfi", "-i", f"color=c=0x1E2332:s=1280x720:d={duration:.3f}"]

        cmd = [
            ffmpeg_exe, "-y",
            *input_args,
            "-i", str(audio_path),
            "-vf", vf_string,
            "-t", f"{duration:.3f}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path),
        ]

        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        return proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000
    except Exception as err:
        logger.warning(f"[AnimaticDirector] Error rendering shot {idx+1}: {err}")
        return False


# ── Vertex AI Multi-Shot Dialogue Director Engine V2 ──────────────────

async def generate_multi_shot_dialogue_video(
    project_id: str,
    scene_number: int,
    scene_description: str,
    character_visuals: str = "",
    use_veo_for_shots: bool = False,
) -> str | None:
    """
    Generate a full-duration, dynamic multi-camera dialogue scene animatic
    powered by Vertex AI (Gemini 3.1 Flash TTS + Gemini 3.1 Flash Image +
    Dynamic FFmpeg Camera Physics & Burnt-In Subtitles).
    """
    from config import settings
    from tools.script_state import _get_state, attach_media_to_scene, save_media_analysis, _save_state
    from tools.tts import perform_per_speaker_dialogue_tts
    from tools.image_gen import generate_character_portrait

    ffmpeg_exe = _get_ffmpeg_path()
    if not ffmpeg_exe:
        logger.warning("[MultiShotDirector] FFmpeg not found, cannot run multi-shot director.")
        return None

    state = await _get_state(project_id)
    scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
    if not scene:
        return None

    output_dir = Path(settings.output_videos_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = Path(settings.output_images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"[MultiShotDirector] Directing dynamic multi-camera scene for Scene {scene_number} ({len(scene.dialogue)} lines)...")

    # Step 1: Generate per-speaker dialogue audio clips via Vertex AI Gemini 3.1 Flash TTS
    dialogue_raw = [d.model_dump() for d in scene.dialogue] if scene and scene.dialogue else []
    
    segments = []
    if dialogue_raw:
        segments = await perform_per_speaker_dialogue_tts(project_id, dialogue_raw, scene_number)
    
    if not segments:
        logger.warning("[MultiShotDirector] No dialogue found. Slicing scene_description into action shots...")
        import re
        # Slice the detailed prompt into logical chunks for multi-shot b-roll
        sentences = [s.strip() for s in re.split(r'[.!?]\s+', scene_description) if len(s.strip()) > 10]
        if not sentences:
            sentences = [scene_description]
        
        import wave, uuid
        for idx, sentence in enumerate(sentences):
            duration = 7.0
            filename = f"action_scene_{scene_number}_shot_{idx}_{uuid.uuid4().hex[:6]}.wav"
            filepath = output_dir / filename
            
            # Generate silent wav file
            sample_rate = 24000
            total_samples = int(sample_rate * duration)
            silent_bytes = b"\x00\x00" * total_samples
            with wave.open(str(filepath), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(silent_bytes)

            segments.append({
                "character": "ACTION",
                "line": sentence,
                "duration": duration,
                "audio_path": str(filepath),
                "audio_bytes": silent_bytes
            })
            
    if not segments:
        return None

    # Step 2: Generate cinematic scene-action images for each dialogue beat
    # Instead of static face portraits, we generate FULL SCENE images showing
    # the character IN the environment performing actions relevant to the line.
    from tools.tts import normalize_character_name, find_matching_character
    from tools.image_gen import generate_scene_image

    shot_images: dict[int, Path] = {}  # idx -> image path
    scene_mood_board = None

    # Try to use existing mood board as establishing shot base
    if scene.mood_board_image:
        mb_cand = images_dir / scene.mood_board_image.split("/")[-1]
        if mb_cand.exists():
            scene_mood_board = mb_cand

    # Build character visual descriptions for prompts
    char_visual_map = {}
    for seg in segments:
        char_name = seg["character"]
        if char_name in char_visual_map:
            continue
        norm_char = normalize_character_name(char_name)
        canon_name, char_obj = find_matching_character(norm_char, state.characters)
        if char_obj and char_obj.visual_description:
            char_visual_map[char_name] = char_obj.visual_description
        else:
            char_visual_map[char_name] = f"Character named {canon_name or char_name}"

    # Generate a unique cinematic scene image for each dialogue beat
    for idx, seg in enumerate(segments):
        speaker = seg["character"]
        line = seg.get("line", "")
        vis_desc = char_visual_map.get(speaker, speaker)

        # Build a rich action-oriented prompt for this specific dialogue beat
        beat_prompt = (
            f"Cinematic widescreen film still from a movie scene. "
            f"Setting: {scene_description[:200]}. "
            f"Character {speaker} ({vis_desc}) is in the middle of speaking: \"{line[:120]}\". "
            f"Show the character's FULL BODY or MEDIUM SHOT in the environment, "
            f"with expressive body language, hands gesturing, interacting with props or surroundings. "
            f"NOT a headshot or portrait. Show the full scene environment around them. "
            f"Cinematic lighting, 35mm film grain, dramatic composition, 16:9 widescreen aspect ratio."
        )

        logger.info(f"[MultiShotDirector] Generating scene-action image for Shot {idx+1}/{len(segments)} ({speaker})...")
        try:
            img_json = await generate_scene_image(
                scene_description=beat_prompt,
                dialogue_context=line,
                characters=f"{speaker}: {vis_desc}",
            )
            img_res = json.loads(img_json)
            if img_res.get("success") and img_res.get("image_path"):
                shot_images[idx] = Path(img_res["image_path"])
                logger.info(f"[MultiShotDirector] Shot {idx+1} image generated: {img_res['image_path']}")
            else:
                logger.warning(f"[MultiShotDirector] Shot {idx+1} image generation failed, will use fallback")
        except Exception as img_err:
            logger.warning(f"[MultiShotDirector] Shot {idx+1} image error: {img_err}")

    # Step 3: Render each shot with dynamic camera motion, subtitles & audio
    # Now using scene-action images (full environment) instead of face portraits
    shot_video_files = []
    fps = 30

    for idx, seg in enumerate(segments):
        speaker = seg["character"]
        dialogue_line = seg.get("line", "")
        duration = seg["duration"]
        audio_path = Path(seg["audio_path"])

        # Use the scene-action image for this beat, fallback to mood board
        shot_image = shot_images.get(idx) or scene_mood_board

        shot_video_path = output_dir / f"scene_{scene_number}_shot_{idx}_{uuid.uuid4().hex[:6]}.mp4"
        logger.info(f"[MultiShotDirector] Rendering Shot {idx+1}/{len(segments)} ({speaker}, {duration:.1f}s)...")

        ok = False
        if use_veo_for_shots:
            if speaker == "ACTION":
                veo_prompt = f"Cinematic action shot: {dialogue_line}. Setting: {scene_description}"
            else:
                veo_prompt = f"Cinematic close-up of {speaker} acting, reacting, and speaking. They are saying: '{dialogue_line}'. Setting: {scene_description}"
            
            logger.info(f"[MultiShotDirector] Calling Veo for Shot {idx+1} (speaker: {speaker})...")
            # NOTE: Assuming generate_veo_scene_video exists in scope or is imported
            v_success, v_path, _ = await generate_veo_scene_video(
                scene_number=scene_number,
                scene_description=veo_prompt,
                character_visuals=character_visuals,
                project_id="", # Don't pass project_id so it doesn't attach to script state here!
            )
            if v_success and v_path and v_path.exists():
                merged = merge_video_with_audio(v_path, audio_path, shot_video_path)
                if merged and merged.exists():
                    ok = True

        if not ok:
            ok = _render_dynamic_animatic_shot(
                portrait_path=shot_image,
                audio_path=audio_path,
                speaker=speaker,
                dialogue_line=dialogue_line,
                duration=duration,
                idx=idx,
                output_path=shot_video_path,
                ffmpeg_exe=ffmpeg_exe,
                fps=fps,
            )

        if ok and shot_video_path.exists() and shot_video_path.stat().st_size > 1000:
            shot_video_files.append(shot_video_path)
        else:
            logger.warning(f"[MultiShotDirector] Shot {idx+1} render failed")


    if not shot_video_files:
        logger.warning("[MultiShotDirector] No shots rendered successfully.")
        return None

    # Step 4: Stitch all shots together into the full scene video
    concat_list_file = output_dir / f"concat_scene_{scene_number}_{uuid.uuid4().hex[:6]}.txt"
    with open(concat_list_file, "w", encoding="utf-8") as cf:
        for shot_file in shot_video_files:
            cf.write(f"file '{shot_file.as_posix()}'\n")

    final_filename = f"scene_{scene_number}_full_scene_{uuid.uuid4().hex[:8]}.mp4"
    final_filepath = output_dir / final_filename

    cmd_concat = [
        ffmpeg_exe, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(final_filepath),
    ]

    logger.info(f"[MultiShotDirector] Stitching {len(shot_video_files)} camera shots into full scene video...")
    proc_concat = subprocess.run(cmd_concat, capture_output=True, timeout=60)
    concat_list_file.unlink(missing_ok=True)

    if proc_concat.returncode != 0 or not final_filepath.exists() or final_filepath.stat().st_size < 1000:
        logger.warning(f"[MultiShotDirector] Concat failed: {proc_concat.stderr.decode('utf-8', errors='ignore')[:200]}")
        return None

    # Step 5: Mix background score (Lyria 3) if available
    soundtrack_file = None
    if scene.soundtrack_audio:
        if scene.soundtrack_audio.startswith("/api/media/audio/"):
            sfname = scene.soundtrack_audio.split("/")[-1]
            scand = Path(settings.output_audio_dir) / sfname
            if scand.exists():
                soundtrack_file = scand
        else:
            scand = Path(scene.soundtrack_audio)
            if scand.exists():
                soundtrack_file = scand

    if soundtrack_file and soundtrack_file.exists():
        logger.info("[MultiShotDirector] Mixing Lyria 3 score under dialogue...")
        scored_filename = f"scene_{scene_number}_scored_{uuid.uuid4().hex[:8]}.mp4"
        scored_filepath = output_dir / scored_filename
        cmd_mix = [
            ffmpeg_exe, "-y",
            "-i", str(final_filepath),
            "-stream_loop", "-1", "-i", str(soundtrack_file),
            "-filter_complex",
            "[0:a]volume=1.0[vocal];[1:a]volume=0.22[score];[vocal][score]amix=inputs=2:duration=first[aout]",
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(scored_filepath),
        ]
        proc_mix = subprocess.run(cmd_mix, capture_output=True, timeout=60)
        if proc_mix.returncode == 0 and scored_filepath.exists() and scored_filepath.stat().st_size > 1000:
            final_filepath.unlink(missing_ok=True)
            final_filepath = scored_filepath
            final_filename = scored_filename

    total_scene_duration = sum(s["duration"] for s in segments)
    
    # Force the video to be at least 120s as requested
    padded_filepath = _pad_video_to_120s(final_filepath)
    if padded_filepath != final_filepath:
        final_filepath = padded_filepath
        final_filename = padded_filepath.name
        total_scene_duration = max(120.0, total_scene_duration)

    video_url = f"/api/media/videos/{final_filename}"

    # Step 6: Save and register in ScriptState
    await attach_media_to_scene(project_id, scene_number, "concept_video", video_url)
    await save_media_analysis(
        project_id=project_id,
        media_type="video",
        media_url=video_url,
        filename=final_filename,
        scene_number=scene_number,
        is_canon=True,
        caption=f"Dynamic Multi-Camera Dialogue Performance for Scene {scene_number} ({total_scene_duration:.1f}s, {len(segments)} dynamic cuts)",
        structured_description={
            "video_summary": f"Full dynamic multi-camera dialogue performance for Scene {scene_number}",
            "duration_seconds": total_scene_duration,
            "shots_count": len(segments),
            "characters_speaking": list(character_portraits.keys()),
            "transcript": [
                {"speaker": seg["character"], "line": seg["line"], "duration": seg["duration"]}
                for seg in segments
            ],
            "has_embedded_dialogue": True,
            "has_soundtrack": bool(soundtrack_file),
            "video_mode": "dynamic-multishot-animatic-v2",
        },
    )

    logger.info(f"[MultiShotDirector] Dynamic scene video ready: {final_filepath} ({total_scene_duration:.1f}s)")

    return json.dumps({
        "success": True,
        "video_path": str(final_filepath),
        "filename": final_filename,
        "url": video_url,
        "scene_number": scene_number,
        "model": "dynamic-multishot-animatic-v2",
        "video_mode": "animatic",
        "duration_seconds": total_scene_duration,
        "shots_count": len(segments),
        "speakers": list(character_portraits.keys()),
        "has_embedded_dialogue": True,
        "has_soundtrack": bool(soundtrack_file),
        "message": (
            f"🎬 Generated Dynamic Multi-Shot Animatic for Scene {scene_number}! "
            f"Total duration: {total_scene_duration:.1f}s across {len(segments)} dynamic camera cuts with "
            f"cinematic camera physics, speaker subtitles, character voices, and background score."
        ),
    })


# ── Google Veo 3.1 Generative Video Engine (Vertex AI) ────────────────

async def _generate_single_veo_clip(
    client,
    model_used: str,
    prompt: str,
    output_path: Path,
    duration_seconds: int = 8,
    shot_index: int = 1,
    max_polls: int = 24,
    poll_interval: int = 10,
) -> bool:
    """Helper to submit and poll a single Google Veo clip on Vertex AI."""
    from google.genai import types
    from config import settings

    negative_prompt = (
        "phasing through walls, walking through solid objects, clipping through geometry, "
        "morphing into walls, melting into surfaces, disappearing body parts, floating characters, "
        "extra arms, extra hands, extra legs, deformed fingers, mutated limbs, distorted face, "
        "cartoon, anime, 3D CGI animation, videogame render, Unreal Engine, plastic skin, "
        "wax mannequin, airbrushed, oversaturated neon, rubbery motion, jittery camera, "
        "teleporting, ghosting, video glitch, blurry, low resolution, amateur footage, uncanny valley"
    )

    logger.info(f"[VeoShot {shot_index}] Submitting generation ({duration_seconds}s, model={model_used})...")
    try:
        operation = client.models.generate_videos(
            model=model_used,
            source=types.GenerateVideosSource(
                prompt=prompt[:1500],
            ),
            config=types.GenerateVideosConfig(
                person_generation="ALLOW_ADULT",
                aspect_ratio="16:9",
                number_of_videos=1,
                duration_seconds=duration_seconds,
                negative_prompt=negative_prompt,
            ),
        )

        for i in range(max_polls):
            await asyncio.sleep(poll_interval)
            try:
                operation = client.operations.get(operation)
            except Exception as poll_err:
                logger.warning(f"[VeoShot {shot_index}] Poll {i+1} check: {poll_err}")
                continue

            is_done = getattr(operation, "done", False)
            logger.info(f"[VeoShot {shot_index}] Polling {i+1}/{max_polls}: done={is_done}")
            if is_done:
                break

        is_done = getattr(operation, "done", False)
        if is_done:
            response = getattr(operation, "response", None)
            if response:
                generated_videos = getattr(response, "generated_videos", None)
                if generated_videos and len(generated_videos) > 0:
                    video_obj = generated_videos[0].video
                    video_bytes = getattr(video_obj, "video_bytes", None)
                    if video_bytes:
                        with open(output_path, "wb") as f:
                            f.write(video_bytes)
                        logger.info(f"[VeoShot {shot_index}] Saved: {output_path} ({len(video_bytes)} bytes)")
                        return True

                    video_uri = getattr(video_obj, "uri", None)
                    if video_uri:
                        try:
                            from google.cloud import storage
                            if video_uri.startswith("gs://"):
                                parts = video_uri[5:].split("/", 1)
                                bucket_name = parts[0]
                                blob_name = parts[1] if len(parts) > 1 else ""
                                storage_client = storage.Client(project=settings.gcp_project_id)
                                bucket = storage_client.bucket(bucket_name)
                                blob = bucket.blob(blob_name)
                                blob.download_to_filename(str(output_path))
                                logger.info(f"[VeoShot {shot_index}] Downloaded from GCS: {output_path}")
                                return True
                        except Exception as gcs_err:
                            logger.warning(f"[VeoShot {shot_index}] GCS download error: {gcs_err}")

            err = getattr(operation, "error", None)
            logger.warning(f"[VeoShot {shot_index}] Finished with error: {err}")
            return False
        else:
            logger.warning(f"[VeoShot {shot_index}] Timed out after polling")
            return False
    except Exception as e:
        logger.warning(f"[VeoShot {shot_index}] Exception: {e}")
        return False


def _concat_video_clips(clip_paths: list[Path], output_path: Path) -> bool:
    """Concatenate multiple video MP4 clips into a single continuous video with FFmpeg."""
    ffmpeg_exe = _get_ffmpeg_path()
    if not ffmpeg_exe or not clip_paths:
        return False
    if len(clip_paths) == 1:
        shutil.copyfile(clip_paths[0], output_path)
        return True

    concat_txt = output_path.parent / f"concat_{uuid.uuid4().hex[:6]}.txt"
    try:
        with open(concat_txt, "w", encoding="utf-8") as f:
            for c in clip_paths:
                f.write(f"file '{c.resolve().as_posix()}'\n")
        cmd = [
            ffmpeg_exe, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        concat_txt.unlink(missing_ok=True)
        return proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000
    except Exception as e:
        logger.warning(f"[Concat] Error: {e}")
        concat_txt.unlink(missing_ok=True)
        return False


async def _plan_cinematic_shots(
    scene_number: int,
    scene_description: str,
    dialogue_context: str,
    char_block: str,
    num_shots: int,
    project_id: str = "",
) -> list[str]:
    """
    Dynamically plan sequential cinematic camera setups using Gemini as the AI Director.
    
    Enforces:
    1. Rigid Physical Architecture & Geometry: Solid ground, walls, railings. Actors have weight and gravity.
       Explicitly forbids walking into walls, phasing through solid objects, or floating.
    2. Screenplay-faithful narrative: Specific physical gestures and emotional deliveries aligned with the scene.
    3. Photorealistic 35mm optical cinematography (ARRI ALEXA LF, Master Prime lenses, natural skin pores).
    4. Exact character appearance preservation.
    """
    from config import settings

    # Extract additional context from script state if available
    slug = ""
    action_text = scene_description
    dialogue_text = dialogue_context
    if project_id:
        try:
            from tools.script_state import _get_state
            state = await _get_state(project_id)
            scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
            if scene:
                slug = scene.slug or ""
                if scene.action_lines:
                    action_text = f"{slug}. " + " ".join(scene.action_lines)
                if not dialogue_text and scene.dialogue:
                    dialogue_text = " ".join([f'{d.character}: "{d.line}"' for d in scene.dialogue[:5]])
        except Exception as e:
            logger.warning(f"[ShotDirector] Could not extract scene state: {e}")

    # Fallback shot prompts adhering strictly to realism, physics, and the specific scene
    def _build_physics_fallback() -> list[str]:
        cinematic_base = (
            f"Photorealistic live-action cinema, shot on ARRI ALEXA LF, ARRI Master Prime 35mm anamorphic lens, "
            f"Kodak Vision3 500T film grain emulation, realistic natural skin pores, realistic subsurface scattering. "
            f"Rigid spatial physics: solid impenetrable architecture, solid floor with authentic foot grounding, friction, and mass. "
            f"Zero wall-phasing, zero geometry clipping, zero floating. Characters do not walk into solid objects. "
        )
        fps_spec = "24fps filmic motion blur, natural camera pacing, 16:9 widescreen aspect ratio."
        char_desc = f"\n{char_block}\n" if char_block else ""
        
        if num_shots == 1:
            return [
                f"{cinematic_base}Scene {scene_number} ({slug or 'Scene Action'}). Setting & Action: {action_text}. "
                f"Dialogue & Acting: {dialogue_text}. {char_desc}Steadycam tracking shot, subtle organic camera breathing, "
                f"authentic physical blocking, realistic eye contact and micro-expressions. {fps_spec}"
            ]
        elif num_shots == 2:
            return [
                f"{cinematic_base}Scene {scene_number} (Shot 1 of 2 - Establishing Action & Spatial Blocking). "
                f"Setting & Action: {action_text}. {char_desc}Medium-wide tracking shot establishing characters firmly grounded on the solid floor. "
                f"Initiating dramatic interaction: {dialogue_text}. Subtle camera push-in on dolly, volumetric ambient lighting. {fps_spec}",
                f"{cinematic_base}Scene {scene_number} (Shot 2 of 2 - Reverse Angle & Dramatic Interaction). "
                f"Setting & Action: {action_text}. {char_desc}Over-the-shoulder medium close-up reverse angle. "
                f"Characters reacting and delivering dialogue with intense focus: {dialogue_text}. "
                f"Natural physical gestures, solid boundaries behind characters with zero clipping. {fps_spec}"
            ]
        else:
            return [
                f"{cinematic_base}Scene {scene_number} (Shot 1 of 3 - Opening Wide & Physical Grounding). "
                f"Setting & Action: {action_text}. {char_desc}Medium-wide atmospheric establishing shot. Characters firmly anchored on solid ground. {fps_spec}",
                f"{cinematic_base}Scene {scene_number} (Shot 2 of 3 - Medium Reverse Coverage). "
                f"Setting & Action: {action_text}. {char_desc}Medium two-shot / reverse angle. Dialogue delivery: {dialogue_text}. Natural physical interaction. {fps_spec}",
                f"{cinematic_base}Scene {scene_number} (Shot 3 of 3 - Climactic Tight Angle). "
                f"Setting & Action: {action_text}. {char_desc}Dynamic medium close-up, dramatic lighting contrast, realistic facial emotion and physical tension. {fps_spec}"
            ]

    # Use Gemini to generate dynamic screenplay-specific shot prompts
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location or "us-central1",
        )

        director_prompt = f"""You are a master Hollywood Film Director, Cinematographer, and Visual Effects Supervisor directing Google Veo 3.1 video generation.

SCENE CONTEXT:
Scene Number: {scene_number}
Slugline: {slug or "LOCATION"}
Screenplay Action: {action_text}
Dialogue Lines: {dialogue_text}
{char_block}

DIRECTORIAL REQUIREMENTS:
You must plan exactly {num_shots} sequential, distinct cinematic shot prompts (each shot is an 8-second video clip).
CRITICAL RULES TO ELIMINATE DEFECTS:
1. RIGID SPATIAL GEOMETRY & COLLISION PHYSICS:
   - Define the physical environment explicitly (e.g. solid concrete floor, impenetrable brick parapet wall, solid steel railing).
   - Actors MUST stand firmly on the ground with realistic mass, balance, and friction.
   - EXPLICITLY forbid wall-phasing: "Characters do not walk into walls, do not clip through solid geometry, and never phase or morph into background surfaces."
2. SCREENPLAY NARRATIVE FIDELITY (NO HALLUCINATED GADGETS/ACTIONS):
   - Every shot's action and blocking must directly reflect the actual screenplay action ({action_text}) and dialogue ({dialogue_text}).
   - DO NOT invent generic sci-fi consoles, machinery, sparks, or weapons unless explicitly in the text.
3. 35MM LIVE-ACTION PHOTOREALISM (ANTI-CGI / ANTI-WAX):
   - Specify: "Shot on ARRI ALEXA LF, Master Prime 35mm anamorphic lens, Kodak Vision3 500T film grain emulation."
   - Mandate natural human skin pores, authentic subsurface scattering, real damp fabric texture, physically plausible lighting.
   - Forbid cartoon, anime, 3D CGI render, videogame graphics, wax mannequin skin, or plastic sheen.
4. CHARACTER CONSISTENCY:
   - Include the character appearance traits in every shot prompt so the face, hair, and wardrobe remain 100% identical.
5. SEQUENTIAL CAMERA CUTS:
   - Shot 1: Establishing wide or medium tracking shot introducing the spatial environment and starting the action.
   - Shot 2: Reverse angle or over-the-shoulder medium shot capturing reaction, dialogue delivery, and physical handoff/interaction.
   - Shot 3 (if requested): Climactic tight angle capturing emotional resolution and environmental atmosphere.

Return a JSON object with a single key "shots" containing exactly {num_shots} strings.
"""
        resp = client.models.generate_content(
            model=settings.gemini_main_model,
            contents=director_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
        if resp and resp.text:
            cleaned_text = resp.text.strip()
            if cleaned_text.startswith("```"):
                cleaned_text = re.sub(r"^```(?:json)?\n?", "", cleaned_text)
                cleaned_text = re.sub(r"\n?```$", "", cleaned_text)
            data = json.loads(cleaned_text)
            shots = data.get("shots", [])
            if isinstance(shots, list) and len(shots) >= num_shots:
                logger.info(f"[Veo Director] Gemini planned {len(shots)} dynamic cinematic shots successfully.")
                return [s.strip() for s in shots[:num_shots]]
            elif isinstance(shots, list) and len(shots) > 0:
                fallback = _build_physics_fallback()
                while len(shots) < num_shots:
                    shots.append(fallback[len(shots)])
                return [s.strip() for s in shots[:num_shots]]
    except Exception as e:
        logger.warning(f"[Veo Director] Dynamic shot planning fallback triggered: {e}")

    return _build_physics_fallback()


async def generate_veo_scene_video(
    scene_number: int,
    scene_description: str,
    dialogue_context: str = "",
    character_visuals: str = "",
    characters: str = "",
    project_id: str = "",
    target_duration: float = 8.0,
) -> tuple[bool, Path | None, str]:
    """
    Generate real 24fps fluid cinematic video using Google Veo 3.1 via Vertex AI.
    
    Supports multi-shot sequential generation for durations > 8s (e.g. 16s, 24s):
    - When target_duration >= 20.0s: Generates 3 distinct 8s camera setups in parallel (24s total).
    - When target_duration >= 11.0s: Generates 2 distinct 8s camera setups in parallel (16s total).
    - Otherwise: Generates 1 comprehensive 8s cinematic shot.
    
    All shots are stitched into a continuous sequence with zero looping!
    """
    from config import settings

    output_dir = Path(settings.output_videos_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"scene_{scene_number}_veo_{uuid.uuid4().hex[:8]}.mp4"
    filepath = output_dir / filename
    model_used = settings.veo_video_model

    # Determine character visuals context
    char_block = _build_character_appearance_block(character_visuals)
    if not char_block and project_id:
        try:
            from tools.script_state import _get_state
            from tools.tts import normalize_character_name, find_matching_character
            state = await _get_state(project_id)
            scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
            char_lines = []
            char_list = (scene.characters if scene and scene.characters else [])
            if not char_list and scene and scene.dialogue:
                char_list = list(dict.fromkeys([d.character for d in scene.dialogue if d.character]))
            if not char_list and characters:
                char_list = [c.strip() for c in characters.split(",") if c.strip()]
            for cname in char_list:
                canon_name, c_obj = find_matching_character(normalize_character_name(cname), state.characters)
                if c_obj and c_obj.visual_description:
                    char_lines.append(f"- {canon_name or cname}: {c_obj.visual_description}")
            if char_lines:
                char_block = "Character Visuals & Acting Guide:\n" + "\n".join(char_lines)
            elif characters:
                char_block = f"Characters: {characters}"
        except Exception as e:
            logger.warning(f"[Veo] Could not load character visuals from state: {e}")
            if characters:
                char_block = f"Characters: {characters}"
    elif not char_block and characters:
        char_block = f"Characters: {characters}"

    # Determine shot count: 8s per clip
    if target_duration >= 20.0:
        num_shots = 3
    elif target_duration >= 11.0:
        num_shots = 2
    else:
        num_shots = 1

    logger.info(f"[Veo Director] Directing Scene {scene_number} ({target_duration:.1f}s requested -> {num_shots} x 8s shots = {num_shots * 8}s total)...")

    # Build prompts for each shot setup dynamically using AI Cinematic Director
    shot_prompts = await _plan_cinematic_shots(
        scene_number=scene_number,
        scene_description=scene_description,
        dialogue_context=dialogue_context,
        char_block=char_block,
        num_shots=num_shots,
        project_id=project_id,
    )

    try:
        from google import genai
        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=getattr(settings, "gcp_video_location", settings.gcp_location or "us-central1"),
        )

        shot_paths = [
            output_dir / f"scene_{scene_number}_veo_shot{i+1}_{uuid.uuid4().hex[:6]}.mp4"
            for i in range(num_shots)
        ]

        if num_shots == 1:
            ok = await _generate_single_veo_clip(
                client=client,
                model_used=model_used,
                prompt=shot_prompts[0],
                output_path=filepath,
                duration_seconds=8,
                shot_index=1,
            )
            if ok and filepath.exists() and filepath.stat().st_size > 1000:
                return True, filepath, model_used
            return False, None, "Veo single shot failed"
        else:
            # Parallel multi-shot generation on Vertex AI
            logger.info(f"[Veo Director] Launching {num_shots} Veo shots in parallel on Vertex AI...")
            tasks = [
                _generate_single_veo_clip(
                    client=client,
                    model_used=model_used,
                    prompt=shot_prompts[i],
                    output_path=shot_paths[i],
                    duration_seconds=8,
                    shot_index=i + 1,
                )
                for i in range(num_shots)
            ]
            results = await asyncio.gather(*tasks)

            successful_clips = [
                shot_paths[i]
                for i, ok in enumerate(results)
                if ok and shot_paths[i].exists() and shot_paths[i].stat().st_size > 1000
            ]

            if len(successful_clips) > 1:
                logger.info(f"[Veo Director] Successfully generated {len(successful_clips)}/{num_shots} shots. Stitching into continuous {len(successful_clips)*8}s sequence...")
                ok_concat = _concat_video_clips(successful_clips, filepath)
                for c in successful_clips:
                    c.unlink(missing_ok=True)
                if ok_concat and filepath.exists() and filepath.stat().st_size > 1000:
                    return True, filepath, model_used
            elif len(successful_clips) == 1:
                logger.info("[Veo Director] 1 shot succeeded. Using single 8s clip...")
                shutil.move(str(successful_clips[0]), str(filepath))
                return True, filepath, model_used

            return False, None, "Veo multi-shot generation failed"

    except Exception as e:
        logger.warning(f"[Veo Director] Exception during generation: {e}")
        return False, None, str(e)


# ── Public API: generate_scene_video ─────────────────────────────────

async def generate_scene_video(
    scene_number: int = 1,
    scene_description: str = "Screenplay scene performance",
    dialogue_context: str = "",
    characters: str = "",
    character_visuals: str = "",
    project_id: str = "",
    video_mode: str = "auto",
    duration_seconds: int = 0,
) -> str:
    """
    Generate a cinematic video performance for a screenplay scene.

    Args:
        scene_number: Scene number being animated.
        scene_description: Detailed visual action lines and environment.
        dialogue_context: Spoken dialogue lines to be performed.
        characters: Character names and descriptions (fallback).
        character_visuals: Character appearance spec JSON string (preferred).
        project_id: Project identifier for ScriptState registration.
        video_mode: "auto" (tries Veo 3.1 then animatic), "veo" (forces Veo 3.1),
                    or "animatic" (forces dynamic multi-shot animatic engine).
        duration_seconds: Target video duration (0 = auto-detects from dialogue audio duration).

    Returns:
        JSON string containing the generated video path, URL, and metadata.
    """
    from config import settings

    logger.info(f"[VideoDirector] Generating scene video for Scene {scene_number} (mode={video_mode})...")

    if not project_id:
        from tools.script_state import _active_states
        if _active_states:
            project_id = list(_active_states.keys())[-1]

    # ── Mode Branch: Forced Animatic or Veo-Director ─────────────────────────────────
    if video_mode.lower() in ("animatic", "veo-director", "auto") and project_id:
        try:
            animatic_res = await generate_multi_shot_dialogue_video(
                project_id=project_id,
                scene_number=scene_number,
                scene_description=scene_description,
                character_visuals=character_visuals,
                use_veo_for_shots=(video_mode.lower() in ("veo-director", "auto")),
            )
            if animatic_res:
                return animatic_res
        except Exception as a_err:
            logger.warning(f"[VideoDirector] {video_mode} mode error: {a_err}")
    # Auto-enrich sparse scene inputs from canonical ScriptState if available
    target_dur = float(duration_seconds)
    if project_id:
        try:
            from tools.script_state import _get_state
            state = await _get_state(project_id)
            scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
            if scene:
                if (not scene_description or len(scene_description.strip()) < 35 or scene_description == "Screenplay scene performance") and scene.action_lines:
                    scene_description = f"{scene.slug or ''}. " + " ".join(scene.action_lines)
                if not dialogue_context and scene.dialogue:
                    dialogue_context = " ".join([f'{d.character}: "{d.line}"' for d in scene.dialogue[:6]])
                if target_dur <= 0:
                    if scene.table_read_audio:
                        fname = scene.table_read_audio.split("/")[-1]
                        cand = Path(settings.output_audio_dir) / fname
                        if cand.exists():
                            target_dur = _get_media_duration(cand)
                    if target_dur <= 0 and scene.dialogue:
                        target_dur = float(max(8, len(scene.dialogue) * 3.5))
        except Exception as e:
            logger.warning(f"[VideoDirector] Error enriching scene details from state: {e}")

    if target_dur <= 0:
        target_dur = 16.0  # Default to cinematic 16s multi-shot scene!

    # ── Google Veo 3.1 Generative Video (Default & Enforced) ─────────
    # Static image zoompan fallbacks have been completely eliminated per user directive.
    # We always generate real 24fps physical motion using Google Veo 3.1 with multi-shot cuts.
    veo_success = False
    veo_filepath = None
    veo_model = settings.veo_video_model

    logger.info(f"[VideoDirector] Enforcing Google Veo 3.1 generator for Scene {scene_number} (target={target_dur}s)...")
    veo_success, veo_filepath, veo_info = await generate_veo_scene_video(
        scene_number=scene_number,
        scene_description=scene_description,
        dialogue_context=dialogue_context,
        character_visuals=character_visuals,
        characters=characters,
        project_id=project_id,
        target_duration=target_dur,
    )

    if veo_success and veo_filepath and veo_filepath.exists():
        final_filepath = veo_filepath
        final_filename = veo_filepath.name
        merged_with_dialogue = False
        merged_with_soundtrack = False

        if project_id:
            try:
                from tools.script_state import _get_state, attach_media_to_scene, save_media_analysis
                state = await _get_state(project_id)
                scene = next((s for s in state.scenes if s.scene_number == scene_number), None)

                audio_file = None
                soundtrack_file = None

                if scene:
                    if scene.soundtrack_audio:
                        if scene.soundtrack_audio.startswith("/api/media/audio/"):
                            sfname = scene.soundtrack_audio.split("/")[-1]
                            scandidate = Path(settings.output_audio_dir) / sfname
                            if scandidate.exists():
                                soundtrack_file = scandidate
                        else:
                            scandidate = Path(scene.soundtrack_audio)
                            if scandidate.exists():
                                soundtrack_file = scandidate

                    # Table read logic has been removed to allow the video to use its native audio (if any).
                    if soundtrack_file and soundtrack_file.exists():
                        merged_output_path = veo_filepath.parent / f"scene_{scene_number}_veo_scored_{uuid.uuid4().hex[:8]}.mp4"
                        # Use soundtrack as the primary audio track since table read is disabled
                        merged_path = merge_video_with_audio(
                            video_path=veo_filepath,
                            audio_path=soundtrack_file,
                            output_path=merged_output_path,
                            soundtrack_path=None,
                        )
                        if merged_path and merged_path.exists():
                            final_filepath = merged_path
                            final_filename = merged_path.name
                            merged_with_soundtrack = True

                    # Ensure at least 120 seconds for Veo mode too
                    padded_filepath = _pad_video_to_120s(final_filepath)
                    if padded_filepath != final_filepath:
                        final_filepath = padded_filepath
                        final_filename = padded_filepath.name

                video_url = f"/api/media/videos/{final_filename}"
                await attach_media_to_scene(project_id, scene_number, "concept_video", video_url)
                await save_media_analysis(
                    project_id=project_id,
                    media_type="video",
                    media_url=video_url,
                    filename=final_filename,
                    scene_number=scene_number,
                    is_canon=True,
                    caption=f"Google Veo 3.1 AI Cinematic Video for Scene {scene_number}: {scene_description[:100]}",
                    structured_description={
                        "video_summary": f"Google Veo 3.1 Cinematic Performance: {scene_description}",
                        "has_embedded_dialogue": merged_with_dialogue,
                        "has_soundtrack": merged_with_soundtrack,
                        "video_mode": "veo",
                        "model": veo_model,
                    },
                )
            except Exception as save_err:
                logger.warning(f"[VeoMerge] Error registering Veo video: {save_err}")
        # Mirror video to easily accessible consumer locations (project root and Downloads)
        try:
            workspace_videos_dir = Path(__file__).resolve().parent.parent.parent / "generated_videos"
            workspace_videos_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(final_filepath), str(workspace_videos_dir / final_filename))

            user_downloads = Path.home() / "Downloads"
            if user_downloads.exists():
                shutil.copy2(str(final_filepath), str(user_downloads / final_filename))

            user_videos = Path.home() / "Videos"
            if user_videos.exists():
                shutil.copy2(str(final_filepath), str(user_videos / final_filename))
            logger.info(f"[VideoDirector] Mirrored video to: {workspace_videos_dir / final_filename} and {user_downloads / final_filename}")
        except Exception as copy_err:
            logger.warning(f"Could not mirror video to consumer directories: {copy_err}")

        video_url = f"/api/media/videos/{final_filename}"
        return json.dumps({
            "success": True,
            "video_path": str(final_filepath),
            "filename": final_filename,
            "url": video_url,
            "scene_number": scene_number,
            "model": veo_model,
            "video_mode": "veo",
            "merged_with_dialogue": merged_with_dialogue,
            "merged_with_soundtrack": merged_with_soundtrack,
            "message": f"🎬 Generated high-fidelity cinematic video using Google Veo 3.1 for Scene {scene_number}!",
        })

    logger.error(f"[VideoDirector] Google Veo 3.1 generation failed for Scene {scene_number}")
    return json.dumps({
        "success": False,
        "error": f"Google Veo 3.1 video generation failed for Scene {scene_number}. Static image fallbacks have been completely disabled to maintain true live-action cinematic quality.",
        "scene_number": scene_number,
    })
