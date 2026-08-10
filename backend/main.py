"""
FastAPI backend for the Agentic Screenwriting Studio.

Serves as the HTTP API layer between the Next.js frontend and the
ADK agent system. Handles chat, script state, media serving, and
real-time WebSocket events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Add backend dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from models.api_models import (
    ChatRequest, ChatResponse, AgentEvent,
    CreateProjectRequest, ProjectSummary,
    AgentStatus, AgentStatusResponse,
    ExportRequest, ExportResponse,
)
from models.script_state import ScriptState, ScriptFormat, Genre, StructuralFramework
from db.sqlite_store import get_sqlite_store
from db.chroma_store import get_chroma_store
from tools.script_state import set_active_state, get_active_state_sync, _active_states

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("studio")

# ── FastAPI App ───────────────────────────────────────────────────────
app = FastAPI(
    title="Agentic Screenwriting Studio",
    description="Multi-agent AI system for collaborative screenwriting",
    version="1.0.0",
)

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── WebSocket connections ─────────────────────────────────────────────
_ws_connections: list[WebSocket] = []


async def broadcast_event(event: dict):
    """Broadcast an event to all connected WebSocket clients."""
    message = json.dumps(event)
    disconnected = []
    for ws in _ws_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _ws_connections.remove(ws)


# ── Agent State ───────────────────────────────────────────────────────
_agent_statuses: dict[str, dict] = {
    "Showrunner": {"status": "idle", "display_name": "🎬 Showrunner", "icon": "🎬", "last_active": None},
    "StoryArchitect": {"status": "idle", "display_name": "📐 Story Architect", "icon": "📐", "last_active": None},
    "DialogueSpecialist": {"status": "idle", "display_name": "✍️ Dialogue Specialist", "icon": "✍️", "last_active": None},
    "ContinuityChecker": {"status": "idle", "display_name": "🔍 Continuity Checker", "icon": "🔍", "last_active": None},
    "ResearchAgent": {"status": "idle", "display_name": "🌐 Research Agent", "icon": "🌐", "last_active": None},
    "RightsClearance": {"status": "idle", "display_name": "⚖️ Rights & Clearance", "icon": "⚖️", "last_active": None},
    "Visualizer": {"status": "idle", "display_name": "🎨 Visualizer", "icon": "🎨", "last_active": None},
    "TableRead": {"status": "idle", "display_name": "🎙️ Table Read", "icon": "🎙️", "last_active": None},
}

# ── ADK Runner ────────────────────────────────────────────────────────
_showrunner = None
_runner = None
_sessions: dict[str, str] = {}  # project_id → session_id


def _get_showrunner():
    """Lazy-initialize the Showrunner agent."""
    global _showrunner
    if _showrunner is None:
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
        from agents.showrunner import create_showrunner
        _showrunner = create_showrunner()
    return _showrunner


async def _get_runner():
    """Lazy-initialize the ADK Runner."""
    global _runner
    if _runner is None:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        
        _runner = Runner(
            agent=_get_showrunner(),
            app_name="screenwriting_studio",
            session_service=InMemorySessionService(),
        )
    return _runner


async def _run_agent(project_id: str, user_message: str) -> tuple[str, list[dict]]:
    """
    Run the Showrunner agent with a user message and return the response.
    Returns (response_text, events).
    """
    runner = await _get_runner()
    events_list = []
    response_parts = []

    # Get or create session
    if project_id not in _sessions:
        session_id = f"session_{project_id}"
        _sessions[project_id] = session_id
    
    session_id = _sessions[project_id]

    # Ensure session exists
    try:
        session = await runner.session_service.get_session(
            app_name="screenwriting_studio",
            user_id="user",
            session_id=session_id,
        )
    except Exception:
        session = await runner.session_service.create_session(
            app_name="screenwriting_studio",
            user_id="user",
            session_id=session_id,
            state={"project_id": project_id},
        )

    # Inject project_id context into the message
    full_message = f"[Project ID: {project_id}]\n\n{user_message}"

    # Run the agent
    from google.genai import types

    content = types.Content(
        role="user",
        parts=[types.Part(text=full_message)],
    )

    try:
        async for event in runner.run_async(
            user_id="user",
            session_id=session_id,
            new_message=content,
        ):
            # Track agent activity
            author = getattr(event, 'author', '') or ''
            
            if author and author in _agent_statuses:
                _agent_statuses[author]["status"] = "working"
                _agent_statuses[author]["last_active"] = datetime.now().isoformat()

            # Collect text responses
            if hasattr(event, 'content') and event.content:
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            response_parts.append(part.text)
                            
                            # Broadcast streaming event
                            ws_event = {
                                "type": "text_chunk",
                                "agent": author,
                                "content": part.text,
                                "timestamp": datetime.now().isoformat(),
                            }
                            events_list.append(ws_event)
                            await broadcast_event(ws_event)

            # Track tool calls
            if hasattr(event, 'function_calls') and event.function_calls:
                for fc in event.function_calls:
                    ws_event = {
                        "type": "tool_call",
                        "agent": author,
                        "content": f"Calling: {fc.name}",
                        "metadata": {"tool": fc.name},
                        "timestamp": datetime.now().isoformat(),
                    }
                    events_list.append(ws_event)
                    await broadcast_event(ws_event)

    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        response_parts.append(f"I encountered an error: {str(e)}. Let me try a different approach.")
        
    finally:
        # Reset agent statuses
        for name in _agent_statuses:
            if _agent_statuses[name]["status"] == "working":
                _agent_statuses[name]["status"] = "idle"

    response_text = "\n".join(response_parts) if response_parts else "I'm processing your request..."
    return response_text, events_list


# ── Startup / Shutdown ────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize database connections on startup."""
    settings.ensure_directories()
    await get_sqlite_store()
    get_chroma_store()
    logger.info("🎬 Agentic Screenwriting Studio backend started")
    logger.info(f"   Frontend URL: {settings.frontend_url}")


