"""
API request/response models for the FastAPI endpoints.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ── Chat ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """User message sent to the Showrunner."""
    message: str
    project_id: Optional[str] = None
    # Optional overrides
    genre: Optional[str] = None
    format: Optional[str] = None
    framework: Optional[str] = None


class AgentEvent(BaseModel):
    """A real-time event from the agent system."""
    type: str          # "agent_start", "agent_end", "tool_call", "text_chunk", "error"
    agent: str = ""
    content: str = ""
    metadata: dict = Field(default_factory=dict)
    timestamp: str = ""


class ChatResponse(BaseModel):
    """Response from the Showrunner after processing."""
    project_id: str
    response_text: str
    events: list[AgentEvent] = Field(default_factory=list)
    script_state_updated: bool = False


# ── Project ───────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    """Create a new screenplay project."""
    title: str = "Untitled Project"
    genre: str = "drama"
    format: str = "feature"
    framework: str = "three_act"
    logline: str = ""


class ProjectSummary(BaseModel):
    """Summary of a project for listing."""
    project_id: str
    title: str
    genre: str
    format: str
    logline: str
    scene_count: int = 0
    created_at: str = ""
    updated_at: str = ""


# ── Scene ─────────────────────────────────────────────────────────────

class SceneUpdateRequest(BaseModel):
    """Request to update a specific scene."""
    scene_number: int
    action_lines: Optional[str] = None
    mood_description: Optional[str] = None
    status: Optional[str] = None


# ── Agent Status ──────────────────────────────────────────────────────

class AgentStatus(BaseModel):
    """Current status of a specialist agent."""
    name: str
    display_name: str
    status: str = "idle"       # idle, working, completed, error
    description: str = ""
    last_active: Optional[str] = None
    icon: str = ""


class AgentStatusResponse(BaseModel):
    """All agent statuses."""
    agents: list[AgentStatus] = Field(default_factory=list)


# ── Export ────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    """Export the script in a specific format."""
    format: str = "fountain"   # "fountain", "pdf", "text"


class ExportResponse(BaseModel):
    """Result of a script export."""
    file_path: str
    format: str
    page_count: int = 0
