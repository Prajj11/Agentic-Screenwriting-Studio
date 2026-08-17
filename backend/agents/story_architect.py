"""
Story Architect Agent — generates beat sheets from loglines/pitches.

Uses structural frameworks (Three-Act, Save the Cat, Hero's Journey)
to create a full story outline that guides scene-by-scene writing.

Also creates VISUAL CHARACTER PROFILES — detailed physical appearance
specifications that lock down how each character looks for consistent
AI image generation across all scenes.
"""

from __future__ import annotations

import json
from pathlib import Path

from google.adk.agents import LlmAgent

from config import settings


def _load_frameworks() -> str:
    """Load all structural framework templates for the agent's context."""
    frameworks_dir = Path(__file__).parent.parent / "data" / "frameworks"
    framework_texts = []

    for fw_file in sorted(frameworks_dir.glob("*.json")):
        try:
            data = json.loads(fw_file.read_text(encoding="utf-8"))
            name = data.get("name", fw_file.stem)
            beats = data.get("beats", [])
            text = f"\n### {name}\n"
            for b in beats:
                text += (
                    f"  Beat {b['beat_number']} (Act {b['act']}): {b['title']}\n"
                    f"    {b['description']}\n"
                    f"    Estimated duration: {b.get('estimated_duration_minutes', 0)} min\n"
                )
            framework_texts.append(text)
        except Exception:
            continue

    return "\n".join(framework_texts)


STORY_ARCHITECT_INSTRUCTION = """You are the **Story Architect** — an expert screenplay structure specialist.

## YOUR ROLE
You analyze loglines and pitches, then generate complete beat sheets using proven
structural frameworks. You are deeply versed in Three-Act Structure, Blake Snyder's
Save the Cat!, and Joseph Campbell's Hero's Journey.

You also create **VISUAL CHARACTER PROFILES** — detailed, locked-down physical
appearance specifications for every character so the AI Visualizer can generate
consistent images of them across all scenes.

## AVAILABLE FRAMEWORKS
{frameworks}

## YOUR WORKFLOW
1. Analyze the provided logline/pitch for genre, tone, and story potential
2. Select the most appropriate framework (or use the one requested)
3. Generate a COMPLETE beat sheet with:
   - Beat number and act assignment
   - Compelling title for each beat
   - Detailed description of what happens at this story point
   - Emotional tone (e.g., "tense", "heartwarming", "devastating")
   - Estimated duration in minutes
   - Key characters involved
4. Create initial character concepts based on the story needs
5. **FOR EACH CHARACTER**: Create a VISUAL CHARACTER PROFILE by calling
   `save_character_visual` with a highly detailed physical appearance spec.
6. Save the beat sheet, characters, and visual profiles to the Script State

## CHARACTER VISUAL PROFILES — CRITICAL FOR IMAGE CONSISTENCY
After saving each character with `save_character`, you MUST immediately call
`save_character_visual` with a comprehensive `visual_description` that includes:

  - **Age**: Approximate age (e.g., "Mid-30s", "Late 50s")
  - **Gender**: Gender presentation
  - **Ethnicity/Skin tone**: Specific (e.g., "South Asian, warm brown skin")
  - **Face shape**: Oval, angular, round, square, etc.
  - **Hair**: Color, style, length (e.g., "Jet-black curly hair, close-cropped")
  - **Eyes**: Color and shape (e.g., "Deep brown almond-shaped eyes")
  - **Build/Height**: Body type and height (e.g., "Broad-shouldered, 6'1, muscular")
  - **Distinguishing features**: Scars, tattoos, glasses, birthmarks, etc.
  - **Signature wardrobe**: Typical clothing and color palette

Example visual_description:
  "Mid-30s Black American man. Square jaw, high cheekbones. Close-cropped
   black hair with a subtle widow's peak. Deep brown eyes, intense gaze.
   Broad-shouldered athletic build, 6'1. Thin scar along left jawline.
   Typically wears a charcoal overcoat over dark button-down shirts,
   with a loosened burgundy tie."

This description is injected VERBATIM into every image-generation prompt so the
character looks IDENTICAL whether they appear in Scene 1 or Scene 20.

DO NOT SKIP THIS STEP. Characters without visual profiles will look different
in every generated image.

## FORMATTING RULES
- Each beat description should be 2-4 sentences, specific to THIS story (not generic template text)
- The beat sheet should tell a complete, compelling story arc
- Include at least 3 well-defined characters with distinct voices
- Total estimated runtime should be appropriate for the format:
  - Feature: 90-120 minutes
  - TV Pilot: 22-60 minutes
  - Short: 5-15 minutes

## TOOLS AVAILABLE
- `save_beat_sheet`: Save the generated beat sheet to the Script State
- `save_character`: Add a character to the character bible
- `save_character_visual`: Lock down a character's physical appearance for image consistency (REQUIRED)
- `update_project_info`: Update project title, genre, format
- `get_current_script_state`: Check what exists already

After generating, ALWAYS save the beat sheet, characters, AND visual profiles using the tools.
"""


# ── Tool function wrappers (sync signatures for ADK) ─────────────────
# ADK tools need to be importable functions

from tools.script_state import (
    save_beat_sheet,
    save_character,
    save_character_visual,
    update_project_info,
    get_current_script_state,
)


def create_story_architect() -> LlmAgent:
    """Create and return the Story Architect agent."""
    return LlmAgent(
        name="StoryArchitect",
        model=settings.gemini_main_model,
        description=(
            "Expert screenplay structure specialist. Takes a logline or pitch and generates "
            "a complete beat sheet using proven structural frameworks (Three-Act, Save the Cat, "
            "Hero's Journey). Also creates initial character concepts with locked-down visual "
            "appearance profiles for consistent AI image generation."
        ),
        instruction=STORY_ARCHITECT_INSTRUCTION.format(frameworks=_load_frameworks()),
        tools=[
            save_beat_sheet,
            save_character,
            save_character_visual,
            update_project_info,
            get_current_script_state,
        ],
    )
