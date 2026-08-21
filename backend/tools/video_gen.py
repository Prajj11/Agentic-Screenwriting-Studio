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

    Uses Google Veo 2.0 via Vertex AI for real AI video generation.
    The operation is asynchronous (long-running) — we poll until it completes.

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
                    import shutil

                    ffmpeg_path = shutil.which("ffmpeg")
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

    # ── 6. Register & return ──────────────────────────────────────────
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

    video_url = f"/api/media/videos/{filename}"

    # Save to ScriptState
    if project_id:
        try:
            from tools.script_state import save_media_analysis
            await save_media_analysis(
                project_id=project_id,
                media_type="video",
                media_url=video_url,
                filename=filename,
                scene_number=scene_number,
                is_canon=True,
                caption=f"AI Video Performance for Scene {scene_number}: {scene_description[:100]}",
                structured_description={
                    "video_summary": f"Video clip of Scene {scene_number}: {scene_description}",
                    "transcript": [
                        {"timestamp": "00:01", "speaker": "Character", "dialogue": dialogue_context[:100]}
                    ] if dialogue_context else [],
                    "visual_events": [
                        {"timestamp": "00:00", "description": scene_description[:120]}
                    ],
                },
            )
        except Exception as err:
            logger.warning(f"Could not register generated video in ScriptState: {err}")

    return json.dumps({
        "success": True,
        "video_path": str(filepath),
        "filename": filename,
        "url": video_url,
        "scene_number": scene_number,
        "model": model_used,
        "prompt": prompt[:200],
        "message": f"Generated video clip for Scene {scene_number}. Watch it in the Media Lab!",
    })
