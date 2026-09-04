"""
Script State tool functions — CRUD operations on the shared Script State.

These are registered as ADK tools so agents can read/write the script.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from models.script_state import (
    ScriptState, Scene, Character, Beat, ContinuityFact, MediaAnalysis,
    DialogueLine, SceneStatus, BeatStatus, ContinuityCategory,
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


def _parse_json_arg(arg: Any) -> Any:
    """Safely parse a tool argument that might be a dict, list, or JSON string with markdown backticks."""
    if isinstance(arg, (dict, list)):
        return arg
    if not isinstance(arg, str):
        return arg
    cleaned = arg.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return json.loads(cleaned)


async def save_beat_sheet(project_id: str, beats_json: Any) -> str:
    """
    Save a new beat sheet to the Script State.
    Input: JSON array of beat objects with keys: beat_number, act, title, description,
    emotional_tone, estimated_duration_minutes.
    """
    state = await _get_state(project_id)
    try:
        beats_data = _parse_json_arg(beats_json)
        if isinstance(beats_data, dict) and "beats" in beats_data:
            beats_data = beats_data["beats"]
        if not isinstance(beats_data, list):
            return json.dumps({"success": False, "error": f"Expected JSON array of beats, got {type(beats_data)}"})

        cleaned_beats = []
        for i, b in enumerate(beats_data):
            if not isinstance(b, dict):
                continue
            # Sanitize beat_number
            if "beat_number" not in b or not b["beat_number"]:
                b["beat_number"] = i + 1
            elif isinstance(b["beat_number"], str):
                digits = re.findall(r"\d+", b["beat_number"])
                b["beat_number"] = int(digits[0]) if digits else i + 1

            # Sanitize act (integer 1, 2, or 3)
            raw_act = b.get("act", 1)
            if isinstance(raw_act, str):
                digits = re.findall(r"\d+", raw_act)
                b["act"] = int(digits[0]) if digits else 1
            elif not isinstance(raw_act, int):
                b["act"] = 1

            # Sanitize status if passed
            if "status" in b and isinstance(b["status"], str):
                b["status"] = _normalize_enum(b["status"], BeatStatus)

            cleaned_beats.append(Beat(**b))

        state.beat_sheet = cleaned_beats
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


async def save_character(project_id: str, character_json: Any) -> str:
    """
    Add or update a character in the character bible.
    Input: JSON object with keys: name, description, traits, voice_notes, backstory.
    """
    state = await _get_state(project_id)
    try:
        char_data = _parse_json_arg(character_json)
        if not isinstance(char_data, dict):
            return json.dumps({"success": False, "error": f"Expected character JSON object, got {type(char_data)}"})

        name = char_data.get("name", "").strip()
        if not name:
            return json.dumps({"success": False, "error": "Character 'name' is required."})

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


async def add_scene_to_script(project_id: str, scene_json: Any) -> str:
    """
    Add a new scene to the script. Also indexes it in ChromaDB for continuity RAG.
    Input: JSON object with keys: scene_number, beat_reference, slugline, location,
    time_of_day, characters, action_lines, dialogue (array of {character, line, parenthetical}),
    mood_description, continuity_facts (array of {description, characters_involved, category}).
    """
    state = await _get_state(project_id)
    try:
        scene_data = _parse_json_arg(scene_json)
        if not isinstance(scene_data, dict):
            return json.dumps({"success": False, "error": f"Expected scene JSON object, got {type(scene_data)}"})

        # Sanitize scene_number
        raw_scene_num = scene_data.get("scene_number")
        if raw_scene_num is None or raw_scene_num == "":
            scene_number = len(state.scenes) + 1
        elif isinstance(raw_scene_num, int):
            scene_number = raw_scene_num
        else:
            digits = re.findall(r"\d+", str(raw_scene_num))
            scene_number = int(digits[0]) if digits else (len(state.scenes) + 1)
        scene_data["scene_number"] = scene_number

        # Sanitize beat_reference
        raw_beat_ref = scene_data.get("beat_reference")
        if raw_beat_ref is not None and raw_beat_ref != "":
            if isinstance(raw_beat_ref, int):
                scene_data["beat_reference"] = raw_beat_ref
            else:
                digits = re.findall(r"\d+", str(raw_beat_ref))
                scene_data["beat_reference"] = int(digits[0]) if digits else None
        else:
            # Check if any beat in beat_sheet matches this scene number
            if any(b.beat_number == scene_number for b in state.beat_sheet):
                scene_data["beat_reference"] = scene_number
            else:
                scene_data["beat_reference"] = None

        # Sanitize slugline / location / time_of_day
        slug = scene_data.get("slugline", "").strip()
        loc = scene_data.get("location", "").strip()
        tod = scene_data.get("time_of_day", "").strip()
        if slug and not loc:
            parts = slug.replace("INT.", "").replace("EXT.", "").replace("INT/EXT.", "").split("-")
            if parts:
                loc = parts[0].strip()
                if len(parts) > 1 and not tod:
                    tod = parts[1].strip()
        scene_data["location"] = loc or "LOCATION"
        scene_data["time_of_day"] = tod or "DAY"
        if not slug:
            scene_data["slugline"] = f"INT. {scene_data['location']} - {scene_data['time_of_day']}"

        # Sanitize characters
        raw_chars = scene_data.get("characters", [])
        chars = []
        if isinstance(raw_chars, str):
            chars = [c.strip() for c in raw_chars.split(",") if c.strip()]
        elif isinstance(raw_chars, list):
            for c in raw_chars:
                if isinstance(c, str) and c.strip():
                    chars.append(c.strip())
                elif isinstance(c, dict) and c.get("name"):
                    chars.append(str(c["name"]).strip())
        scene_data["characters"] = chars

        # Parse dialogue lines (gracefully handling strings and variations)
        dialogue = []
        for dl in scene_data.get("dialogue", []):
            if isinstance(dl, dict):
                char = dl.get("character") or dl.get("speaker") or dl.get("name") or "CHARACTER"
                line = dl.get("line") or dl.get("text") or dl.get("dialogue") or ""
                paren = dl.get("parenthetical") or None
                if paren and not str(paren).startswith("("):
                    paren = f"({paren})"
                dialogue.append(DialogueLine(character=str(char).upper(), line=str(line), parenthetical=paren))
            elif isinstance(dl, str) and dl.strip():
                if ":" in dl:
                    spk, text = dl.split(":", 1)
                    spk = spk.strip().upper()
                    text = text.strip()
                    paren = None
                    if text.startswith("(") and ")" in text:
                        paren_end = text.index(")")
                        paren = text[:paren_end + 1].strip()
                        text = text[paren_end + 1:].strip()
                    dialogue.append(DialogueLine(character=spk, line=text, parenthetical=paren))
                else:
                    dialogue.append(DialogueLine(character="CHARACTER", line=dl.strip()))
        # Fallback: If dialogue array is empty, check if dialogue was embedded in action_lines
        if not dialogue and scene_data.get("action_lines"):
            action_text = scene_data["action_lines"]
            # 1. Screenplay format: CHARACTER NAME in all caps, optional parenthetical, dialogue lines
            pattern_script = re.compile(
                r'(?:^|\n\n)([A-Z][A-Z0-9\s\.\'\-]{1,25})\n(?:\((.*?)\)\n)?([^\n]+(?:\n(?![A-Z]{2,}\b|\n)[^\n]+)*)',
                re.MULTILINE
            )
            for m in pattern_script.finditer(action_text):
                spk = m.group(1).strip().upper()
                if any(kw in spk for kw in ["INT.", "EXT.", "CUT TO", "FADE IN", "FADE OUT", "DISSOLVE", "SCENE"]):
                    continue
                paren = f"({m.group(2).strip()})" if m.group(2) else None
                text = m.group(3).strip()
                if text:
                    dialogue.append(DialogueLine(character=spk, line=text, parenthetical=paren))

            # 2. Colon format: CHARACTER: Line
            if not dialogue:
                pattern_colon = re.compile(
                    r'(?:^|\n)([A-Z][A-Z0-9\s\.\'\-]{1,25})(?:\s*\((.*?)\))?:\s*([^\n]+)',
                    re.MULTILINE
                )
                for m in pattern_colon.finditer(action_text):
                    spk = m.group(1).strip().upper()
                    if any(kw in spk for kw in ["INT.", "EXT.", "NOTE", "SCENE"]):
                        continue
                    paren = f"({m.group(2).strip()})" if m.group(2) else None
                    text = m.group(3).strip()
                    if text:
                        dialogue.append(DialogueLine(character=spk, line=text, parenthetical=paren))

        scene_data["dialogue"] = dialogue

        # Parse continuity facts (gracefully handling plain strings or dicts)
        facts = []
        raw_facts = scene_data.get("continuity_facts", [])
        if isinstance(raw_facts, list):
            for f in raw_facts:
                if isinstance(f, dict):
                    f["scene_established"] = scene_number
                    if "characters_involved" not in f or not f["characters_involved"]:
                        f["characters_involved"] = chars
                    elif isinstance(f["characters_involved"], str):
                        f["characters_involved"] = [c.strip() for c in f["characters_involved"].split(",") if c.strip()]
                    if "category" in f and isinstance(f["category"], str):
                        f["category"] = _normalize_enum(f["category"], ContinuityCategory)
                    facts.append(ContinuityFact(**f))
                elif isinstance(f, str) and f.strip():
                    facts.append(ContinuityFact(
                        description=f.strip(),
                        scene_established=scene_number,
                        characters_involved=chars,
                        category=ContinuityCategory.PLOT,
                    ))
        scene_data["continuity_facts"] = facts

        # Filter only valid Scene model attributes
        valid_keys = set(Scene.model_fields.keys())
        cleaned_scene_data = {k: v for k, v in scene_data.items() if k in valid_keys}

        scene = Scene(**cleaned_scene_data)
        scene.status = SceneStatus.DRAFTED
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

        # Mark corresponding beat as DRAFTED in the beat sheet
        if scene.beat_reference is not None:
            for b in state.beat_sheet:
                if b.beat_number == scene.beat_reference:
                    b.status = BeatStatus.DRAFTED
                    if scene.scene_number not in b.scene_numbers:
                        b.scene_numbers.append(scene.scene_number)

        # Add continuity facts to global log
        for fact in facts:
            state.continuity_log.append(fact)

        # Update characters' first appearance
        for char_name in scene.characters:
            if char_name in state.characters:
                if state.characters[char_name].first_appearance_scene is None:
                    state.characters[char_name].first_appearance_scene = scene.scene_number

        # Index in vector stores (ClickHouse + ChromaDB) — non-fatal
        try:
            store = get_vector_store()
            await store.index_scene(project_id, scene)
            for fact in facts:
                await store.index_continuity_fact(project_id, fact)
        except Exception as ve:
            logger.warning(f"Vector indexing warning for scene {scene.scene_number}: {ve}")

        # Save to SQLite
        await _save_state(project_id)

        return json.dumps({
            "success": True,
            "scene_number": scene.scene_number,
            "beat_reference": scene.beat_reference,
            "status": scene.status.value,
            "dialogue_count": len(scene.dialogue),
        })
    except Exception as e:
        logger.error(f"Error adding scene: {e}", exc_info=True)
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


async def save_character_visual(
    project_id: str,
    character_name: str,
    visual_description: str,
    reference_portrait: str = "",
) -> str:
    """
    Lock down a character's canonical physical appearance for visual consistency.

    This MUST be called by the StoryArchitect (or Visualizer) once per character
    before any scene images are generated.  Every subsequent image-generation
    call will inject this `visual_description` verbatim into the prompt so the
    AI depicts the character identically across scenes.

    Args:
        project_id: The project identifier.
        character_name: Exact name of the character (must already exist in the bible).
        visual_description: A detailed, structured physical appearance specification.
            MUST include: approximate age, gender, ethnicity/skin tone, face shape,
            hair color + style + length, eye color, build/height, and any
            distinguishing features (scars, tattoos, glasses, etc.).
            SHOULD include: signature wardrobe and color palette.
            Example: "Mid-30s East Asian woman. Oval face, sharp cheekbones.
            Jet-black straight hair, shoulder length, often tucked behind left ear.
            Dark brown almond eyes. Slim athletic build, 5'6. Small scar above
            right eyebrow. Typically wears dark tailored blazers over muted
            earth-tone tops."
        reference_portrait: Optional URL/path to a generated canonical portrait image.
    """
    state = await _get_state(project_id)
    char = state.characters.get(character_name)
    if not char:
        return json.dumps({
            "success": False,
            "error": f"Character '{character_name}' not found in the bible. Save the character first.",
        })

    char.visual_description = visual_description
    if reference_portrait:
        char.reference_portrait = reference_portrait
    await _save_state(project_id)

    logger.info(f"Locked visual description for '{character_name}' in project '{project_id}'")
    return json.dumps({
        "success": True,
        "character": character_name,
        "visual_description": visual_description[:200] + ("..." if len(visual_description) > 200 else ""),
        "has_reference_portrait": bool(reference_portrait),
        "message": (
            f"Visual appearance for '{character_name}' has been locked. "
            "All future image generations will use this description for consistency."
        ),
    })


async def get_character_visuals_for_scene(project_id: str, scene_number: int = 0) -> str:
    """
    Get a compact visual-only summary of characters for image generation.

    If scene_number is provided, returns visuals only for characters in that scene.
    If scene_number is 0, returns visuals for ALL characters.

    The output is formatted specifically for injection into image-generation prompts,
    containing only the visual_description (not backstory or personality traits).
    """
    state = await _get_state(project_id)

    # Determine which characters to include
    if scene_number > 0:
        scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
        if not scene:
            return json.dumps({"error": f"Scene {scene_number} not found."})
        char_names = scene.characters
    else:
        char_names = list(state.characters.keys())

    visuals = {}
    missing_visuals = []
    for name in char_names:
        char = state.characters.get(name)
        if char:
            if char.visual_description:
                visuals[name] = {
                    "visual_description": char.visual_description,
                    "reference_portrait": char.reference_portrait,
                }
            else:
                missing_visuals.append(name)
                # Fallback: use general description if no visual_description is set
                visuals[name] = {
                    "visual_description": char.description or f"[No visual description set for {name}]",
                    "reference_portrait": None,
                    "warning": "No locked visual_description — using general description as fallback.",
                }

    result = {"characters": visuals}
    if missing_visuals:
        result["warning"] = (
            f"Characters without locked visual descriptions: {', '.join(missing_visuals)}. "
            "Run save_character_visual for each to ensure consistent depiction across scenes."
        )
    return json.dumps(result, indent=2)


async def attach_media_to_scene(project_id: str, scene_number: int, media_type: str, url: str) -> str:
    """
    Attach a generated media URL to a scene in the Script State.
    media_type should be one of 'mood_board_image', 'table_read_audio', or 'soundtrack_audio'.
    """
    state = await _get_state(project_id)
    scene = next((s for s in state.scenes if s.scene_number == scene_number), None)
    if not scene:
        return json.dumps({"success": False, "error": f"Scene {scene_number} not found."})

    if media_type == "mood_board_image":
        scene.mood_board_image = url
    elif media_type == "concept_video":
        scene.concept_video = url
    elif media_type == "table_read_audio":
        scene.table_read_audio = url
    elif media_type == "soundtrack_audio":
        scene.soundtrack_audio = url
    else:
        return json.dumps({"success": False, "error": "Invalid media_type."})

    await _save_state(project_id)

    return json.dumps({
        "success": True,
        "scene_number": scene_number,
        "media_type": media_type,
        "url": url,
        "message": f"Successfully attached {media_type} to scene {scene_number}."
    })


# ── Media Analysis Functions ──────────────────────────────────────────

async def save_media_analysis(
    project_id: str,
    media_type: str,
    media_url: str,
    filename: str = "",
    scene_number: Optional[int] = None,
    is_canon: bool = False,
    caption: str = "",
    structured_description: Optional[dict] = None,
) -> str:
    """
    Save a new media analysis entry to the Script State.
    """
    state = await _get_state(project_id)
    analysis = MediaAnalysis(
        project_id=project_id,
        media_type=media_type,
        media_url=media_url,
        filename=filename,
        scene_number=scene_number,
        is_canon=is_canon,
        caption=caption,
        structured_description=structured_description or {},
    )
    state.media_analyses.append(analysis)
    await _save_state(project_id)

    return json.dumps({
        "success": True,
        "media_id": analysis.media_id,
        "media_type": analysis.media_type,
        "is_canon": analysis.is_canon,
        "scene_number": analysis.scene_number,
    })


async def get_project_media_analyses(project_id: str) -> str:
    """
    Get all media analysis items for a project as JSON.
    """
    state = await _get_state(project_id)
    return json.dumps([m.model_dump() for m in state.media_analyses], indent=2)


async def mark_media_canon(project_id: str, media_id: str, is_canon: bool) -> str:
    """
    Toggle whether a media item is marked as CANON or REFERENCE.
    """
    state = await _get_state(project_id)
    item = next((m for m in state.media_analyses if m.media_id == media_id), None)
    if not item:
        return json.dumps({"success": False, "error": f"Media item {media_id} not found."})

    item.is_canon = is_canon
    await _save_state(project_id)
    return json.dumps({"success": True, "media_id": media_id, "is_canon": item.is_canon})


async def associate_media_scene(project_id: str, media_id: str, scene_number: Optional[int]) -> str:
    """
    Associate a media analysis item with a specific scene number (or None for project-level).
    """
    state = await _get_state(project_id)
    item = next((m for m in state.media_analyses if m.media_id == media_id), None)
    if not item:
        return json.dumps({"success": False, "error": f"Media item {media_id} not found."})

    item.scene_number = scene_number
    await _save_state(project_id)
    return json.dumps({"success": True, "media_id": media_id, "scene_number": item.scene_number})


async def delete_media_analysis(project_id: str, media_id: str) -> str:
    """
    Delete a media analysis item from the script state.
    """
    state = await _get_state(project_id)
    state.media_analyses = [m for m in state.media_analyses if m.media_id != media_id]
    await _save_state(project_id)
    return json.dumps({"success": True, "media_id": media_id})