@app.on_event("shutdown")
async def shutdown():
    """Close database connections on shutdown."""
    store = await get_sqlite_store()
    await store.close()
    logger.info("Backend shutdown complete")


# ── Health Check ──────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Agentic Screenwriting Studio", "version": "1.0.0"}


# ── Chat Endpoint ─────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the Showrunner and get a response."""
    project_id = request.project_id

    # Create a new project if none specified
    if not project_id:
        project_id = str(uuid.uuid4())[:12]
        state = ScriptState(project_id=project_id)
        if request.genre:
            state.genre = request.genre
        if request.format:
            state.format = request.format
        if request.framework:
            state.framework = request.framework
        set_active_state(project_id, state)
        store = await get_sqlite_store()
        await store.save_script_state(state)

    # Ensure active state exists
    if not get_active_state_sync(project_id):
        store = await get_sqlite_store()
        loaded = await store.load_script_state(project_id)
        if loaded:
            set_active_state(project_id, loaded)
        else:
            state = ScriptState(project_id=project_id)
            set_active_state(project_id, state)

    # Run the agent
    await broadcast_event({
        "type": "agent_start",
        "agent": "Showrunner",
        "content": f"Processing: {request.message[:100]}...",
        "timestamp": datetime.now().isoformat(),
    })

    response_text, events = await _run_agent(project_id, request.message)

    await broadcast_event({
        "type": "agent_end",
        "agent": "Showrunner",
        "content": "Processing complete",
        "timestamp": datetime.now().isoformat(),
    })

    return ChatResponse(
        project_id=project_id,
        response_text=response_text,
        events=[AgentEvent(**e) for e in events],
        script_state_updated=True,
    )


# ── Project Endpoints ─────────────────────────────────────────────────

