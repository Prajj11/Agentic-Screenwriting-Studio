# 🎬 Talevora — Agentic Screenwriting Studio

> **Built for the Google Cloud Agentic Cinema Hackathon** 🏆  

Live App: https://talevora.antideploy.com/

---

**Talevora** is an end-to-end, multi-agent virtual writers' room and cinematic pre-production studio powered by **Google ADK (Agent Development Kit)** and **Google Gemini models**. It elevates screenwriting from a solitary blank-page ordeal to an orchestrated, collaborative pipeline: transforming a single-sentence logline into a fully structured, continuity-checked, performable screenplay complete with **cinematic concept art**, **multi-speaker dramatic table reads**, **original musical scores**, and **full-motion video performances**.

---

## 🏗️ Multi-Agent Architecture

Talevora coordinates specialized agents organized in a hierarchical writers' room topology managed by the **Showrunner**. Every agent has dedicated prompt engineering, tool access, and access to the shared, versioned **Script State**.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           🎬 Showrunner (Coordinator)                            │
│           Orchestrates specialists, manages Script State, enforces gates         │
├──────┬──────┬──────┬──────┬──────────┬────────┬──────────┬────────┬──────────────┤
│  📐  │  ✍️  │  🔍  │  ⚖️  │    🎨    │   🎙️   │    🎵    │   🎥   │      🎬      │
│Story │Dial. │Cont. │Rights│Visualizer│ Table  │ Composer │ Media  │    Video     │
│Arch. │Spec. │Check │Clear │(Art/Port)│ Read   │(Lyria 3) │Analyzer│    Engine    │
└──────┴──────┴──────┴──────┴──────────┴────────┴──────────┴────────┴──────────────┘
```

### The 9 ADK Agents

| Agent | Role & Responsibility | Primary Model / Integration |
|---|---|---|
| **🎬 Showrunner** | Central coordinator — routes intents, updates Script State, maintains session history, and enforces quality gates | Google ADK + `gemini-2.5-flash` / `gemini-2.5-pro` |
| **📐 Story Architect** | Generates beat sheets from pitches using proven dramatic frameworks (Save the Cat!, Three-Act, Hero's Journey) | `gemini-2.5-flash` + Structured Framework Templates |
| **✍️ Dialogue Specialist** | Drafts full cinematic scenes with authentic character voices, parentheticals, and sluglines adhering to screenplay standards | `gemini-2.5-pro` + Character Bible context |
| **🔍 Continuity Checker** | Real-time RAG-based consistency verification — prevents contradictions across characters, props, timelines, and world rules | ClickHouse Cloud (Vector DB) + ChromaDB + `text-embedding-004` |
| **⚖️ Rights & Clearance** | Scans drafted scenes for legal risks (brand trademarks, song lyrics, public figures, defamatory references) | `gemini-2.5-flash` + Legal Severity Scoring |
| **🎨 Visualizer** | Generates high-fidelity scene concept art, atmospheric mood boards, and locked character reference portraits | `gemini-2.5-flash-image` / `gemini-3.1-flash-image` |
| **🎙️ Table Read** | Synthesizes multi-speaker dramatic audio performances with character-distinct voices, emotional tags, and pauses | `gemini-3.1-flash-tts-preview` |
| **🎵 Composer** | Analyzes the emotional arc and dramatic tension of finalized scenes to compose bespoke cinematic soundtracks | Google DeepMind **Lyria 3** (`lyria-3-pro-preview`) |
| **🎥 Media Analyzer** | Multimodal reference ingestion — analyzes uploaded mood images, storyboards, and reference video clips, extracts transcripts, and sets visual canon | Gemini Multimodal Vision + Audio Transcription |

---

## ✨ Key Features

### 🛑 Programmatic Continuity Gate
In professional screenwriting, canon consistency is critical. Talevora enforces an automated **Continuity Gate**: no scene can transition to `"FINAL"` status until the **Continuity Checker** agent has indexed the scene facts, verified them against all historical canon in the vector database, and resolved any conflicting issues.

### 🧠 Dual-Write Vector RAG (ClickHouse Cloud + ChromaDB)
The studio features a resilient, dual-write vector store architecture:
- **ClickHouse Cloud (Primary)**: High-performance cloud vector database indexing characters, locations, timeline milestones, props, and visual canon using cosine distance over `text-embedding-004` 768-dimensional embeddings.
- **ChromaDB (Local Fallback)**: Automatically activates if cloud credentials are absent, guaranteeing uninterrupted offline development.
- Live connection health and latency monitoring are displayed directly in the studio UI.

### 🎬 Cinematic Video Generation Engine (Veo 3.1 & Animatic Engine)
Bring screenplay scenes to life in motion:
- **Google Veo (`veo-3.1-generate-001`)**: Generates high-definition video clips matching the visual style, lighting, and camera instructions of the drafted scene.
- **Cinematic Multi-Shot Animatic Renderer**: A custom rendering pipeline using FFmpeg that decomposes scenes into key visual beats, pans and zooms with dynamic camera motion, and layers the synthesized character dialogue and original score into an exported MP4.
- Handled via non-blocking asynchronous background worker tasks with WebSocket progress updates.

### 🎥 Multimodal Media Lab & Reference Analyzer
Writers often work with visual references, mood boards, and video clips:
- **Image Analysis**: Upload concept art, location photos, or storyboards for automated Gemini breakdown (setting, lighting, characters, props, action).
- **Video Analysis & Transcription**: Upload reference footage (`.mp4`, `.mov`, `.webm`) to extract timestamped dialogue transcripts with speaker attribution and visual event timelines.
- **Visual Canon**: Mark reference media as authoritative **CANON**, which automatically injects its visual parameters into downstream character portraits and scene art.

### 👥 Character Bible & Cross-Scene Visual Consistency
- Automatically extracts character concepts during beat sheet creation.
- Maintains character archetypes, backstories, voice notes, dialogue balance, and traits.
- Generates locked visual appearance descriptions and reference portraits so characters maintain visual fidelity across every scene.

### 🎭 Multi-Speaker Table Reads
- Uses `gemini-3.1-flash-tts-preview` to perform dialogue aloud.
- Intelligently batches dialogue lines to support multi-character conversations without exceeding API limits.
- Assigns distinct voice profiles with embedded emotion tags (whispers, shouts, tension).

### 🎵 Bespoke Musical Scores (Lyria 3)
- Analyzes scene mood, genre, and tempo to create prompt-engineered soundtrack requests.
- Generates lossless audio scores using Google's **Lyria 3** music model.

### 📜 Screenplay Formatting & Fountain Export
- Standard industry layout with scene headers (sluglines), action lines, character names, parentheticals, and dialogue.
- Export scripts with one click into **Fountain (`.fountain`)** plain text screenplay syntax or formatted `.txt`.

### 🖥️ Bespoke Cinema UI & Real-Time Event Bus
- High-contrast, dark-mode cinema aesthetic built with Next.js 14 and pure Vanilla CSS (no bloated UI libraries).
- Real-time **WebSocket event stream** displaying agent thoughts, tool execution, and generation progress.
- Dedicated **Scene Experience Modal** unifying script text, concept video, mood board art, table read audio, and original soundtrack in a single playback deck.

---

## 💻 Tech Stack

- **Backend**: Python 3.11, FastAPI, Google ADK (Agent Development Kit), Google GenAI SDK / Vertex AI, Uvicorn, WebSockets, aiosqlite, SQLAlchemy, FFmpeg
- **Frontend**: Next.js 14 (App Router), React 18, TypeScript, Vanilla CSS (Design Tokens, Glassmorphism, Micro-animations)
- **AI Models**:
  - **Showrunner & Specialists**: Gemini 2.5 Flash (`gemini-2.5-flash`), Gemini 2.5 Pro (`gemini-2.5-pro`)
  - **Concept Art & Character Portraits**: Gemini Flash Image (`gemini-2.5-flash-image`, `gemini-3.1-flash-image`)
  - **Speech & Table Reads**: Gemini 3.1 Flash TTS (`gemini-3.1-flash-tts-preview`)
  - **Cinematic Video**: Google Veo (`veo-3.1-generate-001`) + Multi-Shot Animatic Renderer
  - **Original Music**: Google DeepMind Lyria 3 (`lyria-3-pro-preview`, `lyria-3-clip-preview`)
  - **Multimodal Video & Image Ingestion**: Gemini 2.5 Flash Vision
  - **Embeddings**: `text-embedding-004`
- **Partner & Data Integrations**:
  - **ClickHouse Cloud**: Cloud vector database for RAG continuity search
  - **ChromaDB**: Embedded vector database for local fallback
  - **SQLite / aiosqlite**: Persistent application state and ADK database session storage
- **Containerization & Deployment**:
  - Multi-stage Docker build (Node.js 20 Alpine builder + Python 3.11 Slim runtime)
  - Hosted on Antideploy / Cloud Run

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+** (Python 3.11 recommended)
- **Node.js 18+** (Node 20 recommended)
- **FFmpeg** installed and accessible in PATH (required for video/audio processing)
- **Google Cloud Project** with Vertex AI API enabled

---

### Option A: One-Click Launch (Windows)

The repository includes preconfigured launcher scripts:

1. Copy `.env.example` to `.env` in `backend/`:
   ```cmd
   copy backend\.env.example backend\.env
   ```
2. Authenticate your Google Cloud CLI:
   ```cmd
   gcloud auth application-default login
   ```
3. Double-click **`run.bat`** (or execute `.\run.bat` in PowerShell/CMD).  
   This starts the FastAPI backend on port `8000`, the Next.js dev server on port `3000`, and opens the studio in your default browser!
4. When finished, double-click **`stop.bat`** to gracefully shut down both services.

---

### Option B: Manual Setup

#### 1. Backend Setup

```bash
cd backend

