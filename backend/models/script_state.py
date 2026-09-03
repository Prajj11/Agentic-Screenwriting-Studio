"""
Pydantic data models for the shared Script State.

These models define the core data structures that all agents read/write:
- Characters, Beats, Scenes, Continuity Facts
- The top-level ScriptState that the Showrunner owns and updates
- Versioned snapshots for undo/history
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums & Normalization ──────────────────────────────────────────────

def normalize_enum(value: str | Enum | None, enum_class: type[Enum]) -> Enum:
    """Fuzzy-match a free-text string to an enum member with fallback to default."""
    if value is None:
        return list(enum_class)[0]
    if isinstance(value, enum_class):
        return value
    if not isinstance(value, str):
        return list(enum_class)[0]

    lowered = value.lower().strip()

    # 1. Exact value match
    for member in enum_class:
        if member.value == value or member.value == lowered:
            return member

    # 2. Name match
    for member in enum_class:
        if member.name.lower() == lowered:
            return member

    # 3. Slug match (strip quotes, exclamation marks, replace spaces/dashes with underscores)
    slug = (
        lowered.replace("'", "")
        .replace("!", "")
        .replace("?", "")
        .replace("-", "_")
        .replace(" ", "_")
    )
    for member in enum_class:
        if member.value == slug or member.name.lower() == slug:
            return member

    # 4. Substring match
    for member in enum_class:
        if member.value in slug or slug in member.value:
            return member

    # 5. Fallback to first member of enum
    return list(enum_class)[0]


class ScriptFormat(str, Enum):
    FEATURE = "feature"
    TV_PILOT = "tv_pilot"
    SHORT = "short"


class Genre(str, Enum):
    DRAMA = "drama"
    COMEDY = "comedy"
    THRILLER = "thriller"
    HORROR = "horror"
    SCI_FI = "sci_fi"
    ROMANCE = "romance"
    ACTION = "action"
    MYSTERY = "mystery"
    FANTASY = "fantasy"
    HISTORICAL = "historical"
    CRIME = "crime"
    WESTERN = "western"


class BeatStatus(str, Enum):
    PLANNED = "planned"
    DRAFTED = "drafted"
    FINAL = "final"


class SceneStatus(str, Enum):
    OUTLINE = "outline"
    DRAFTED = "drafted"
    REVIEWED = "reviewed"       # Continuity-checked
    FINAL = "final"


class StructuralFramework(str, Enum):
    THREE_ACT = "three_act"
    SAVE_THE_CAT = "save_the_cat"
    HEROS_JOURNEY = "heros_journey"


class ContinuityCategory(str, Enum):
    LOCATION = "location"
    TIMELINE = "timeline"
    CHARACTER = "character"
    PROP = "prop"
    PLOT = "plot"
    WORLD_RULE = "world_rule"


class ClearanceSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Core Models ───────────────────────────────────────────────────────

class DialogueLine(BaseModel):
    """A single line of dialogue in a scene."""
    character: str
    parenthetical: Optional[str] = None   # e.g. "(whispering)"
    line: str


class Character(BaseModel):
    """A character in the screenplay with their bible entry."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str = ""
    traits: list[str] = Field(default_factory=list)
    voice_notes: str = ""                  # How they speak — dialect, patterns, quirks
    backstory: str = ""
    established_facts: dict[str, str] = Field(default_factory=dict)  # fact_key → fact_value
    first_appearance_scene: Optional[int] = None

    # ── Visual Consistency Fields ─────────────────────────────────────
    # These fields lock down a character's canonical physical appearance so
    # that every AI-generated image depicts them identically across scenes.
    visual_description: str = ""           # Locked-down physical appearance spec:
                                           #   age, gender, ethnicity/skin tone, face shape,
                                           #   hair color/style/length, eye color, build/height,
                                           #   distinguishing features (scars, tattoos, glasses),
                                           #   signature wardrobe/color palette.
                                           # Example: "Mid-30s East Asian woman. Oval face, sharp
                                           #   cheekbones. Jet-black straight hair, shoulder length,
                                           #   often tucked behind left ear. Dark brown almond eyes.
                                           #   Slim athletic build, 5'6. Small scar above right
                                           #   eyebrow. Typically wears dark tailored blazers over
                                           #   muted earth-tone tops."
    reference_portrait: Optional[str] = None  # Path/URL to a canonical reference portrait image
                                              # generated once and reused for visual consistency


