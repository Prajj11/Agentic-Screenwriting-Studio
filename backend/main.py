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

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
os.environ["GOOGLE_CLOUD_PROJECT"] = "gen-lang-client-0423661956"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form
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
from db.vector_router import get_vector_store
from tools.script_state import (
    set_active_state, get_active_state_sync, _active_states, _normalize_enum,
    save_media_analysis, get_project_media_analyses, mark_media_canon, associate_media_scene, delete_media_analysis
)
from tools.image_analyzer import analyze_image
from tools.video_analyzer import analyze_video
from tools.video_gen import generate_scene_video

# ── Gemini Rate Limit Monkey Patch ──────────────────────────────────────
import time
try:
    from google.genai.models import AsyncModels, Models
    _GENAI_PATCH_AVAILABLE = True
except ImportError:
    _GENAI_PATCH_AVAILABLE = False

if _GENAI_PATCH_AVAILABLE:
    # Async patch
    _orig_async_generate_content = AsyncModels.generate_content
    _orig_async_generate_content_stream = AsyncModels.generate_content_stream

    async def _patched_async_generate_content(self, *args, **kwargs):
        retries = 7
        delay = 4.0
        for attempt in range(retries):
            try:
                return await _orig_async_generate_content(self, *args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "too many requests" in err_str or "quota" in err_str:
                    if attempt == retries - 1:
                        raise
                    logging.getLogger("studio").warning(f"Rate limited (429). Retrying in {delay}s... (Attempt {attempt+1}/{retries})")
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    raise

    async def _patched_async_generate_content_stream(self, *args, **kwargs):
        retries = 7
        delay = 4.0
        for attempt in range(retries):
            try:
                return await _orig_async_generate_content_stream(self, *args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "too many requests" in err_str or "quota" in err_str:
                    if attempt == retries - 1:
                        raise
                    logging.getLogger("studio").warning(f"Rate limited (429) in stream. Retrying in {delay}s... (Attempt {attempt+1}/{retries})")
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    raise

    AsyncModels.generate_content = _patched_async_generate_content
    AsyncModels.generate_content_stream = _patched_async_generate_content_stream

    # Sync patch
    _orig_generate_content = Models.generate_content

    def _patched_generate_content(self, *args, **kwargs):
        retries = 7
        delay = 4.0
        for attempt in range(retries):
            try:
                return _orig_generate_content(self, *args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "too many requests" in err_str or "quota" in err_str:
                    if attempt == retries - 1:
                        raise
                    logging.getLogger("studio").warning(f"Rate limited (429) in sync call. Retrying in {delay}s... (Attempt {attempt+1}/{retries})")
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise

    Models.generate_content = _patched_generate_content

    # Patch generate_images only if it exists on this SDK version
    if hasattr(Models, 'generate_images'):
        _orig_generate_images = Models.generate_images

        def _patched_generate_images(self, *args, **kwargs):
            retries = 7
            delay = 4.0
            for attempt in range(retries):
                try:
                    return _orig_generate_images(self, *args, **kwargs)
                except Exception as e:
                    err_str = str(e).lower()
                    if "429" in err_str or "too many requests" in err_str or "quota" in err_str:
                        if attempt == retries - 1:
                            raise
                        logging.getLogger("studio").warning(f"Rate limited (429) in images call. Retrying in {delay}s... (Attempt {attempt+1}/{retries})")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        raise

        Models.generate_images = _patched_generate_images
# ──────────────────────────────────────────────────────────────────────
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
    allow_origin_regex=".*",
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
    "RightsClearance": {"status": "idle", "display_name": "⚖️ Rights & Clearance", "icon": "⚖️", "last_active": None},
    "Visualizer": {"status": "idle", "display_name": "🎨 Visualizer", "icon": "🎨", "last_active": None},
    "TableRead": {"status": "idle", "display_name": "🎙️ Table Read", "icon": "🎙️", "last_active": None},
    "Composer": {"status": "idle", "display_name": "🎵 Composer", "icon": "🎵", "last_active": None},
    "MediaAnalyzer": {"status": "idle", "display_name": "🎥 Media Analyzer", "icon": "🎥", "last_active": None},
}

# ── ADK Runner ────────────────────────────────────────────────────────
_showrunner = None
_runner = None
_sessions: dict[str, str] = {}  # project_id → session_id


def _get_showrunner():
    """Lazy-initialize the Showrunner agent."""
    global _showrunner
    if _showrunner is None:
        import vertexai
        if settings.gcp_project_id:
            vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)
        from agents.showrunner import create_showrunner
        _showrunner = create_showrunner()
    return _showrunner


async def _get_runner():
    """Lazy-initialize the ADK Runner with a DB-backed session service."""
    global _runner
    if _runner is None:
        from google.adk.runners import Runner
        from google.adk.sessions import DatabaseSessionService

        # Build the sqlite+aiosqlite URL from the same data/ directory already
        # used by the script-state SQLite store so everything lives together.
        session_db_url = (
            "sqlite+aiosqlite:///"
            + settings.sqlite_db_path.replace(
                "scriptwriter.db", "adk_sessions.db"
            ).replace("\\", "/")
        )
        logger.info(f"ADK session DB: {session_db_url}")

        _runner = Runner(
            agent=_get_showrunner(),
            app_name="screenwriting_studio",
            session_service=DatabaseSessionService(db_url=session_db_url),
        )
    return _runner


async def _get_or_create_session(runner, project_id: str) -> str:
    """
    Return the session_id for project_id, creating or re-creating it in the
    DB-backed session service when necessary.

    Strategy:
    1. Look up the cached session_id for this project.
    2. Try to fetch it from the DB — if it exists, return it.
    3. If the DB row is missing (restart / new worker / first use), create a
       fresh session, cache the new ID, and log a notice.
    """
    APP_NAME = "screenwriting_studio"
    USER_ID = "user"

    session_id = _sessions.get(project_id, f"session_{project_id}")

    # Try to read the existing session from the DB
    try:
        existing = await runner.session_service.get_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id,
        )
        if existing is not None:
            _sessions[project_id] = session_id
            return session_id
    except Exception as probe_err:
        logger.debug(f"Session probe raised (will recreate): {probe_err}")

    # Session missing — auto-recreate transparently
    logger.info(
        f"Session '{session_id}' not found in DB for project '{project_id}' — "
        "recreating transparently."
    )
    try:
        await runner.session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id,
            state={"project_id": project_id},
        )
    except Exception as create_err:
        # If the session_id already exists concurrently just continue
        logger.debug(f"Session create raised (likely race, continuing): {create_err}")

    _sessions[project_id] = session_id
    return session_id