# Create & activate virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux

# Authenticate with Google Cloud
gcloud auth application-default login

# Launch backend
python main.py
```

- API runs at: `http://localhost:8000`
- Interactive Swagger documentation: `http://localhost:8000/docs`

#### 2. Frontend Setup

```bash
cd frontend

# Install packages
npm install

# Start Next.js development server
npm run dev
```

- Studio UI runs at: `http://localhost:3000`

---

### Option C: Docker Container

You can build and run the full stack (FastAPI backend + statically compiled Next.js frontend) in a single unified container:

```bash
# Build the Docker image
docker build -t talevora .

# Run container with environment variables
docker run -p 8000:8000 \
  -e GCP_PROJECT_ID=your-gcp-project \
  -e GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat /path/to/sa-key.json)" \
  talevora
```

Access the studio at `http://localhost:8000`.

---

## ⚙️ Configuration & Environment Variables

Configure your settings in `backend/.env`:

```env
# ── Google Cloud Credentials ─────────────────────────────────────────
GCP_PROJECT_ID=gen-lang-client-0423661956
GCP_LOCATION=us-central1

# ── Model Configuration ──────────────────────────────────────────────
GEMINI_MAIN_MODEL=gemini-2.5-flash
GEMINI_PRO_MODEL=gemini-2.5-pro
GEMINI_TTS_MODEL=gemini-3.1-flash-tts-preview
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
GEMINI_IMAGE_GEN_MODEL=gemini-2.5-flash-image
LYRIA_MUSIC_MODEL=lyria-3-pro-preview
VEO_VIDEO_MODEL=veo-3.1-generate-001
GEMINI_EMBEDDING_MODEL=text-embedding-004

# ── ClickHouse Cloud Vector Store (Partner Integration) ──────────────
CLICKHOUSE_HOST=your-clickhouse-host.clickhouse.cloud
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=your_secure_password
CLICKHOUSE_DATABASE=default

# ── Server & Persistence ─────────────────────────────────────────────
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:3000
SQLITE_DB_PATH=./data/scriptwriter.db
```