class Beat(BaseModel):
    """A single beat in the story's structural outline."""
    beat_number: int
    act: int                               # 1, 2, or 3
    title: str
    description: str
    emotional_tone: str = ""
    estimated_duration_minutes: float = 0.0
    status: BeatStatus = BeatStatus.PLANNED
    scene_numbers: list[int] = Field(default_factory=list)  # Scenes that realize this beat


class ContinuityFact(BaseModel):
    """A fact established in a scene that must remain consistent."""
    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    scene_established: int                 # Scene number where the fact was set
    description: str
    characters_involved: list[str] = Field(default_factory=list)
    category: ContinuityCategory = ContinuityCategory.PLOT


class ContinuityIssue(BaseModel):
    """A continuity contradiction found by the Continuity Checker."""
    issue_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    scene_number: int
    description: str
    conflicting_fact: Optional[ContinuityFact] = None
    severity: str = "medium"               # low, medium, high
    suggested_fix: str = ""
    resolved: bool = False


class ClearanceFlag(BaseModel):
    """A rights/clearance issue found by the Rights & Clearance Agent."""
    flag_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    scene_number: int
    flagged_text: str
    issue_type: str                        # brand_name, song_lyrics, public_figure, trademark
    severity: ClearanceSeverity = ClearanceSeverity.MEDIUM
    explanation: str = ""
    suggested_rewrite: str = ""
    resolved: bool = False


class MediaAnalysis(BaseModel):
    """An analyzed media item (image or video) attached to a project/scene."""
    media_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    project_id: str
    media_type: str                         # "image" or "video"
    media_url: str                          # URL or relative path to access the file
    filename: str = ""
    scene_number: Optional[int] = None      # Optional scene association
    is_canon: bool = False                  # REFERENCE vs CANON
    caption: str = ""                       # Summary / caption string
    structured_description: dict = Field(default_factory=dict) # Image analysis or video transcript/events
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class Scene(BaseModel):
    """A full scene in the screenplay."""
    scene_number: int
    beat_reference: Optional[int] = None   # Which beat this scene realizes
    slugline: str = ""                     # e.g. "INT. COFFEE SHOP - DAY"
    location: str = ""
    time_of_day: str = ""
    characters: list[str] = Field(default_factory=list)
    action_lines: str = ""                 # Narrative/action description
    dialogue: list[DialogueLine] = Field(default_factory=list)
    continuity_facts: list[ContinuityFact] = Field(default_factory=list)
    continuity_issues: list[ContinuityIssue] = Field(default_factory=list)
    clearance_flags: list[ClearanceFlag] = Field(default_factory=list)
    status: SceneStatus = SceneStatus.OUTLINE
    version: int = 1
    mood_description: str = ""             # For Visualizer
    mood_board_image: Optional[str] = None # Path to generated image
    concept_video: Optional[str] = None    # Path to generated video clip
    table_read_audio: Optional[str] = None # Path to generated audio
    soundtrack_audio: Optional[str] = None # Path to generated Lyria 3 score
    raw_text: str = ""                     # The full formatted screenplay text

    def to_screenplay_text(self) -> str:
        """Render this scene as formatted screenplay text."""
        lines = []
        if self.slugline:
            lines.append(f"\n{self.slugline}\n")
        if self.action_lines:
            lines.append(self.action_lines)
        for dl in self.dialogue:
            lines.append(f"\n\t\t\t{dl.character.upper()}")
            if dl.parenthetical:
                lines.append(f"\t\t{dl.parenthetical}")
            lines.append(f"\t{dl.line}")
        return "\n".join(lines)


