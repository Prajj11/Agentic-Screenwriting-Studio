"""
Story Architect Agent — generates beat sheets from loglines/pitches.

Uses structural frameworks (Three-Act, Save the Cat, Hero's Journey)
to create a full story outline that guides scene-by-scene writing.
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
5. Save the beat sheet and characters to the Script State

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
- `update_project_info`: Update project title, genre, format
- `get_current_script_state`: Check what exists already

After generating, ALWAYS save the beat sheet and characters using the tools.
"""


# ── Tool function wrappers (sync signatures for ADK) ─────────────────
# ADK tools need to be importable functions

from tools.script_state import (
    save_beat_sheet,
    save_character,
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
            "Hero's Journey). Also creates initial character concepts."
        ),
        instruction=STORY_ARCHITECT_INSTRUCTION.format(frameworks=_load_frameworks()),
        tools=[
            save_beat_sheet,
            save_character,
            update_project_info,
            get_current_script_state,
        ],
    )
