# 🎬 Agentic Screenwriting Studio

A multi-agent AI system powered by **Google ADK** and **Gemini** that acts as a virtual writers' room for screenwriters. The system takes a writer from a one-line pitch to a continuity-checked, performable screenplay.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              🎬 Showrunner (Coordinator)             │
│         Routes tasks, owns Script State             │
├──────┬──────┬──────┬──────┬──────┬──────┬──────────┤
│  📐  │  ✍️  │  🔍  │  🌐  │  ⚖️  │  🎨  │   🎙️    │
│Story │Dial. │Cont. │Resrch│Rights│Visua │Table     │
│Arch. │Spec. │Check │Agent │Clear │lizer │Read      │
└──────┴──────┴──────┴──────┴──────┴──────┴──────────┘
```

### Agents

| Agent | Role | Integration |
|-------|------|-------------|
| **Showrunner** | Coordinator — routes tasks, enforces quality gates | Google ADK |
| **Story Architect** | Generates beat sheets from pitches | Gemini + Framework templates |
| **Dialogue Specialist** | Drafts full scenes with dialogue | Gemini + Character Bible |
| **Continuity Checker** | RAG-based consistency verification | ChromaDB + Gemini |
| **Research Agent** | Live fact-checking | Parallel API |
| **Rights & Clearance** | Legal clearance analysis | Gemini (simulated watsonx) |
| **Visualizer** | Concept art / mood boards | Imagen 3 |
| **Table Read** | Multi-speaker audio performance | Gemini TTS |

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Gemini API key ([Get one here](https://aistudio.google.com/))
- Parallel API key (optional, for Research Agent)

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env and add your GEMINI_API_KEY

# Run the backend
python main.py
```

The backend starts at `http://localhost:8000`. Swagger UI at `http://localhost:8000/docs`.

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run the dev server
npm run dev
```

The frontend starts at `http://localhost:3000`.

### 3. Use the Studio

1. Open `http://localhost:3000`
2. Enter a pitch in the Writers' Room panel (e.g., "A burned-out detective in 1920s Chicago discovers their partner is working for the mob")
3. Click "📐 Beat Sheet" to generate the story structure
4. Click "✍️ Draft Scene" to write scenes
5. Use the other agents as needed

## Key Features

### Forced Continuity Gate
No scene can be marked as "final" until the Continuity Checker has verified it against all established canon. This is enforced programmatically — not optional.

### RAG-Based Continuity
ChromaDB indexes every scene and continuity fact as it's added. The Continuity Checker performs vector search to find potential conflicts.

### Multi-Speaker Table Reads
Gemini TTS performs scenes aloud with distinct character voices. Handles the 2-speaker API limit by intelligently batching dialogue.

### Live Fact-Checking
The Research Agent uses the Parallel API for real-time web research, letting writers verify historical and technical details without leaving the app.

## Tech Stack

- **Backend**: Python, FastAPI, Google ADK, SQLite, ChromaDB
- **Frontend**: Next.js 14, TypeScript, Vanilla CSS
- **AI**: Gemini 2.5 Flash/Pro, Imagen 3, Gemini TTS
- **Research**: Parallel API
- **State**: SQLite (persistent) + ChromaDB (vector search)

## Project Structure

```
├── backend/
│   ├── agents/          # 8 ADK agent definitions
│   ├── tools/           # Tool functions for agents
│   ├── models/          # Pydantic data models
│   ├── db/              # SQLite + ChromaDB stores
│   ├── data/frameworks/ # Story structure templates
│   ├── main.py          # FastAPI entry point
│   └── config.py        # Settings
├── frontend/
│   └── src/
│       ├── app/         # Next.js pages + CSS
│       ├── lib/         # API client
│       └── hooks/       # WebSocket hook
└── README.md
```

## License

Built for the Google Cloud Hackathon 2026.
