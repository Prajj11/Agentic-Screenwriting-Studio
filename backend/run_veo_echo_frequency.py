"""
Direct verification script for Google Veo 3.1 cinematic video generation.
Tests Scene 1 generation for 'The Echo Frequency' using locked character visuals,
directorial collision physics, and audio merging.
"""
import asyncio
import os
import sys
import json
import logging
from pathlib import Path

# Setup Vertex AI environment
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0423661956"))
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("veo_runner")

async def main():
    from tools.video_gen import generate_scene_video
    from tools.script_state import _get_state

    project_id = "f78b5d13-04b"
    state = await _get_state(project_id)
    print(f"Loaded project: {state.title} ({project_id})")

    # Character visuals from character bible
    char_visuals = {
        name: {
            "visual_description": c.visual_description,
            "reference_portrait": c.reference_portrait,
        }
        for name, c in state.characters.items()
    }
    char_visuals_json = json.dumps(char_visuals)

    scene_1 = next((s for s in state.scenes if s.scene_number == 1), None)
    desc = (
        "INT. AUDIO LAB - NIGHT: The sterile glow of monitors illuminates Dr. ELARA REID (30s, East Asian woman, chin-length bob) "
        "as she hunches over her soundboard amidst a labyrinth of cables. Her deep brown eyes are analytical and tense as her fingers "
        "turn rotary dials and adjust faders. She wears large padded studio headphones, head cocked, listening intensely as waveform "
        "monitors dance erratically with sound data. Steadycam 35mm optical cinematography, photorealistic live action with real physical motion."
    )

    print("\n" + "=" * 60)
    print("STARTING GOOGLE VEO 3.1 GENERATION FOR THE ECHO FREQUENCY (SCENE 1)")
    print("=" * 60 + "\n")

    res_json = await generate_scene_video(
        scene_number=1,
        scene_description=desc,
        dialogue_context='ELARA: "Isolating frequency band 4... what is that sound?"',
        characters="ELARA REID",
        character_visuals=char_visuals_json,
        project_id=project_id,
        video_mode="veo",
        duration_seconds=16,
    )

    res = json.loads(res_json)
    print("\n" + "=" * 60)
    print("VEO GENERATION COMPLETE")
    print("=" * 60)
    print(json.dumps(res, indent=2))

    if res.get("success") and res.get("video_path"):
        vpath = Path(res["video_path"])
        if vpath.exists():
            print(f"\n[CONFIRMED] Generated Veo video exists at: {vpath}")
            print(f"File size: {vpath.stat().st_size / (1024*1024):.2f} MB")

if __name__ == "__main__":
    asyncio.run(main())
