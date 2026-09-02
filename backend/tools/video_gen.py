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


def merge_video_with_audio(
    video_path: Path | str,
    audio_path: Path | str,
    output_path: Path | str | None = None,
    soundtrack_path: Path | str | None = None,
) -> Path | None:
    """
    Merge a dialogue audio track (and optional background soundtrack) into a video MP4.

    If the video clip is shorter than the dialogue audio, the video loops smoothly
    using `-stream_loop -1` so the entire vocal performance is played over the video.
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

        if has_soundtrack:
            # Mix dialogue (100% volume) and background score (22% volume)
            cmd = [
                ffmpeg_exe, "-y",
                "-stream_loop", "-1", "-i", str(v_path),
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
                "-stream_loop", "-1", "-i", str(v_path),
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

        logger.info(f"[AudioMerge] Running FFmpeg audio-video merge on {v_path.name} + {a_path.name}...")
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
        "drawbox=y=ih-115:color=black@0.78:width=iw:height=115:t=fill",
        f"drawtext=text='{esc_speaker}':fontcolor=0xF5A623:fontsize=22:x=60:y=h-98",
        f"drawtext=text='{esc_line}':fontcolor=0xFFFFFF:fontsize=20:x=60:y=h-58",
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

    # Step 2: Ensure all speaking characters have canonical portraits
    character_portraits = {}
    for seg in segments:
        char_name = seg["character"]
        if char_name in character_portraits:
            continue

        char_obj = state.characters.get(char_name)
        portrait_file = None

        # Check existing portrait
        if char_obj and char_obj.reference_portrait:
            if char_obj.reference_portrait.startswith("/api/media/images/"):
                p_cand = images_dir / char_obj.reference_portrait.split("/")[-1]
                if p_cand.exists():
                    portrait_file = p_cand
            else:
                p_cand = Path(char_obj.reference_portrait)
                if p_cand.exists():
                    portrait_file = p_cand

        # Generate portrait via Gemini Image if missing
        if not portrait_file:
            logger.info(f"[MultiShotDirector] Generating canonical reference portrait for '{char_name}'...")
            vis_desc = char_obj.visual_description if (char_obj and char_obj.visual_description) else f"Actor portraying {char_name} in scene {scene_description[:100]}"
            port_json = await generate_character_portrait(char_name, vis_desc)
            port_res = json.loads(port_json)
            if port_res.get("success") and port_res.get("image_path"):
                portrait_file = Path(port_res["image_path"])
                if char_obj:
                    char_obj.reference_portrait = port_res.get("url")
                    await _save_state(project_id)

        # Fallback to scene mood board if character portrait couldn't be generated
        if not portrait_file and scene.mood_board_image:
            mb_cand = images_dir / scene.mood_board_image.split("/")[-1]
            if mb_cand.exists():
                portrait_file = mb_cand

        if portrait_file:
            character_portraits[char_name] = portrait_file

    # Step 3: Render each speaker shot with dynamic camera motion, subtitles & audio
    shot_video_files = []
    fps = 30

    for idx, seg in enumerate(segments):
        speaker = seg["character"]
        dialogue_line = seg.get("line", "")
        duration = seg["duration"]
        audio_path = Path(seg["audio_path"])
        portrait_path = character_portraits.get(speaker)

        shot_video_path = output_dir / f"scene_{scene_number}_shot_{idx}_{uuid.uuid4().hex[:6]}.mp4"
        logger.info(f"[MultiShotDirector] Rendering Shot {idx+1}/{len(segments)} ({speaker}, {duration:.1f}s)...")

        ok = _render_dynamic_animatic_shot(
            portrait_path=portrait_path,
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


# ── Google Veo 2.0 Generative Video Engine (Vertex AI) ────────────────

async def generate_veo_scene_video(
    scene_number: int,
    scene_description: str,
    dialogue_context: str = "",
    character_visuals: str = "",
    characters: str = "",
    project_id: str = "",
) -> tuple[bool, Path | None, str]:
    """
    Generate real 24fps fluid cinematic video using Google Veo 2.0 via Vertex AI.
    Returns (success, filepath, error_or_model_name).
    """
    from config import settings

    output_dir = Path(settings.output_videos_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"scene_{scene_number}_veo_{uuid.uuid4().hex[:8]}.mp4"
    filepath = output_dir / filename
    model_used = settings.veo_video_model

    # Build prompt
    prompt_parts = [
        f"Cinematic photorealistic movie scene performance for Scene {scene_number}.",
        f"Setting & Action: {scene_description}",
    ]

    appearance_block = _build_character_appearance_block(character_visuals)
    if appearance_block:
        prompt_parts.append(appearance_block)
    elif characters:
        prompt_parts.append(f"Characters: {characters}")

    if dialogue_context:
        prompt_parts.append(f"Performance & Acting: Characters speaking and emotionally reacting to the scene: {dialogue_context}")

    prompt_parts.append(
        "Style: photorealistic 35mm film, 24fps smooth motion, natural character acting, dramatic lighting, "
        "fluid camera pan, cinematic depth of field, 16:9 widescreen movie production quality."
    )

    prompt = "\n".join(prompt_parts)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=getattr(settings, "gcp_video_location", settings.gcp_location or "us-central1"),
        )

        logger.info(f"[Veo 2.0] Initiating generative video generation for Scene {scene_number} with model={model_used}...")

        operation = client.models.generate_videos(
            model=model_used,
            source=types.GenerateVideosSource(
                prompt=prompt[:1500],
            ),
            config=types.GenerateVideosConfig(
                person_generation="ALLOW_ADULT",
                aspect_ratio="16:9",
                number_of_videos=1,
                duration_seconds=6,
            ),
        )

        logger.info("[Veo 2.0] Operation submitted. Polling for completion...")

        max_polls = 14
        poll_interval = 15
        for i in range(max_polls):
            await asyncio.sleep(poll_interval)
            try:
                operation = client.operations.get(operation)
            except Exception as poll_err:
                logger.warning(f"[Veo 2.0] Poll {i+1} check: {poll_err}")
                continue

            is_done = getattr(operation, "done", False)
            logger.info(f"[Veo 2.0] Polling {i+1}/{max_polls}: done={is_done}")
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
                        with open(filepath, "wb") as f:
                            f.write(video_bytes)
                        logger.info(f"[Veo 2.0] Video successfully generated and saved: {filepath} ({len(video_bytes)} bytes)")
                        return True, filepath, model_used

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
                                blob.download_to_filename(str(filepath))
                                logger.info(f"[Veo 2.0] Downloaded generated video from GCS: {filepath}")
                                return True, filepath, model_used
                        except Exception as gcs_err:
                            logger.warning(f"[Veo 2.0] GCS download error: {gcs_err}")

            err = getattr(operation, "error", None)
            return False, None, f"Veo operation finished with error: {err}"
        else:
            return False, None, "Veo operation timed out after polling window"

    except Exception as e:
        logger.warning(f"[Veo 2.0] Video generation request failed: {type(e).__name__}: {e}")
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
        video_mode: "auto" (tries Veo 2.0 then animatic), "veo" (forces Veo 2.0),
                    or "animatic" (forces dynamic multi-shot animatic engine).

    Returns:
        JSON string containing the generated video path, URL, and metadata.
    """
    from config import settings

    logger.info(f"[VideoDirector] Generating scene video for Scene {scene_number} (mode={video_mode})...")

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

    # ── Mode Branch: Veo 2.0 Generative Video ────────────────────────
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
        )

        if veo_success and veo_filepath and veo_filepath.exists():
            # If scene has dialogue audio or table read audio, merge it!
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
                            dialogue_payload = json.dumps({"dialogue": [d.model_dump() for d in scene.dialogue]})
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
                        caption=f"Google Veo 2.0 AI Cinematic Video for Scene {scene_number}: {scene_description[:100]}",
                        structured_description={
                            "video_summary": f"Google Veo 2.0 Cinematic Performance: {scene_description}",
                            "has_embedded_dialogue": merged_with_dialogue,
                            "has_soundtrack": merged_with_soundtrack,
                            "video_mode": "veo-2.0",
                        },
                    )

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
                        "message": f"🎬 Generated high-fidelity cinematic video using Google Veo 2.0 for Scene {scene_number}!",
                    })

                except Exception as save_err:
                    logger.warning(f"[VeoMerge] Error registering Veo video: {save_err}")

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
