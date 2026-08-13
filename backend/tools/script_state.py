"""
Script State tool functions — CRUD operations on the shared Script State.

These are registered as ADK tools so agents can read/write the script.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from models.script_state import (
    ScriptState, Scene, Character, Beat, ContinuityFact,
    DialogueLine, SceneStatus, BeatStatus,
    Genre, ScriptFormat, StructuralFramework,
    normalize_enum,
)
from db.sqlite_store import get_sqlite_store
from db.vector_router import get_vector_store

logger = logging.getLogger(__name__)

_normalize_enum = normalize_enum


# ── In-memory state cache ─────────────────────────────────────────────
# Agents operate on the in-memory state for speed; periodically flushed to SQLite.
_active_states: dict[str, ScriptState] = {}


async def _get_state(project_id: str) -> ScriptState:
    """Get the current active state, loading from DB if needed."""
    if project_id not in _active_states:
        store = await get_sqlite_store()
        state = await store.load_script_state(project_id)
        if state is None:
            state = ScriptState(project_id=project_id)
        _active_states[project_id] = state
    return _active_states[project_id]


async def _save_state(project_id: str):
    """Flush in-memory state to SQLite."""
    if project_id in _active_states:
        store = await get_sqlite_store()
        await store.save_script_state(_active_states[project_id])


def set_active_state(project_id: str, state: ScriptState):
    """Set the active in-memory state (used by the Showrunner on project creation)."""
    _active_states[project_id] = state


def get_active_state_sync(project_id: str) -> ScriptState | None:
    """Synchronous getter for the in-memory state (for agent tools)."""
    return _active_states.get(project_id)


# ── Tool Functions (registered with ADK agents) ──────────────────────

async def get_current_script_state(project_id: str) -> str:
    """
    Get the full current Script State as a JSON string.
    Includes: title, genre, logline, beat sheet, all scenes, character bible,
    continuity log, and metadata.
    """
    state = await _get_state(project_id)
    return state.model_dump_json(indent=2)


async def get_beat_sheet(project_id: str) -> str:
    """Get the current beat sheet as a JSON string."""
    state = await _get_state(project_id)
    if not state.beat_sheet:
        return json.dumps({"message": "No beat sheet has been created yet.", "beats": []})
    return json.dumps([b.model_dump() for b in state.beat_sheet], indent=2)


async def save_beat_sheet(project_id: str, beats_json: str) -> str:
    """
    Save a new beat sheet to the Script State.
    Input: JSON array of beat objects with keys: beat_number, act, title, description,
    emotional_tone, estimated_duration_minutes.
    """
    state = await _get_state(project_id)
    try:
        beats_data = json.loads(beats_json)
        state.beat_sheet = [Beat(**b) for b in beats_data]
        await _save_state(project_id)
        return json.dumps({"success": True, "beat_count": len(state.beat_sheet)})
    except Exception as e:
        logger.error(f"Error saving beat sheet: {e}")
        return json.dumps({"success": False, "error": str(e)})


async def get_character_bible(project_id: str, character_name: str = "") -> str:
    """
    Get character bible entries. If character_name is provided, returns that
    character's entry. Otherwise returns all characters.
    """
    state = await _get_state(project_id)
    if character_name:
        char = state.characters.get(character_name)
        if char:
            return char.model_dump_json(indent=2)
        return json.dumps({"error": f"Character '{character_name}' not found."})
    return json.dumps({name: c.model_dump() for name, c in state.characters.items()}, indent=2)


async def save_character(project_id: str, character_json: str) -> str:
    """
    Add or update a character in the character bible.
    Input: JSON object with keys: name, description, traits, voice_notes, backstory.
    """
    state = await _get_state(project_id)
    try:
        char_data = json.loads(character_json)
        name = char_data["name"]

        # Coerce comma-separated string → list (LLMs often send "a, b, c" instead of ["a","b","c"])
        if isinstance(char_data.get("traits"), str):
            char_data["traits"] = [t.strip() for t in char_data["traits"].split(",") if t.strip()]

        if name in state.characters:
            existing = state.characters[name]
            for key, val in char_data.items():
                if key != "id" and val:
                    setattr(existing, key, val)
        else:
            state.characters[name] = Character(**char_data)
        await _save_state(project_id)
        return json.dumps({"success": True, "character": name})
    except Exception as e:
        logger.error(f"Error saving character: {e}")
        return json.dumps({"success": False, "error": str(e)})


async def add_scene_to_script(project_id: str, scene_json: str) -> str:
    """
    Add a new scene to the script. Also indexes it in ChromaDB for continuity RAG.
    Input: JSON object with keys: scene_number, beat_reference, slugline, location,
    time_of_day, characters, action_lines, dialogue (array of {character, line, parenthetical}),
    mood_description, continuity_facts (array of {description, characters_involved, category}).
    """
    state = await _get_state(project_id)
    try:
        scene_data = json.loads(scene_json)

        # Parse dialogue lines
        dialogue = []
        for dl in scene_data.get("dialogue", []):
            dialogue.append(DialogueLine(**dl))
        scene_data["dialogue"] = dialogue

        # Parse continuity facts
        facts = []
        for f in scene_data.get("continuity_facts", []):
            f["scene_established"] = scene_data.get("scene_number", len(state.scenes) + 1)
            facts.append(ContinuityFact(**f))
        scene_data["continuity_facts"] = facts

        scene = Scene(**scene_data)
        scene.status = SceneStatus.DRAFTED

        # Generate the raw screenplay text
        scene.raw_text = scene.to_screenplay_text()

        # Add or update
        existing_idx = next(
            (i for i, s in enumerate(state.scenes) if s.scene_number == scene.scene_number),
            None,
        )
        if existing_idx is not None:
            scene.version = state.scenes[existing_idx].version + 1
            state.scenes[existing_idx] = scene
        else:
            state.scenes.append(scene)
            state.scenes.sort(key=lambda s: s.scene_number)

        # Add continuity facts to the global log
        for fact in facts:
            state.continuity_log.append(fact)

        # Update characters' first appearance
        for char_name in scene.characters:
            if char_name in state.characters:
                if state.characters[char_name].first_appearance_scene is None:
                    state.characters[char_name].first_appearance_scene = scene.scene_number

        # Index in vector stores (ClickHouse + ChromaDB)
        store = get_vector_store()
        await store.index_scene(project_id, scene)
        for fact in facts:
            await store.index_continuity_fact(project_id, fact)

        # Save
        await _save_state(project_id)

        return json.dumps({
            "success": True,
            "scene_number": scene.scene_number,
            "status": scene.status.value,
            "dialogue_count": len(scene.dialogue),
        })
    except Exception as e:
        logger.error(f"Error adding scene: {e}")
        return json.dumps({"success": False, "error": str(e)})


async def get_scene(project_id: str, scene_number: int) -> str:
    """Get a specific scene by number."""
    state = await _get_state(project_id)
    scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
    if scene:
        return scene.model_dump_json(indent=2)
    return json.dumps({"error": f"Scene {scene_number} not found."})


async def get_all_scenes_summary(project_id: str) -> str:
    """Get a summary list of all scenes (number, slugline, status, characters)."""
    state = await _get_state(project_id)
    summaries = []
    for s in state.scenes:
        summaries.append({
            "scene_number": s.scene_number,
            "slugline": s.slugline,
            "status": s.status.value,
            "characters": s.characters,
            "dialogue_count": len(s.dialogue),
        })
    return json.dumps(summaries, indent=2)


async def get_continuity_log(project_id: str) -> str:
    """Get all established continuity facts."""
    state = await _get_state(project_id)
    return json.dumps([f.model_dump() for f in state.continuity_log], indent=2)


async def update_project_info(
    project_id: str,
    title: str = "",
    genre: str = "",
    format: str = "",
    logline: str = "",
    framework: str = "",
) -> str:
    """Update basic project information (title, genre, format, logline, framework)."""
    state = await _get_state(project_id)
    if title:
        state.title = title
    if genre:
        state.genre = _normalize_enum(genre, Genre)
    if format:
        state.format = _normalize_enum(format, ScriptFormat)
    if logline:
        state.logline = logline
    if framework:
        state.framework = _normalize_enum(framework, StructuralFramework)
    await _save_state(project_id)
    return json.dumps({"success": True, "project_id": project_id})


async def mark_scene_final(project_id: str, scene_number: int) -> str:
    """
    Mark a scene as FINAL. This is a FORCED FUNCTION — the continuity checker
    MUST have been run before this function succeeds. If the scene has unresolved
    continuity issues, this will FAIL.
    """
    state = await _get_state(project_id)
    scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
    if not scene:
        return json.dumps({"success": False, "error": f"Scene {scene_number} not found."})

    # ENFORCEMENT: Check that the scene has been reviewed (continuity-checked)
    if scene.status not in (SceneStatus.REVIEWED, SceneStatus.FINAL):
        return json.dumps({
            "success": False,
            "error": (
                f"Scene {scene_number} has NOT been continuity-checked yet. "
                "You MUST run the ContinuityChecker agent on this scene before marking it final. "
                "Current status: " + scene.status.value
            ),
        })

    # Check for unresolved continuity issues
    unresolved = [i for i in scene.continuity_issues if not i.resolved]
    if unresolved:
        return json.dumps({
            "success": False,
            "error": f"Scene {scene_number} has {len(unresolved)} unresolved continuity issues.",
            "issues": [i.model_dump() for i in unresolved],
        })

    scene.status = SceneStatus.FINAL
    await _save_state(project_id)

    # Save a version snapshot
    store = await get_sqlite_store()
    await store.save_version(state, f"Scene {scene_number} marked as FINAL")

    return json.dumps({
        "success": True,
        "scene_number": scene_number,
        "status": "final",
        "message": f"Scene {scene_number} is now FINAL. Continuity verified.",
    })


async def mark_scene_reviewed(project_id: str, scene_number: int, issues_json: str = "[]") -> str:
    """
    Mark a scene as REVIEWED by the Continuity Checker.
    Optionally attach continuity issues found.
    """
    state = await _get_state(project_id)
    scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
    if not scene:
        return json.dumps({"success": False, "error": f"Scene {scene_number} not found."})

    # Parse and attach issues
    try:
        issues_data = json.loads(issues_json)
        from models.script_state import ContinuityIssue
        scene.continuity_issues = [ContinuityIssue(**i) for i in issues_data]
    except Exception:
        scene.continuity_issues = []

    scene.status = SceneStatus.REVIEWED
    await _save_state(project_id)

    return json.dumps({
        "success": True,
        "scene_number": scene_number,
        "status": "reviewed",
        "issues_found": len(scene.continuity_issues),
    })