async def _run_agent(project_id: str, user_message: str) -> tuple[str, list[dict]]:
    """
    Run the Showrunner agent with a user message and return the response.
    Returns (response_text, events).
    Handles stale session errors by recreating the session and retrying once.
    """
    runner = await _get_runner()
    events_list = []
    response_parts = []

    # Resolve (or create) a persistent DB-backed session
    session_id = await _get_or_create_session(runner, project_id)

    # Inject project_id context into the message
    full_message = f"[Project ID: {project_id}]\n\n{user_message}"

    # Run the agent
    from google.genai import types

    content = types.Content(
        role="user",
        parts=[types.Part(text=full_message)],
    )

    max_stale_retries = 2
    for stale_attempt in range(max_stale_retries):
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
                    if hasattr(event.content, 'parts') and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                txt = part.text.strip()
                                if txt and txt not in response_parts:
                                    response_parts.append(txt)
                                    ws_event = {
                                        "type": "text_chunk",
                                        "agent": author,
                                        "content": txt,
                                        "timestamp": datetime.now().isoformat(),
                                    }
                                    events_list.append(ws_event)
                                    await broadcast_event(ws_event)

                if hasattr(event, 'text') and event.text:
                    txt = str(event.text).strip()
                    if txt and txt not in response_parts:
                        response_parts.append(txt)

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

            # If we get here without error, break out of retry loop
            break

        except ValueError as ve:
            # Handle stale session error from ADK DatabaseSessionService
            if "stale" in str(ve).lower() or "modified in storage" in str(ve).lower():
                if stale_attempt < max_stale_retries - 1:
                    logger.warning(f"Stale session detected for project '{project_id}', recreating session and retrying...")
                    # Force-recreate the session
                    _sessions.pop(project_id, None)
                    session_id = await _get_or_create_session(runner, project_id)
                    events_list.clear()
                    response_parts.clear()
                    continue
                else:
                    raise
            else:
                raise

        except Exception as e:
            import traceback
            with open("error_trace.txt", "w") as f:
                f.write(traceback.format_exc())
            logger.error(f"Error running showrunner: {e}")
            response_parts.append(f"I encountered an error: {str(e)}. Let me try a different approach.")
            break
        
    # Reset agent statuses
    for name in _agent_statuses:
        if _agent_statuses[name]["status"] == "working":
            _agent_statuses[name]["status"] = "idle"

    if response_parts:
        response_text = "\n\n".join(response_parts)
    else:
        state = get_active_state_sync(project_id)
        if state and state.beat_sheet:
            response_text = f"I have processed your pitch for '{state.title}' and generated {len(state.beat_sheet)} beats in the Beat Sheet!"
        elif state and state.scenes:
            response_text = f"I have updated the script with {len(state.scenes)} scene(s)!"
        else:
            response_text = "I have processed your request and updated the script state."

    return response_text, events_list


