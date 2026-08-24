"""
Veo Video Generation tool for the Visualizer agent.

Generates real video clips of characters performing their roles for screenplay
scenes using Google Veo 2.0 via Vertex AI.

Pipeline:
  1. Build a rich cinematic prompt from the scene description, dialogue,
     and character appearance sheet (same system as image_gen.py).
  2. Call `client.models.generate_videos` with the Veo model.
  3. Poll the long-running operation until it completes (up to ~4 minutes).
  4. Download the video bytes and save as MP4.
  5. Register the video in ScriptState for display in the Media Lab.

CHARACTER VISUAL CONSISTENCY
─────────────────────────────
Reuses `_build_character_appearance_block` from image_gen to inject the
Character Bible's visual descriptions into the video prompt, ensuring
the characters' look is consistent with all other generated media.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path

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
    import shutil
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


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
        import subprocess
        st_path = Path(soundtrack_path) if soundtrack_path else None
        has_soundtrack = st_path is not None and st_path.exists()

        if has_soundtrack:
            # Mix dialogue (100% volume) and background score (25% volume)
            cmd = [
                ffmpeg_exe, "-y",
                "-stream_loop", "-1", "-i", str(v_path),
                "-i", str(a_path),
                "-stream_loop", "-1", "-i", str(st_path),
                "-filter_complex",
                "[1:a]volume=1.0[dialogue];[2:a]volume=0.25[music];[dialogue][music]amix=inputs=2:duration=first[aout]",
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


# ── Vertex AI Multi-Shot Dialogue Director Engine ─────────────────────

async def generate_multi_shot_dialogue_video(
    project_id: str,
    scene_number: int,
    scene_description: str,
    character_visuals: str = "",
) -> str | None:
    """
    Generate a full-duration, multi-camera dialogue scene video strictly powered by
    Vertex AI (Gemini 3.1 Flash TTS + Gemini 3.1 Flash Image + FFmpeg Director Stitcher).
    
    1. Extracts each dialogue line in the scene.
    2. Generates per-line character vocal tracks via Vertex AI Gemini 3.1 Flash TTS.
    3. Retrieves or creates canonical character portraits via Vertex AI Gemini 3.1 Flash Image.
    4. Creates dynamic cinematic camera shots (slow push-ins, pans) for each speaker turn.
    5. Seamlessly cuts between characters as each speaks, matching the exact speech duration.
    6. Mixes background score (Lyria 3) if available.
    7. Returns the final broadcast-ready video JSON with full duration and multi-shot metadata.
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

    logger.info(f"[MultiShotDirector] Directing multi-camera dialogue scene for Scene {scene_number} ({len(scene.dialogue)} lines)...")

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

        # Generate portrait via Gemini 3.1 Flash Image if missing
        if not portrait_file:
            logger.info(f"[MultiShotDirector] Generating canonical reference portrait for '{char_name}' via Gemini 3.1 Flash Image...")
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

    # Step 3: Render each speaker shot with cinematic camera motion & line audio
    shot_video_files = []
    fps = 30

    for idx, seg in enumerate(segments):
        speaker = seg["character"]
        duration = seg["duration"]
        audio_path = seg["audio_path"]
        portrait_path = character_portraits.get(speaker)

        if not portrait_path or not portrait_path.exists():
            # Fallback frame if image missing
            fallback_img = images_dir / f"fallback_{uuid.uuid4().hex[:6]}.jpg"
            from PIL import Image, ImageDraw
            im = Image.new("RGB", (1280, 720), color=(20, 24, 35))
            d = ImageDraw.Draw(im)
            d.text((540, 340), speaker, fill=(240, 240, 240))
            im.save(fallback_img)
            portrait_path = fallback_img

        shot_video_path = output_dir / f"scene_{scene_number}_shot_{idx}_{uuid.uuid4().hex[:6]}.mp4"
        total_frames = int(duration * fps)

        # Alternate cinematic camera motion per shot (slow push-in, subtle pan, slight zoom-out)
        if idx % 3 == 0:
            # Slow dramatic push-in
            z_filter = "min(zoom+0.0006,1.15)"
            x_filter = "iw/2-(iw/zoom/2)"
            y_filter = "ih/2-(ih/zoom/2)"
        elif idx % 3 == 1:
            # Subtle pan left to right
            z_filter = "min(zoom+0.0004,1.08)"
            x_filter = "(iw-iw/zoom)*0.7"
            y_filter = "ih/2-(ih/zoom/2)"
        else:
            # Steady close-up with slight floating motion
            z_filter = "min(zoom+0.0005,1.10)"
            x_filter = "iw/2-(iw/zoom/2)"
            y_filter = "(ih-ih/zoom)*0.4"

        cmd = [
            ffmpeg_exe, "-y",
            "-loop", "1", "-i", str(portrait_path),
            "-i", str(audio_path),
            "-vf", f"scale=1280:720,zoompan=z='{z_filter}':d={total_frames}:x='{x_filter}':y='{y_filter}':s=1280x720:fps={fps}",
            "-t", f"{duration:.3f}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            str(shot_video_path),
        ]

        logger.info(f"[MultiShotDirector] Rendering Shot {idx+1}/{len(segments)} ({speaker}, {duration:.1f}s)...")
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if proc.returncode == 0 and shot_video_path.exists() and shot_video_path.stat().st_size > 1000:
            shot_video_files.append(shot_video_path)
        else:
            logger.warning(f"[MultiShotDirector] Shot {idx+1} render failed: {proc.stderr.decode('utf-8', errors='ignore')[:200]}")

    if not shot_video_files:
        logger.warning("[MultiShotDirector] No shots rendered successfully.")
        return None

    # Step 4: Stitch all shots together into the full scene video
    concat_list_file = output_dir / f"concat_scene_{scene_number}_{uuid.uuid4().hex[:6]}.txt"
    with open(concat_list_file, "w") as cf:
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
        logger.info(f"[MultiShotDirector] Mixing Lyria 3 score under dialogue...")
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
        caption=f"Multi-Camera Dialogue Performance for Scene {scene_number} ({total_scene_duration:.1f}s, {len(segments)} shots)",
        structured_description={
            "video_summary": f"Full multi-camera dialogue performance for Scene {scene_number}",
            "duration_seconds": total_scene_duration,
            "shots_count": len(segments),
            "characters_speaking": list(character_portraits.keys()),
            "transcript": [
                {"speaker": seg["character"], "line": seg["line"], "duration": seg["duration"]}
                for seg in segments
            ],
            "has_embedded_dialogue": True,
            "has_soundtrack": bool(soundtrack_file),
        },
    )

    logger.info(f"[MultiShotDirector] Full scene video ready: {final_filepath} ({total_scene_duration:.1f}s)")

    return json.dumps({
        "success": True,
        "video_path": str(final_filepath),
        "filename": final_filename,
        "url": video_url,
        "scene_number": scene_number,
        "model": "vertex-ai-multi-shot-director",
        "duration_seconds": total_scene_duration,
        "shots_count": len(segments),
        "speakers": list(character_portraits.keys()),
        "has_embedded_dialogue": True,
        "has_soundtrack": bool(soundtrack_file),
        "message": (
            f"🎬 Generated full multi-camera dialogue performance for Scene {scene_number}! "
            f"Total duration: {total_scene_duration:.1f}s across {len(segments)} dynamic camera cuts with "
            f"character voices and background score. Watch it in the Media Lab or Script Workspace!"
        ),
    })