---

## 🎬 Using the Studio

1. **Dashboard**: Click **"+ New Project"** or choose an existing screenplay. Select your genre, format (Feature, TV Pilot, Short), and dramatic structure (Three-Act, Save the Cat!, Hero's Journey).
2. **Pitch to Beat Sheet**: Enter your logline or pitch in the Writers' Room chat (e.g. *"In 2084 Neo-Detroit, an empathetic android detective uncovers an underground syndicate trading human memories"*). The **Story Architect** produces a structural beat sheet.
3. **Draft Scenes**: Select a beat and ask the **Dialogue Specialist** to draft the scene. Characters, sluglines, parentheticals, and dialogue appear in the **Script Workspace**.
4. **Enforce Continuity**: The **Continuity Checker** scans the scene against canon facts in ClickHouse Cloud.
5. **Media Lab**:
   - Upload concept art or reference videos to analyze mood, settings, and dialogue transcripts.
   - Tag reference items as **Canon** to lock in visual continuity.
6. **Bring Scenes to Life**:
   - 🎨 **Visualize**: Generate mood board concept art and character portraits.
   - 🎙️ **Table Read**: Listen to multi-speaker dramatic audio readings.
   - 🎵 **Score**: Generate an original soundtrack with Lyria 3.
   - 🎬 **Video Performance**: Render a full-motion video scene preview.
7. **Export**: Export the completed screenplay to **Fountain (`.fountain`)** or formatted plain text.

---

## 📂 Project Structure

```
Talevora/
├── backend/
│   ├── agents/                   # 9 Google ADK agent implementations
│   │   ├── showrunner.py         # Coordinator & supervisor agent
│   │   ├── story_architect.py    # Beat sheet & story framework specialist
│   │   ├── dialogue_specialist.py# Scene & dialogue writing specialist
│   │   ├── continuity_checker.py # RAG-based canon verification specialist
│   │   ├── rights_clearance.py   # Legal clearance & risk analysis agent
│   │   ├── visualizer.py         # Mood board art & character portrait generator
│   │   ├── table_read.py         # Multi-speaker TTS dramatic performance agent
│   │   ├── composer.py           # Lyria 3 cinematic soundtrack agent
│   │   └── media_analyzer.py     # Multimodal reference image & video analyzer
│   ├── tools/                    # Tool functions called by agents
│   │   ├── script_state.py       # Script State CRUD & DB operations
│   │   ├── image_gen.py          # Gemini image generation & portraits
│   │   ├── video_gen.py          # Google Veo & multi-shot animatic video engine
│   │   ├── image_analyzer.py     # Multimodal visual analysis
│   │   ├── video_analyzer.py     # Video analysis & speech transcription
│   │   ├── tts.py                # Gemini 3.1 Flash multi-speaker TTS engine
│   │   ├── music_gen.py          # Lyria 3 music composition tool
│   │   ├── rights_check.py       # Legal clearance scanner
│   │   └── vector_store.py       # Dual-write ClickHouse / ChromaDB interface
│   ├── db/                       # Persistence layer
│   │   ├── clickhouse_store.py   # ClickHouse Cloud vector store
│   │   ├── chroma_store.py       # Local ChromaDB vector fallback
│   │   ├── sqlite_store.py       # SQLite relational store for projects & scenes
│   │   └── vector_router.py      # Dual-write router & health checker
│   ├── data/frameworks/          # Three-Act, Save the Cat!, Hero's Journey templates
│   ├── models/                   # Pydantic schemas (ScriptState, API models)
│   ├── config.py                 # Configuration & environment settings
│   ├── main.py                   # FastAPI application & WebSocket router
│   └── requirements.txt          # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── app/                  # Next.js App Router (pages, layout, globals.css)
│   │   ├── components/           # Modular React components
│   │   │   ├── AppShell.tsx      # Main application shell & top-level layout
│   │   │   ├── Dashboard.tsx     # Project selection & creation dashboard
│   │   │   ├── ChatPanel.tsx     # Writers' room conversational interface
│   │   │   ├── ScriptWorkspace.tsx# Screenplay editor & Scene Experience modal
│   │   │   ├── BeatSheet.tsx     # Structural beat board component
│   │   │   ├── CharacterBible.tsx# Characters, archetypes & visual consistency
│   │   │   ├── MediaLab.tsx      # Multimodal image/video reference & canon studio
│   │   │   ├── Sidebar.tsx       # Navigation drawer & quick action shortcuts
│   │   │   ├── TopBar.tsx        # Header, project status, and export buttons
│   │   │   └── AgentStatus.tsx   # Live agent working/idle indicators
│   │   ├── hooks/useWebSocket.ts # Real-time WebSocket connection hook
│   │   └── lib/api.ts            # Typed HTTP client & API bindings
│   └── package.json
├── Dockerfile                    # Multi-stage production container build
├── run.bat                       # One-click Windows launch script
├── stop.bat                      # One-click Windows stop script
└── README.md                     # Documentation
```

---

## 📜 License

Built for the **Google Cloud Agentic Cinema Hackathon**.