# ── Startup / Shutdown ────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize database connections on startup."""
    settings.ensure_directories()
    await get_sqlite_store()
    get_vector_store()  # Initializes both ChromaDB + ClickHouse
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


@app.get("/api/health/clickhouse")
async def health_clickhouse():
    """ClickHouse Cloud vector store connection status."""
    store = get_vector_store()
    return store.health_check()


# ── Chat Endpoint ─────────────────────────────────────────────────────

@app.get("/api/chat/history/{project_id}")
async def get_chat_history(project_id: str):
    """Retrieve chat history for a project from ADK sessions."""
    runner = await _get_runner()
    session_id = await _get_or_create_session(runner, project_id)
    try:
        session = await runner.session_service.get_session(
            app_name="screenwriting_studio",
            user_id="user",
            session_id=session_id
        )
        if not session or not hasattr(session, 'events'):
            return {"messages": []}
            
        messages = []
        for event in session.events:
            role = "agent"
            author = getattr(event, 'author', '')
            if getattr(event, 'message', None):
                if getattr(event.message, 'role', '') == "user":
                    role = "user"
            
            txt = ""
            if hasattr(event, 'text') and event.text:
                txt = event.text
            elif hasattr(event, 'content') and event.content and hasattr(event.content, 'parts'):
                parts = [p.text for p in event.content.parts if hasattr(p, 'text') and p.text]
                txt = "\n".join(parts)
                
            if txt:
                messages.append({
                    "id": getattr(event, 'id', str(uuid.uuid4())),
                    "role": role,
                    "text": txt,
                    "agent": author if role == "agent" else None,
                    "timestamp": getattr(event, 'timestamp', datetime.now().isoformat())
                })
                
        # De-duplicate contiguous identical texts or system logs
        filtered = []
        for m in messages:
            if not filtered or filtered[-1]["text"] != m["text"]:
                filtered.append(m)
                
        return {"messages": filtered}
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return {"messages": []}

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the Showrunner and get a response."""
    project_id = request.project_id

    # Create a new project if none specified
    if not project_id:
        project_id = str(uuid.uuid4())[:12]
        state = ScriptState(project_id=project_id)
        if request.genre:
            state.genre = _normalize_enum(request.genre, Genre)
        if request.format:
            state.format = _normalize_enum(request.format, ScriptFormat)
        if request.framework:
            state.framework = _normalize_enum(request.framework, StructuralFramework)
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
    kwargs = {
        "project_id": project_id,
        "title": request.title,
        "logline": request.logline,
    }
    if request.genre:
        kwargs["genre"] = _normalize_enum(request.genre, Genre)
    if request.format:
        kwargs["format"] = _normalize_enum(request.format, ScriptFormat)
    if request.framework:
        kwargs["framework"] = _normalize_enum(request.framework, StructuralFramework)

    state = ScriptState(**kwargs)
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


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project by ID."""
    store = await get_sqlite_store()
    deleted = await store.delete_project(project_id)
    # Also remove from in-memory cache if present
    _active_states.pop(project_id, None)
    _sessions.pop(project_id, None)
    if not deleted:
        raise HTTPException(404, f"Project {project_id} not found")
    return {"status": "deleted", "project_id": project_id}


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


