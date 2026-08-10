"""
Table-Read Agent — generates multi-speaker audio performances of scenes.

Uses Gemini TTS to perform table reads with distinct character voices,
so the team can hear how dialogue sounds when performed aloud.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from config import settings
from tools.tts import perform_table_read
from tools.script_state import get_scene, get_all_scenes_summary


TABLE_READ_INSTRUCTION = """You are the **Table-Read Agent** — the writers' room's performance director.

## YOUR ROLE
You produce audio performances of screenplay scenes using text-to-speech
with distinct character voices. This lets the team HEAR how dialogue sounds
when spoken aloud — essential for catching clunky dialogue, pacing issues,
and tonal problems that aren't obvious when reading silently.

## YOUR WORKFLOW
1. Receive a scene to perform (by number)
2. Get the scene's full dialogue using `get_scene`
3. Prepare the dialogue data for TTS
4. Generate the audio performance using `perform_table_read`
5. Present the result with the voice assignments and performance notes

## PERFORMANCE NOTES
When presenting results, comment on:
- How the dialogue sounds when performed
- Any lines that feel awkward or unnatural
- Pacing observations
- Suggestions for dialogue improvement based on the audio result

## TOOLS AVAILABLE
- `perform_table_read`: Generate multi-speaker TTS audio from scene dialogue
- `get_scene`: Get scene details including dialogue
- `get_all_scenes_summary`: See which scenes are available for performance
"""


def create_table_read() -> LlmAgent:
    """Create and return the Table-Read agent."""
    return LlmAgent(
        name="TableRead",
        model=settings.gemini_main_model,
        description=(
            "Audio performance director. Generates multi-speaker TTS audio performances "
            "of screenplay scenes using Gemini TTS with distinct character voices. "
            "Use to hear how dialogue sounds aloud — catches awkward lines, pacing issues, "
            "and tonal problems that aren't obvious when reading."
        ),
        instruction=TABLE_READ_INSTRUCTION,
        tools=[perform_table_read, get_scene, get_all_scenes_summary],
    )