class ScriptMetadata(BaseModel):
    """Production metadata about the script."""
    page_count: int = 0
    estimated_runtime_minutes: float = 0.0
    total_scenes: int = 0
    total_dialogue_lines: int = 0
    dialogue_balance: dict[str, int] = Field(default_factory=dict)  # character → line count
    action_to_dialogue_ratio: float = 0.0


class ScriptState(BaseModel):
    """
    The top-level shared state object that the Showrunner owns.
    All agents read from and write to this object.
    """
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    title: str = "Untitled Project"
    genre: Genre = Genre.DRAMA
    format: ScriptFormat = ScriptFormat.FEATURE
    logline: str = ""
    framework: StructuralFramework = StructuralFramework.THREE_ACT

    @field_validator("genre", mode="before")
    @classmethod
    def validate_genre(cls, v):
        return normalize_enum(v, Genre)

    @field_validator("format", mode="before")
    @classmethod
    def validate_format(cls, v):
        return normalize_enum(v, ScriptFormat)

    @field_validator("framework", mode="before")
    @classmethod
    def validate_framework(cls, v):
        return normalize_enum(v, StructuralFramework)


    # Story structure
    beat_sheet: list[Beat] = Field(default_factory=list)

    # Scenes
    scenes: list[Scene] = Field(default_factory=list)

    # Character bible
    characters: dict[str, Character] = Field(default_factory=dict)  # name → Character

    # Continuity
    continuity_log: list[ContinuityFact] = Field(default_factory=list)

    # Media Analysis
    media_analyses: list[MediaAnalysis] = Field(default_factory=list)

    # Voice assignments (character_name_normalized → TTS voice name)
    # Persisted so voices survive server restarts and stay consistent
    # between Table Read and Animatic pipelines.
    voice_assignments: dict[str, str] = Field(default_factory=dict)

    # Metadata
    metadata: ScriptMetadata = Field(default_factory=ScriptMetadata)

    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def update_metadata(self):
        """Recalculate production metadata from current state."""
        self.metadata.total_scenes = len(self.scenes)
        total_lines = 0
        balance: dict[str, int] = {}
        total_action_chars = 0
        total_dialogue_chars = 0

        for scene in self.scenes:
            for dl in scene.dialogue:
                total_lines += 1
                balance[dl.character] = balance.get(dl.character, 0) + 1
                total_dialogue_chars += len(dl.line)
            total_action_chars += len(scene.action_lines)

        self.metadata.total_dialogue_lines = total_lines
        self.metadata.dialogue_balance = balance

        if total_dialogue_chars + total_action_chars > 0:
            self.metadata.action_to_dialogue_ratio = (
                total_action_chars / (total_dialogue_chars + total_action_chars)
            )

        # Rough estimate: 1 page ≈ 1 minute, 250 words ≈ 1 page
        total_words = sum(
            len(scene.action_lines.split()) + sum(len(dl.line.split()) for dl in scene.dialogue)
            for scene in self.scenes
        )
        self.metadata.page_count = max(1, total_words // 250) if total_words else 0
        self.metadata.estimated_runtime_minutes = self.metadata.page_count  # 1 page ≈ 1 min

        self.updated_at = datetime.now().isoformat()

    def get_full_script_text(self) -> str:
        """Render the entire script as formatted text."""
        header = f"TITLE: {self.title}\n"
        header += f"GENRE: {self.genre.value}\n"
        header += f"FORMAT: {self.format.value}\n"
        header += f"LOGLINE: {self.logline}\n"
        header += "=" * 60 + "\n"

        body = ""
        for scene in sorted(self.scenes, key=lambda s: s.scene_number):
            body += scene.to_screenplay_text() + "\n"

        return header + body


class ScriptVersion(BaseModel):
    """A versioned snapshot of the full script state."""
    version_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    project_id: str
    version_number: int
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    changes_summary: str = ""
    full_state_json: str = ""  # Serialized ScriptState