@app.get("/api/script/{project_id}/characters/visuals")
async def get_character_visuals(project_id: str):
    """Get visual appearance data and reference portraits for all characters."""
    state = get_active_state_sync(project_id)
    if not state:
        store = await get_sqlite_store()
        state = await store.load_script_state(project_id)
    if not state:
        raise HTTPException(404, f"Project {project_id} not found")

    visuals = {}
    for name, char in state.characters.items():
        visuals[name] = {
            "name": name,
            "visual_description": char.visual_description or "",
            "reference_portrait": char.reference_portrait or None,
            "has_visual_description": bool(char.visual_description),
            "has_reference_portrait": bool(char.reference_portrait),
        }

    total = len(visuals)
    with_visuals = sum(1 for v in visuals.values() if v["has_visual_description"])
    with_portraits = sum(1 for v in visuals.values() if v["has_reference_portrait"])

    return {
        "characters": visuals,
        "summary": {
            "total_characters": total,
            "with_visual_descriptions": with_visuals,
            "with_reference_portraits": with_portraits,
            "consistency_score": f"{(with_visuals / total * 100) if total else 0:.0f}%",
        },
    }


# ── Session Management ────────────────────────────────────────────────

@app.get("/api/sessions/{project_id}")
async def get_or_create_session_endpoint(project_id: str):
    """
    Return the session_id for a project, creating it in the DB if absent.
    Frontend calls this on startup / page-refresh to recover a previous session.
    """
    runner = await _get_runner()
    session_id = await _get_or_create_session(runner, project_id)
    return {"project_id": project_id, "session_id": session_id, "status": "ok"}


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
        "RightsClearance": "Flags legal/clearance risks",
        "Visualizer": "Generates concept art mood boards",
        "TableRead": "Performs TTS audio of dialogue",
        "Composer": "Generates cinematic soundtracks using Lyria 3",
        "MediaAnalyzer": "Analyzes reference images & videos",
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


@app.get("/api/media/videos/{filename}")
async def serve_video(filename: str):
    """Serve a generated scene video clip file."""
    filepath = Path(settings.output_videos_dir) / filename
    if not filepath.exists():
        raise HTTPException(404, f"Video not found: {filename}")
    return FileResponse(str(filepath), media_type="video/mp4")


@app.post("/api/video/generate")
async def generate_video_endpoint(payload: dict):
    """Generate a video performance for a scene."""
    scene_number = payload.get("scene_number", 1)
    scene_description = payload.get("scene_description", "Cinematic screenplay scene performance")
    dialogue_context = payload.get("dialogue_context", "")
    characters = payload.get("characters", "")

    result_json = await generate_scene_video(
        scene_number=scene_number,
        scene_description=scene_description,
        dialogue_context=dialogue_context,
        characters=characters,
    )
    return json.loads(result_json)


@app.get("/api/media/uploads/{filename}")
async def serve_upload(filename: str):
    """Serve an uploaded reference image or video file."""
    uploads_dir = Path(settings.sqlite_db_path).parent / "uploads"
    filepath = uploads_dir / filename
    if not filepath.exists():
        raise HTTPException(404, f"Uploaded media file not found: {filename}")
    
    mime_type, _ = mimetypes.guess_type(str(filepath))
    return FileResponse(str(filepath), media_type=mime_type or "application/octet-stream")


