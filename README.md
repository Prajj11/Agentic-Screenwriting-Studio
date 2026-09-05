# 🎬 Talevora — Agentic Screenwriting Studio

> **Built for the Google Cloud Agentic Cinema Hackathon** 🏆

A multi-agent AI system powered by **Google ADK** and **Gemini** that acts as a virtual writers' room for screenwriters. The system takes a writer from a one-line pitch to a continuity-checked, performable screenplay complete with cinematic concept art and original musical scores.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  🎬 Showrunner (Coordinator)                 │
│             Routes tasks, owns Script State                 │
├──────┬──────┬──────┬──────┬──────┬──────┬──────────┬────────┤
│  📐  │  ✍️  │  🔍  │  🌐  │  ⚖️  │  🎨  │   🎙️    │   🎵   │
│Story │Dial. │Cont. │Resrch│Rights│Visua │Table     │Composer│
│Arch. │Spec. │Check │Agent │Clear │lizer │Read      │        │
└──────┴──────┴──────┴──────┴──────┴──────┴──────────┴────────┘
```

### Agents

| Agent | Role | Integration |
|-------|------|-------------|
| **Showrunner** | Coordinator — routes tasks, enforces quality gates | Google ADK |
| **Story Architect** | Generates beat sheets from pitches | Gemini + Framework templates |
| **Dialogue Specialist** | Drafts full scenes with dialogue | Gemini + Character Bible |
| **Continuity Checker** | RAG-based consistency verification | ClickHouse Cloud + ChromaDB |
| **Rights & Clearance** | Legal clearance analysis | Gemini |
| **Visualizer** | Concept art / mood boards | Gemini 3.1 Flash Image |
| **Table Read** | Multi-speaker audio performance | Gemini 3.1 Flash TTS |
| **Composer** | Original cinematic soundtrack generation | Lyria 3 |

## ✨ Key Features

### 🛑 Forced Continuity Gate
No scene can be marked as "final" until the Continuity Checker has verified it against all established canon. This is enforced programmatically — not optional.

### 🧠 RAG-Based Continuity
The backend utilizes a **Dual-Write Vector Store** (ClickHouse Cloud primary, ChromaDB local fallback). Every scene and continuity fact is indexed as it's added. The Continuity Checker performs vector search using Gemini `text-embedding-004` to find potential conflicts.

### 🎭 Multi-Speaker Table Reads
Gemini 3.1 Flash TTS (`gemini-3.1-flash-tts-preview`) performs scenes aloud with distinct character voices and embedded emotional tags. Handles the 2-speaker API limit by intelligently batching dialogue chunks.

### 🎵 Cinematic Original Scores
The Composer agent analyzes the emotional beat of a finalized scene and generates a production-ready cinematic soundtrack using the **Lyria 3** model.

### 🎨 Responsive UI/UX
A completely redesigned, modular React/Next.js frontend featuring responsive flexbox layouts, a dynamic chat experience, and a dedicated Scene Experience modal for viewing scripts alongside their generated media.

## 💻 Tech Stack

- **Backend**: Python, FastAPI, Google ADK (Agent Development Kit)
- **Frontend**: Next.js 14, TypeScript, Vanilla CSS
- **AI Models**: Gemini 2.5 Flash/Pro, Gemini 3.1 Flash TTS, Gemini 3.1 Flash Image, Lyria 3, text-embedding-004
- **Partner Integrations**: ClickHouse Cloud (Vector DB)
- **State/Persistence**: SQLite (Persistent App State) + ClickHouse (Vector RAG)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Google Cloud Project with Vertex AI enabled
- ClickHouse Cloud instance (optional, falls back to local ChromaDB)

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
# Edit .env and authenticate your Google Cloud CLI
gcloud auth application-default login

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
5. Once a scene is finalized, use the **Visualizer**, **Table Read**, and **Composer** to bring it to life!

## 🌍 Remote Setup (Running on Another Machine)

If a team member needs to run the Agentic Screenwriting Studio on their own computer, follow these steps:

1. **Share the Code**: Push this folder to a GitHub repository and have them clone it (or zip the folder and send it to them).
2. **Google Cloud Access**: Because the app connects directly to Google Cloud Vertex AI using your local account credentials, they will need access to your GCP project:
   - They need to install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) on their computer.
   - Open a terminal and run `gcloud auth application-default login`.
   - They must log in with a Google account that has permission to access your Google Cloud Project (`gen-lang-client-0423661956`).
3. **Run It**: Once they are authenticated, they just double-click `run.bat` on their computer exactly like you do to start both servers.

## 📂 Project Structure

```
├── backend/
│   ├── agents/          # 9 ADK agent definitions (Showrunner + 8 Specialists)
│   ├── tools/           # Tool functions for agents
│   ├── models/          # Pydantic data models
│   ├── db/              # ClickHouse + ChromaDB stores & SQLite session state
│   ├── data/frameworks/ # Story structure templates
│   ├── main.py          # FastAPI entry point
│   └── config.py        # Settings loader
├── frontend/
│   └── src/
│       ├── app/         # Next.js pages + CSS
│       ├── components/  # React components
│       ├── lib/         # API client
│       └── hooks/       # WebSocket hook
└── README.md
```

## 📜 License

Built for the **Google Cloud Agentic Cinema Hackathon**.
