"""
ChromaDB vector store for continuity checking.

Indexes scene text and continuity facts so the Continuity Checker agent
can perform RAG-based retrieval of relevant prior context.
"""

from __future__ import annotations

import logging
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from models.script_state import Scene, ScriptState, ContinuityFact

logger = logging.getLogger(__name__)


class ChromaStore:
    """Local ChromaDB vector store for continuity RAG."""

    SCENE_COLLECTION = "scenes"
    FACTS_COLLECTION = "continuity_facts"

    def __init__(self, persist_dir: str):
        self.persist_dir = persist_dir
        self._client: chromadb.ClientAPI | None = None
        self._scenes_col: chromadb.Collection | None = None
        self._facts_col: chromadb.Collection | None = None

    def connect(self):
        """Initialize the ChromaDB client and collections."""
        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._scenes_col = self._client.get_or_create_collection(
            name=self.SCENE_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self._facts_col = self._client.get_or_create_collection(
            name=self.FACTS_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB connected: {self.persist_dir}")

    def _get_project_prefix(self, project_id: str) -> str:
        return f"{project_id}_"

    # ── Scene Indexing ────────────────────────────────────────────────

    def index_scene(self, project_id: str, scene: Scene):
        """Index a scene's full text and metadata into the vector store."""
        scene_text = scene.to_screenplay_text()
        if not scene_text.strip():
            scene_text = f"Scene {scene.scene_number}: {scene.slugline} - {scene.action_lines}"

        doc_id = f"{self._get_project_prefix(project_id)}scene_{scene.scene_number}"

        # Upsert the scene document
        self._scenes_col.upsert(
            ids=[doc_id],
            documents=[scene_text],
            metadatas=[{
                "project_id": project_id,
                "scene_number": scene.scene_number,
                "slugline": scene.slugline or "",
                "characters": ", ".join(scene.characters),
                "status": scene.status.value if hasattr(scene.status, 'value') else str(scene.status),
                "location": scene.location or "",
            }],
        )
        logger.debug(f"Indexed scene {scene.scene_number} for project {project_id}")

    def index_continuity_fact(self, project_id: str, fact: ContinuityFact):
        """Index a continuity fact for retrieval."""
        doc_id = f"{self._get_project_prefix(project_id)}fact_{fact.fact_id}"

        self._facts_col.upsert(
            ids=[doc_id],
            documents=[fact.description],
            metadatas=[{
                "project_id": project_id,
                "fact_id": fact.fact_id,
                "scene_established": fact.scene_established,
                "category": fact.category.value if hasattr(fact.category, 'value') else str(fact.category),
                "characters": ", ".join(fact.characters_involved),
            }],
        )

    # ── Querying ──────────────────────────────────────────────────────

    def query_relevant_scenes(
        self,
        project_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Retrieve the most relevant prior scenes for a given query.
        Used by the Continuity Checker to find potential conflicts.
        """
        if not self._scenes_col or self._scenes_col.count() == 0:
            return []

        results = self._scenes_col.query(
            query_texts=[query],
            n_results=min(top_k, self._scenes_col.count()),
            where={"project_id": project_id},
        )

        matches = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0
                matches.append({
                    "scene_text": doc,
                    "scene_number": meta.get("scene_number", 0),
                    "slugline": meta.get("slugline", ""),
                    "characters": meta.get("characters", ""),
                    "relevance_score": 1 - distance,  # Convert distance to similarity
                })

        return matches

    def query_relevant_facts(
        self,
        project_id: str,
        query: str,
        top_k: int = 10,
    ) -> list[dict]:
        """Retrieve the most relevant continuity facts for a given query."""
        if not self._facts_col or self._facts_col.count() == 0:
            return []

        results = self._facts_col.query(
            query_texts=[query],
            n_results=min(top_k, self._facts_col.count()),
            where={"project_id": project_id},
        )

        matches = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0
                matches.append({
                    "fact_description": doc,
                    "fact_id": meta.get("fact_id", ""),
                    "scene_established": meta.get("scene_established", 0),
                    "category": meta.get("category", ""),
                    "characters": meta.get("characters", ""),
                    "relevance_score": 1 - distance,
                })

        return matches

    # ── Bulk Operations ───────────────────────────────────────────────

    def reindex_all(self, project_id: str, state: ScriptState):
        """
        Full re-indexing of all scenes and facts for a project.
        Called when major changes happen (e.g., scene reorder, bulk edit).
        """
        # Clear existing entries for this project
        self._clear_project(project_id)

        # Re-index all scenes
        for scene in state.scenes:
            self.index_scene(project_id, scene)

        # Re-index all continuity facts
        for fact in state.continuity_log:
            self.index_continuity_fact(project_id, fact)

        logger.info(
            f"Re-indexed project {project_id}: "
            f"{len(state.scenes)} scenes, {len(state.continuity_log)} facts"
        )

    def _clear_project(self, project_id: str):
        """Remove all entries for a project from both collections."""
        prefix = self._get_project_prefix(project_id)

        # Get and delete scene entries
        try:
            existing = self._scenes_col.get(where={"project_id": project_id})
            if existing and existing["ids"]:
                self._scenes_col.delete(ids=existing["ids"])
        except Exception:
            pass

        # Get and delete fact entries
        try:
            existing = self._facts_col.get(where={"project_id": project_id})
            if existing and existing["ids"]:
                self._facts_col.delete(ids=existing["ids"])
        except Exception:
            pass


# ── Module-level singleton ────────────────────────────────────────────

_store: ChromaStore | None = None


def get_chroma_store() -> ChromaStore:
    """Get or create the singleton ChromaDB store."""
    global _store
    if _store is None:
        from config import settings
        _store = ChromaStore(settings.chroma_persist_dir)
        _store.connect()
    return _store
