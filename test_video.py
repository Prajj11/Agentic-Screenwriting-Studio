import asyncio
import json
import sys
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

logging.basicConfig(level=logging.DEBUG)

# Add backend to path
sys.path.append(str(Path("backend").resolve()))

from backend.tools.video_gen import generate_scene_video

async def main():
    fake_scene = MagicMock()
    fake_scene.scene_number = 2
    fake_dialogue = MagicMock()
    fake_dialogue.model_dump.return_value = {"character": "DR. ARIS THORNE", "line": "Amazing. It's glowing.", "parenthetical": ""}
    fake_scene.dialogue = [fake_dialogue]
    fake_scene.mood_board_image = ""
    
    fake_state = MagicMock()
    fake_state.scenes = [fake_scene]
    fake_state.characters = {}

    with patch("backend.tools.video_gen._get_state", new_callable=AsyncMock) as mock_get_state:
        mock_get_state.return_value = fake_state
        res = await generate_scene_video(
            scene_number=2,
            scene_description="Dr. Aris Thorne discovers the artifact.",
            dialogue_context="",
            characters="",
            character_visuals="",
            project_id="test_project",
            video_mode="auto"
        )
        print("RESULT:", res)

if __name__ == "__main__":
    asyncio.run(main())