@app.post("/api/projects", response_model=ProjectSummary)
async def create_project(request: CreateProjectRequest):
    """Create a new screenplay project."""
    project_id = str(uuid.uuid4())[:12]
    state = ScriptState(
        project_id=project_id,
        title=request.title,
        genre=request.genre,
        format=request.format,
        framework=request.framework,
        logline=request.logline,
    )
    set_active_state(project_id, state)
    store = await get_sqlite_store()
    await store.save_script_state(state)

    return ProjectSummary(
        project_id=project_id,
        title=state.title,
        genre=state.genre.value if hasattr(state.genre, 'value') else str(state.genre),
        format=state.format.value if hasattr(state.format, 'value') else str(state.format),
        logline=state.logline,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


@app.get("/api/projects")
async def list_projects():
    """List all projects."""
    store = await get_sqlite_store()
    return await store.list_projects()


@app.get("/api/script/{project_id}")
async def get_script_state(project_id: str):
    """Get the full Script State for a project."""
    state = get_active_state_sync(project_id)
    if not state:
        store = await get_sqlite_store()
        state = await store.load_script_state(project_id)
    if not state:
        raise HTTPException(404, f"Project {project_id} not found")
    return json.loads(state.model_dump_json())


@app.get("/api/script/{project_id}/scenes")
async def get_scenes(project_id: str):
    """Get all scenes for a project."""
    state = get_active_state_sync(project_id)
    if not state:
        store = await get_sqlite_store()
        state = await store.load_script_state(project_id)
    if not state:
        raise HTTPException(404, f"Project {project_id} not found")
    return [json.loads(s.model_dump_json()) for s in state.scenes]


@app.get("/api/script/{project_id}/beats")
async def get_beats(project_id: str):
    """Get the beat sheet for a project."""
    state = get_active_state_sync(project_id)
    if not state:
        store = await get_sqlite_store()
        state = await store.load_script_state(project_id)
    if not state:
        raise HTTPException(404, f"Project {project_id} not found")
    return [json.loads(b.model_dump_json()) for b in state.beat_sheet]


@app.get("/api/script/{project_id}/characters")
async def get_characters(project_id: str):
    """Get the character bible for a project."""
    state = get_active_state_sync(project_id)
    if not state:
        store = await get_sqlite_store()
        state = await store.load_script_state(project_id)
    if not state:
        raise HTTPException(404, f"Project {project_id} not found")
    return {name: json.loads(c.model_dump_json()) for name, c in state.characters.items()}


# ── Agent Status ──────────────────────────────────────────────────────

@app.get("/api/agents/status", response_model=AgentStatusResponse)
async def get_agent_statuses():
    """Get the current status of all agents."""
    agents = []
    descriptions = {
        "Showrunner": "Coordinates all specialist agents",
        "StoryArchitect": "Generates beat sheets from pitches",
        "DialogueSpecialist": "Drafts scenes with dialogue",
        "ContinuityChecker": "Verifies scene consistency",
        "ResearchAgent": "Fact-checks via Parallel API",
        "RightsClearance": "Flags legal/clearance risks",
        "Visualizer": "Generates concept art mood boards",
        "TableRead": "Performs TTS audio of dialogue",
    }
    for name, info in _agent_statuses.items():
        agents.append(AgentStatus(
            name=name,
            display_name=info["display_name"],
            status=info["status"],
            description=descriptions.get(name, ""),
            last_active=info.get("last_active"),
            icon=info.get("icon", ""),
        ))
    return AgentStatusResponse(agents=agents)


# ── Media Serving ─────────────────────────────────────────────────────

@app.get("/api/media/images/{filename}")
async def serve_image(filename: str):
    """Serve a generated mood board image."""
    filepath = Path(settings.output_images_dir) / filename
    if not filepath.exists():
        raise HTTPException(404, f"Image not found: {filename}")
    return FileResponse(str(filepath), media_type="image/jpeg")


@app.get("/api/media/audio/{filename}")
async def serve_audio(filename: str):
    """Serve a generated table read audio file."""
    filepath = Path(settings.output_audio_dir) / filename
    if not filepath.exists():
        raise HTTPException(404, f"Audio not found: {filename}")
    return FileResponse(str(filepath), media_type="audio/wav")


# ── Export ────────────────────────────────────────────────────────────

@app.post("/api/script/{project_id}/export")
async def export_script(project_id: str, request: ExportRequest):
    """Export the script in the specified format."""
    state = get_active_state_sync(project_id)
    if not state:
        store = await get_sqlite_store()
        state = await store.load_script_state(project_id)
    if not state:
        raise HTTPException(404, f"Project {project_id} not found")

    state.update_metadata()

    if request.format == "fountain":
        # Fountain format (.fountain) — industry-standard plain text screenplay format
        content = _to_fountain(state)
        filename = f"{state.title.replace(' ', '_')}.fountain"
    else:
        # Plain text
        content = state.get_full_script_text()
        filename = f"{state.title.replace(' ', '_')}.txt"

    output_dir = Path(settings.output_images_dir).parent
    filepath = output_dir / filename
    filepath.write_text(content, encoding="utf-8")

    return ExportResponse(
        file_path=str(filepath),
        format=request.format,
        page_count=state.metadata.page_count,
    )


def _to_fountain(state: ScriptState) -> str:
    """Convert ScriptState to Fountain format."""
    lines = []
    lines.append(f"Title: {state.title}")
    lines.append(f"Credit: Written by")
    lines.append(f"Author: Agentic Screenwriting Studio")
    lines.append(f"Draft date: {state.updated_at[:10]}")
    lines.append(f"Notes: {state.logline}")
    lines.append("")
    lines.append("===")
    lines.append("")

    for scene in sorted(state.scenes, key=lambda s: s.scene_number):
        if scene.slugline:
            lines.append(f"\n{scene.slugline}\n")
        if scene.action_lines:
            lines.append(scene.action_lines)
            lines.append("")
        for dl in scene.dialogue:
            lines.append(f"@{dl.character.upper()}")
            if dl.parenthetical:
                lines.append(f"({dl.parenthetical.strip('()')})")
            lines.append(dl.line)
            lines.append("")

    return "\n".join(lines)


# ── WebSocket ─────────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint for real-time agent events."""
    await websocket.accept()
    _ws_connections.append(websocket)
    logger.info(f"WebSocket client connected ({len(_ws_connections)} total)")

    try:
        while True:
            # Keep connection alive; client can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        _ws_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected ({len(_ws_connections)} total)")


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        log_level="info",
    )