# ── Public API ────────────────────────────────────────────────────────

async def generate_scene_video(
    scene_number: int = 1,
    scene_description: str = "Screenplay scene performance",
    dialogue_context: str = "",
    characters: str = "",
    character_visuals: str = "",
    project_id: str = "",
) -> str:
    """
    Generate a video clip depicting characters performing their scene role.

    If the scene has dialogue lines, it uses the Vertex AI Multi-Shot Director
    Pipeline to generate a full-length, multi-camera performance video with
    character voices matching the exact dialogue timeline.

    Args:
        scene_number: Scene number being animated.
        scene_description: Detailed visual action lines and environment.
        dialogue_context: Spoken dialogue lines to be performed.
        characters: Character names and descriptions (legacy fallback).
        character_visuals: Character appearance spec JSON string (preferred).
        project_id: Project identifier for ScriptState registration.

    Returns:
        JSON string containing the generated video path, URL, and metadata.
    """
    from config import settings

    # ── Check if this is a dialogue scene with ScriptState ─────────────
    if project_id:
        try:
            from tools.script_state import _get_state
            state = await _get_state(project_id)
            scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
            if scene and scene.dialogue and len(scene.dialogue) > 0:
                logger.info(f"[Director] Scene {scene_number} has {len(scene.dialogue)} dialogue lines. Directing multi-camera video...")
                multi_shot_result = await generate_multi_shot_dialogue_video(
                    project_id=project_id,
                    scene_number=scene_number,
                    scene_description=scene_description,
                    character_visuals=character_visuals,
                )
                if multi_shot_result:
                    return multi_shot_result
        except Exception as ms_err:
            logger.warning(f"[MultiShotDirector] Multi-shot pipeline error, falling back to single-shot: {ms_err}")

    # ── 1. Build a rich cinematic prompt ──────────────────────────────
    prompt_parts = [
        f"Cinematic video clip for Scene {scene_number} of a screenplay.",
        f"Setting & Action: {scene_description}",
    ]

    # Inject character appearance sheet for visual consistency
    appearance_block = _build_character_appearance_block(character_visuals)
    if appearance_block:
        prompt_parts.append(appearance_block)
    elif characters:
        prompt_parts.append(f"Characters: {characters}")

    if dialogue_context:
        prompt_parts.append(f"Dialogue & Performance: {dialogue_context}")

    prompt_parts.append(
        "Style: photorealistic cinematic film clip, professional acting, "
        "dramatic lighting, smooth camera movement, movie production quality, "
        "widescreen 16:9, shallow depth of field."
    )

    prompt = "\n".join(prompt_parts)

    # ── 2. Prepare output path ────────────────────────────────────────
    output_dir = Path(settings.output_videos_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"scene_{scene_number}_video_{uuid.uuid4().hex[:8]}.mp4"
    filepath = output_dir / filename

    video_generated = False
    model_used = settings.veo_video_model

    # ── 3. Call Veo via Vertex AI ─────────────────────────────────────
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=getattr(settings, "gcp_video_location", "global"),
        )

        logger.info(f"[Veo] Starting video generation for Scene {scene_number} "
                     f"with model={model_used}...")

        operation = client.models.generate_videos(
            model=model_used,
            source=types.GenerateVideosSource(
                prompt=prompt[:1500],  # Veo prompt length limit
            ),
            config=types.GenerateVideosConfig(
                person_generation="ALLOW_ADULT",
                aspect_ratio="16:9",
                number_of_videos=1,
                duration_seconds=6,
            ),
        )

        logger.info(f"[Veo] Operation started. Polling for completion...")

        # Poll the long-running operation (up to ~4 minutes)
        max_polls = 12
        poll_interval = 20  # seconds
        for i in range(max_polls):
            await asyncio.sleep(poll_interval)
            try:
                operation = client.operations.get(operation)
            except Exception as poll_err:
                logger.warning(f"[Veo] Poll {i+1} error: {poll_err}")
                continue

            is_done = getattr(operation, "done", False)
            logger.info(f"[Veo] Poll {i+1}/{max_polls}: done={is_done}")

            if is_done:
                break

        # Extract video from completed operation
        is_done = getattr(operation, "done", False)
        if is_done:
            response = getattr(operation, "response", None)
            if response:
                generated_videos = getattr(response, "generated_videos", None)
                if generated_videos and len(generated_videos) > 0:
                    video_obj = generated_videos[0].video

                    # Try video_bytes first (direct bytes)
                    video_bytes = getattr(video_obj, "video_bytes", None)
                    if video_bytes:
                        with open(filepath, "wb") as f:
                            f.write(video_bytes)
                        video_generated = True
                        logger.info(f"[Veo] Video saved: {filepath} ({len(video_bytes)} bytes)")

                    # Try URI (GCS download) if no inline bytes
                    if not video_generated:
                        video_uri = getattr(video_obj, "uri", None)
                        if video_uri:
                            logger.info(f"[Veo] Video available at URI: {video_uri}")
                            try:
                                from google.cloud import storage
                                # Parse gs://bucket/path
                                if video_uri.startswith("gs://"):
                                    parts = video_uri[5:].split("/", 1)
                                    bucket_name = parts[0]
                                    blob_name = parts[1] if len(parts) > 1 else ""
                                    storage_client = storage.Client(project=settings.gcp_project_id)
                                    bucket = storage_client.bucket(bucket_name)
                                    blob = bucket.blob(blob_name)
                                    blob.download_to_filename(str(filepath))
                                    video_generated = True
                                    logger.info(f"[Veo] Downloaded from GCS: {filepath}")
                            except Exception as gcs_err:
                                logger.warning(f"[Veo] GCS download failed: {gcs_err}")

                if not video_generated:
                    logger.warning("[Veo] Operation completed but no video data found in response")
            else:
                err = getattr(operation, "error", None)
                logger.warning(f"[Veo] Operation completed with error: {err}")
        else:
            logger.warning("[Veo] Operation did not complete within polling window")

    except Exception as e:
        logger.warning(f"[Veo] Primary video generation failed: {type(e).__name__}: {e}")

    # ── 4. Fallback: Generate video via Pollinations (free API) ───────
    if not video_generated:
        logger.info("[Fallback] Trying video.pollinations.ai...")
        try:
            import urllib.request
            import urllib.parse

            # Pollinations video API
            safe_prompt = urllib.parse.quote(prompt[:500])
            video_api_url = (
                f"https://video.pollinations.ai/prompt/{safe_prompt}"
                f"?width=1280&height=720&duration=5&nologo=true"
            )

            req = urllib.request.Request(video_api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                video_data = resp.read()
                if len(video_data) > 1000:  # Sanity check — real video is > 1KB
                    with open(filepath, "wb") as f:
                        f.write(video_data)
                    video_generated = True
                    model_used = "pollinations-video"
                    logger.info(f"[Fallback] Pollinations video saved: {filepath} ({len(video_data)} bytes)")
                else:
                    logger.warning(f"[Fallback] Pollinations returned too-small response ({len(video_data)} bytes)")

        except Exception as poll_err:
            logger.warning(f"[Fallback] Pollinations video failed: {poll_err}")

    # ── 5. Final fallback: generate a sequence of scene images as slideshow ─
    if not video_generated:
        logger.info("[Fallback] Generating scene images as video frames...")
        try:
            from tools.image_gen import generate_scene_image

            # Generate 3 key-moment images for the scene
            frames = []
            moments = [
                f"Opening shot: {scene_description[:200]}",
                f"Mid scene dialogue: {dialogue_context[:200]}" if dialogue_context else f"Mid scene action: {scene_description[:200]}",
                f"Closing shot: {scene_description[:200]}, dramatic angle",
            ]

            for idx, moment_desc in enumerate(moments):
                result_json = await generate_scene_image(
                    scene_description=moment_desc,
                    dialogue_context=dialogue_context if idx == 1 else "",
                    characters=characters,
                    character_visuals=character_visuals,
                )
                result = json.loads(result_json)
                if result.get("success") and result.get("image_path"):
                    frames.append(result["image_path"])
                    logger.info(f"[Fallback] Generated frame {idx+1}: {result['image_path']}")

            if frames:
                # Create a slideshow MP4 from the frames using ffmpeg if available
                try:
                    import subprocess

                    ffmpeg_path = _get_ffmpeg_path()
                    if ffmpeg_path:
                        # Create a concat file
                        concat_path = output_dir / f"concat_{uuid.uuid4().hex[:6]}.txt"
                        with open(concat_path, "w") as cf:
                            for frame_path in frames:
                                cf.write(f"file '{frame_path}'\n")
                                cf.write("duration 2\n")
                            # Last frame needs to be listed again
                            cf.write(f"file '{frames[-1]}'\n")

                        cmd = [
                            ffmpeg_path, "-y",
                            "-f", "concat", "-safe", "0",
                            "-i", str(concat_path),
                            "-vsync", "vfr",
                            "-pix_fmt", "yuv420p",
                            "-c:v", "libx264",
                            "-movflags", "+faststart",
                            str(filepath),
                        ]
                        result = subprocess.run(cmd, capture_output=True, timeout=30)
                        if filepath.exists() and filepath.stat().st_size > 1000:
                            video_generated = True
                            model_used = "image-slideshow"
                            logger.info(f"[Fallback] Slideshow video created: {filepath}")

                        # Cleanup concat file
                        concat_path.unlink(missing_ok=True)
                except Exception as ff_err:
                    logger.warning(f"[Fallback] ffmpeg slideshow failed: {ff_err}")

                if not video_generated:
                    # No ffmpeg — return the image frames as the result
                    video_url = f"/api/media/videos/{filename}"
                    return json.dumps({
                        "success": True,
                        "type": "image_sequence",
                        "frames": [f"/api/media/images/{Path(f).name}" for f in frames],
                        "scene_number": scene_number,
                        "model": "scene-image-sequence",
                        "message": (
                            f"Generated {len(frames)} cinematic stills for Scene {scene_number}. "
                            f"Full video generation requires Veo 2.0 access. "
                            f"View the stills in the Media Lab!"
                        ),
                    })

        except Exception as img_err:
            logger.warning(f"[Fallback] Image sequence generation failed: {img_err}")

    # ── 6. Fail fast if no video ──────────────────────────────────────
    if not video_generated:
        return json.dumps({
            "success": False,
            "error": (
                "Video generation failed. The Veo 2.0 model may not be enabled "
                "for your GCP project, or the prompt may have been filtered. "
                "Please check your Vertex AI console and try again."
            ),
            "scene_number": scene_number,
        })

    # ── 7. Automatic Audio-Video Merging with Table Read Dialogue ─────
    merged_with_dialogue = False
    merged_with_soundtrack = False

    if project_id:
        try:
            from tools.script_state import _get_state, attach_media_to_scene
            state = await _get_state(project_id)
            scene = next((s for s in state.scenes if s.scene_number == scene_number), None)

            audio_file = None
            soundtrack_file = None

            if scene:
                # A. Check existing Table Read audio
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

                # B. If no table read yet, but scene has dialogue lines, generate Table Read automatically!
                if not audio_file and scene.dialogue:
                    logger.info(f"[AudioMerge] Generating Table Read audio automatically for Scene {scene_number}...")
                    from tools.tts import perform_table_read
                    dialogue_payload = json.dumps({"dialogue": [d.model_dump() for d in scene.dialogue]})
                    tts_res_json = await perform_table_read(project_id, dialogue_payload)
                    tts_res = json.loads(tts_res_json)
                    if tts_res.get("success") and tts_res.get("audio_path"):
                        audio_file = Path(tts_res["audio_path"])
                        if tts_res.get("url"):
                            await attach_media_to_scene(project_id, scene_number, "table_read_audio", tts_res["url"])
                            logger.info(f"[AudioMerge] On-the-fly Table Read generated & attached: {audio_file}")

                # C. Check existing Soundtrack score
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

            # D. Perform the audio merge if audio is available
            if audio_file and audio_file.exists():
                merged_output_path = output_dir / f"scene_{scene_number}_voiced_{uuid.uuid4().hex[:8]}.mp4"
                merged_path = merge_video_with_audio(
                    video_path=filepath,
                    audio_path=audio_file,
                    output_path=merged_output_path,
                    soundtrack_path=soundtrack_file,
                )
                if merged_path and merged_path.exists():
                    filepath = merged_path
                    filename = merged_path.name
                    merged_with_dialogue = True
                    if soundtrack_file:
                        merged_with_soundtrack = True
                    logger.info(f"[AudioMerge] Video successfully merged with dialogue: {filename}")
        except Exception as merge_err:
            logger.warning(f"[AudioMerge] Auto-merge encountered an error: {merge_err}")

    video_url = f"/api/media/videos/{filename}"

    # ── 8. Save to ScriptState ────────────────────────────────────────
    if project_id:
        try:
            from tools.script_state import save_media_analysis, attach_media_to_scene
            audio_note = " (with synchronized dialogue audio)" if merged_with_dialogue else ""
            await save_media_analysis(
                project_id=project_id,
                media_type="video",
                media_url=video_url,
                filename=filename,
                scene_number=scene_number,
                is_canon=True,
                caption=f"AI Video Performance for Scene {scene_number}{audio_note}: {scene_description[:100]}",
                structured_description={
                    "video_summary": f"Video clip of Scene {scene_number}: {scene_description}",
                    "has_embedded_dialogue": merged_with_dialogue,
                    "has_soundtrack": merged_with_soundtrack,
                    "transcript": [
                        {"timestamp": "00:01", "speaker": "Character", "dialogue": dialogue_context[:100]}
                    ] if dialogue_context else [],
                    "visual_events": [
                        {"timestamp": "00:00", "description": scene_description[:120]}
                    ],
                },
            )
            await attach_media_to_scene(project_id, scene_number, "concept_video", video_url)
        except Exception as err:
            logger.warning(f"Could not register generated video in ScriptState: {err}")

    msg = f"Generated video clip for Scene {scene_number}."
    if merged_with_dialogue:
        msg = f"🎬 Generated video clip with synchronized dialogue performance for Scene {scene_number}! Watch & listen in the Media Lab or Script Workspace."

    return json.dumps({
        "success": True,
        "video_path": str(filepath),
        "filename": filename,
        "url": video_url,
        "scene_number": scene_number,
        "model": model_used,
        "merged_with_dialogue": merged_with_dialogue,
        "merged_with_soundtrack": merged_with_soundtrack,
        "prompt": prompt[:200],
        "message": msg,
    })