@app.post("/api/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    scene_number: Optional[int] = Form(None),
    is_canon: bool = Form(False),
):
    """
    Upload a reference image or video, run Gemini multimodal analysis,
    and persist the result into the project's ScriptState.
    """
    try:
        uploads_dir = Path(settings.sqlite_db_path).parent / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(file.filename).suffix or ".bin"
        unique_name = f"upload_{uuid.uuid4().hex[:8]}{ext}"
        filepath = uploads_dir / unique_name

        # Save uploaded file bytes
        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)

        # Determine media type (image vs video)
        mime = file.content_type or ""
        if mime.startswith("video/") or ext.lower() in [".mp4", ".mov", ".avi", ".webm", ".mkv"]:
            media_type = "video"
        else:
            media_type = "image"

        # Broadcast status update
        _agent_statuses["MediaAnalyzer"]["status"] = "working"
        _agent_statuses["MediaAnalyzer"]["last_active"] = datetime.now().isoformat()
        await broadcast_event({
            "type": "agent_start",
            "agent": "MediaAnalyzer",
            "content": f"Analyzing {media_type}: {file.filename}...",
            "timestamp": datetime.now().isoformat(),
        })

        # Run Gemini analysis
        if media_type == "video":
            raw_analysis = await analyze_video(str(filepath))
        else:
            raw_analysis = await analyze_image(str(filepath))

        _agent_statuses["MediaAnalyzer"]["status"] = "idle"
        await broadcast_event({
            "type": "agent_end",
            "agent": "MediaAnalyzer",
            "content": "Analysis complete",
            "timestamp": datetime.now().isoformat(),
        })

        analysis_data = json.loads(raw_analysis)
        if not analysis_data.get("success", False):
            raise HTTPException(500, analysis_data.get("error", "Analysis failed"))

        structured_desc = analysis_data.get("structured_description", {})
        summary = analysis_data.get("summary", "")

        media_url = f"/api/media/uploads/{unique_name}"

        # Persist into Script State
        raw_res = await save_media_analysis(
            project_id=project_id,
            media_type=media_type,
            media_url=media_url,
            filename=file.filename or unique_name,
            scene_number=scene_number,
            is_canon=is_canon,
            caption=summary,
            structured_description=structured_desc,
        )
        saved_info = json.loads(raw_res)

        return {
            "success": True,
            "media_id": saved_info.get("media_id"),
            "project_id": project_id,
            "media_type": media_type,
            "media_url": media_url,
            "filename": file.filename,
            "scene_number": scene_number,
            "is_canon": is_canon,
            "caption": summary,
            "structured_description": structured_desc,
            "created_at": datetime.now().isoformat(),
        }

    except Exception as e:
        _agent_statuses["MediaAnalyzer"]["status"] = "idle"
        logger.error(f"Error in upload_media: {e}", exc_info=True)
        raise HTTPException(500, f"Media processing failed: {str(e)}")


@app.get("/api/media/project/{project_id}")
async def list_project_media(project_id: str):
    """List all analyzed media items for a project."""
    res = await get_project_media_analyses(project_id)
    return json.loads(res)


@app.patch("/api/media/project/{project_id}/{media_id}")
async def update_media_item(
    project_id: str,
    media_id: str,
    payload: dict,
):
    """Update canon flag or scene association for a media item."""
    if "is_canon" in payload:
        await mark_media_canon(project_id, media_id, bool(payload["is_canon"]))
    if "scene_number" in payload:
        sn = payload["scene_number"]
        await associate_media_scene(project_id, media_id, int(sn) if sn is not None else None)
    return {"status": "updated", "media_id": media_id}


@app.delete("/api/media/project/{project_id}/{media_id}")
async def delete_media_item(project_id: str, media_id: str):
    """Delete a media item from the project script state."""
    await delete_media_analysis(project_id, media_id)
    return {"status": "deleted", "media_id": media_id}



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
