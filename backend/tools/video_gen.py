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
    if not scene or not scene.dialogue:
        return None

    output_dir = Path(settings.output_videos_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = Path(settings.output_images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"[MultiShotDirector] Directing dynamic multi-camera scene for Scene {scene_number} ({len(scene.dialogue)} lines)...")

    # Step 1: Generate per-speaker dialogue audio clips via Vertex AI Gemini 3.1 Flash TTS
    dialogue_raw = [d.model_dump() for d in scene.dialogue]
    segments = await perform_per_speaker_dialogue_tts(project_id, dialogue_raw, scene_number)
    if not segments:
        logger.warning("[MultiShotDirector] No audio segments generated.")
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

    # Build prompts for each shot setup
    shot_prompts = []
    base_info = f"Cinematic photorealistic movie scene performance for Scene {scene_number}.\nSetting & Action: {scene_description}\n"
    if char_block:
        base_info += f"{char_block}\n"
    if dialogue_context:
        base_info += f"Performance & Acting: Characters speaking and emotionally reacting to the scene: {dialogue_context}\n"

    if num_shots == 1:
        shot_prompts.append(
            base_info +
            "Cinematography & Motion: Steadycam dynamic tracking shot, continuous physical movement, character gestures and interactions, natural kinetic blocking, rich facial micro-expressions, cinematic lighting, 24fps filmic motion blur, 16:9 widescreen aspect ratio."
        )
    elif num_shots == 2:
        shot_prompts.append(
            base_info +
            "Cinematography & Angle (Shot 1 of 2 - Establishing Action): Dynamic medium-wide establishing tracking shot. Characters active in foreground environment, starting physical action with tools/consoles, steadycam movement pushing in, atmospheric volumetric lighting, 24fps filmic motion blur, 16:9 widescreen."
        )
        shot_prompts.append(
            base_info +
            "Cinematography & Angle (Shot 2 of 2 - Reverse Angle & Progression): Over-the-shoulder medium reverse tracking shot focusing on reaction, counter-action, secondary character operating controls/weapons, emotional acting and physical intensity, dramatic contrast lighting, 24fps filmic motion blur, 16:9 widescreen."
        )
    else:
        shot_prompts.append(
            base_info +
            "Cinematography & Angle (Shot 1 of 3 - Opening Action): Medium-wide establishing tracking shot. High kinetic energy, physical setup in the environment, character operating tools/machinery, steadycam push-in, 24fps filmic motion blur, 16:9 widescreen."
        )
        shot_prompts.append(
            base_info +
            "Cinematography & Angle (Shot 2 of 3 - Reaction & Tension): Reverse angle medium shot. Emotional reaction, secondary character interacting with displays/communications, rising stakes, dramatic volumetric light, 24fps filmic motion blur, 16:9 widescreen."
        )
        shot_prompts.append(
            base_info +
            "Cinematography & Angle (Shot 3 of 3 - Climax Breakthrough): Low-angle dynamic close-up kinetic shot. High physical intensity, sparks/smoke, decisive action/breach, powerful facial micro-expressions, 24fps filmic motion blur, 16:9 widescreen."
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

    # Calculate target duration from audio if available
    target_dur = float(duration_seconds)
    if target_dur <= 0 and project_id:
        try:
            from tools.script_state import _get_state
            state = await _get_state(project_id)
            scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
            if scene and scene.table_read_audio:
                fname = scene.table_read_audio.split("/")[-1]
                cand = Path(settings.output_audio_dir) / fname
                if cand.exists():
                    target_dur = _get_media_duration(cand)
            if target_dur <= 0 and scene and scene.dialogue:
                target_dur = float(max(8, len(scene.dialogue) * 3.5))
        except Exception as e:
            logger.warning(f"[VideoDirector] Error calculating audio duration: {e}")
    if target_dur <= 0:
        target_dur = 16.0  # Default to cinematic 16s multi-shot scene!

    # ── Mode Branch: Forced Animatic ─────────────────────────────────
    if video_mode.lower() == "animatic" and project_id:
        try:
            animatic_res = await generate_multi_shot_dialogue_video(
                project_id=project_id,
                scene_number=scene_number,
                scene_description=scene_description,
                character_visuals=character_visuals,
            )
            if animatic_res:
                return animatic_res
        except Exception as a_err:
            logger.warning(f"[VideoDirector] Animatic mode error: {a_err}")

    # ── Mode Branch: Veo Generative Video ────────────────────────────
    veo_success = False
    veo_filepath = None
    veo_model = settings.veo_video_model

    if video_mode.lower() in ("veo", "auto"):
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
                        if scene.table_read_audio:
                            if scene.table_read_audio.startswith("/api/media/audio/"):
                                fname = scene.table_read_audio.split("/")[-1]
                                candidate = Path(settings.output_audio_dir) / fname
                                if candidate.exists():
                                    audio_file = candidate
                            else:
                                candidate = Path(scene.table_read_audio)
                                if candidate.exists():
                                    audio_file = candidate

                        # If no table read audio yet, generate on the fly
                        if not audio_file and scene.dialogue:
                            logger.info(f"[VeoMerge] Generating Table Read audio for Scene {scene_number}...")
                            from tools.tts import perform_table_read
                            dialogue_payload = json.dumps({
                                "scene_number": scene_number,
                                "dialogue": [d.model_dump() for d in scene.dialogue],
                            })
                            tts_res_json = await perform_table_read(project_id, dialogue_payload)
                            tts_res = json.loads(tts_res_json)
                            if tts_res.get("success") and tts_res.get("audio_path"):
                                audio_file = Path(tts_res["audio_path"])
                                if tts_res.get("url"):
                                    await attach_media_to_scene(project_id, scene_number, "table_read_audio", tts_res["url"])

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

                    if audio_file and audio_file.exists():
                        merged_output_path = veo_filepath.parent / f"scene_{scene_number}_veo_voiced_{uuid.uuid4().hex[:8]}.mp4"
                        merged_path = merge_video_with_audio(
                            video_path=veo_filepath,
                            audio_path=audio_file,
                            output_path=merged_output_path,
                            soundtrack_path=soundtrack_file,
                        )
                        if merged_path and merged_path.exists():
                            final_filepath = merged_path
                            final_filename = merged_path.name
                            merged_with_dialogue = True
                            if soundtrack_file:
                                merged_with_soundtrack = True

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

    # ── Fallback / Auto: Dynamic Multi-Shot Animatic V2 ───────────────

    if project_id:
        try:
            logger.info(f"[VideoDirector] Running Dynamic Multi-Shot Animatic Engine for Scene {scene_number}...")
            animatic_res = await generate_multi_shot_dialogue_video(
                project_id=project_id,
                scene_number=scene_number,
                scene_description=scene_description,
                character_visuals=character_visuals,
            )
            if animatic_res:
                return animatic_res
        except Exception as anim_err:
            logger.warning(f"[VideoDirector] Dynamic animatic pipeline encountered an issue: {anim_err}")

    # ── Final Standalone Fallback ─────────────────────────────────────
    output_dir = Path(settings.output_videos_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fallback_filename = f"scene_{scene_number}_video_{uuid.uuid4().hex[:8]}.mp4"
    fallback_filepath = output_dir / fallback_filename

    try:
        from tools.image_gen import generate_scene_image
        res_json = await generate_scene_image(
            scene_description=f"Cinematic keyframe shot: {scene_description}",
            dialogue_context=dialogue_context,
            characters=characters,
            character_visuals=character_visuals,
        )
        res = json.loads(res_json)
        frame_path = Path(res.get("image_path", "")) if res.get("success") else None

        ffmpeg_exe = _get_ffmpeg_path()
        if ffmpeg_exe and frame_path and frame_path.exists():
            cmd = [
                ffmpeg_exe, "-y",
                "-loop", "1", "-i", str(frame_path),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=24000",
                "-vf", "scale=1280:720,zoompan=z='min(zoom+0.0015,1.20)':d=150:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps=30,eq=contrast=1.06:saturation=1.10,vignette=PI/4",
                "-t", "5.0",
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                str(fallback_filepath),
            ]
            subprocess.run(cmd, capture_output=True, timeout=30)
            if fallback_filepath.exists() and fallback_filepath.stat().st_size > 1000:
                video_url = f"/api/media/videos/{fallback_filename}"
                return json.dumps({
                    "success": True,
                    "video_path": str(fallback_filepath),
                    "filename": fallback_filename,
                    "url": video_url,
                    "scene_number": scene_number,
                    "model": "cinematic-motion-keyframe",
                    "video_mode": "animatic",
                    "message": f"🎬 Generated cinematic motion keyframe video for Scene {scene_number}!",
                })
    except Exception as fb_err:
        logger.warning(f"[VideoDirector] Final fallback error: {fb_err}")

    return json.dumps({
        "success": False,
        "error": "Video generation could not complete. Please verify your video settings and try again.",
        "scene_number": scene_number,
    })
