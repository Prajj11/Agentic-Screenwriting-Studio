"""
Vector Store Router — unified interface over ClickHouse + ChromaDB.

Strategy:
  • Writes → dual-write to both stores (ClickHouse primary, Chroma backup)
  • Reads  → ClickHouse primary, ChromaDB fallback if ClickHouse unavailable
  • Gracefully degrades to ChromaDB-only when ClickHouse is not configured

All public methods are *async* so they can be awaited uniformly by tool
functions, even though the underlying stores are synchronous.
"""

from __future__ import annotations

import logging
from typing import Optional

from models.script_state import Scene, ScriptState, ContinuityFact
from db.chroma_store import ChromaStore, get_chroma_store
from db.clickhouse_store import ClickHouseVectorStore, get_clickhouse_store

logger = logging.getLogger(__name__)


class VectorStoreRouter:
    """Dual-backend vector store: ClickHouse Cloud + local ChromaDB."""

    def __init__(
        self,
        chroma: ChromaStore,
        clickhouse: ClickHouseVectorStore | None,
    ):
        self._chroma = chroma
        self._clickhouse = clickhouse
        self._ch_healthy = clickhouse is not None

    # ── Status ────────────────────────────────────────────────────────

    @property
    def backend_name(self) -> str:
        if self._ch_healthy:
            return "clickhouse"
        return "chromadb"

    def health_check(self) -> dict:
        """Return combined health status."""
        ch_status = (
            self._clickhouse.health_check()
            if self._clickhouse
            else {"status": "not_configured"}
        )
        return {
            "primary_backend": self.backend_name,
            "clickhouse": ch_status,
            "chromadb": {"status": "connected"},
        }

    # ── Indexing (dual-write) ─────────────────────────────────────────

    async def index_scene(self, project_id: str, scene: Scene):
        """Index a scene into both stores."""
        # Always write to ChromaDB (fast, local)
        try:
            self._chroma.index_scene(project_id, scene)
        except Exception as e:
            logger.error(f"ChromaDB index_scene failed: {e}")

        # Write to ClickHouse if available
        if self._clickhouse and self._ch_healthy:
            try:
                self._clickhouse.index_scene(project_id, scene)
            except Exception as e:
                logger.warning(f"ClickHouse index_scene failed (falling back): {e}")
                self._ch_healthy = False

    async def index_continuity_fact(self, project_id: str, fact: ContinuityFact):
        """Index a continuity fact into both stores."""
        try:
            self._chroma.index_continuity_fact(project_id, fact)
        except Exception as e:
            logger.error(f"ChromaDB index_continuity_fact failed: {e}")

        if self._clickhouse and self._ch_healthy:
            try:
                self._clickhouse.index_continuity_fact(project_id, fact)
            except Exception as e:
                logger.warning(f"ClickHouse index_continuity_fact failed: {e}")
                self._ch_healthy = False

    # ── Querying (ClickHouse primary, Chroma fallback) ────────────────

    async def query_relevant_scenes(
        self,
        project_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Query for relevant scenes — ClickHouse first, Chroma fallback."""
        if self._clickhouse and self._ch_healthy:
            try:
                return self._clickhouse.query_relevant_scenes(project_id, query, top_k)
            except Exception as e:
                logger.warning(f"ClickHouse query_relevant_scenes failed: {e}")
                self._ch_healthy = False

        # Fallback to ChromaDB
        return self._chroma.query_relevant_scenes(project_id, query, top_k)

    async def query_relevant_facts(
        self,
        project_id: str,
        query: str,
        top_k: int = 10,
    ) -> list[dict]:
        """Query for relevant facts — ClickHouse first, Chroma fallback."""
        if self._clickhouse and self._ch_healthy:
            try:
                return self._clickhouse.query_relevant_facts(project_id, query, top_k)
            except Exception as e:
                logger.warning(f"ClickHouse query_relevant_facts failed: {e}")
                self._ch_healthy = False

        return self._chroma.query_relevant_facts(project_id, query, top_k)

    # ── Bulk Operations ───────────────────────────────────────────────

    async def reindex_all(self, project_id: str, state: ScriptState):
        """Full re-index across both stores."""
        try:
            self._chroma.reindex_all(project_id, state)
        except Exception as e:
            logger.error(f"ChromaDB reindex_all failed: {e}")

        if self._clickhouse and self._ch_healthy:
            try:
                self._clickhouse.reindex_all(project_id, state)
            except Exception as e:
                logger.warning(f"ClickHouse reindex_all failed: {e}")
                self._ch_healthy = False


# ── Module-level singleton ────────────────────────────────────────────

_router: VectorStoreRouter | None = None


def get_vector_store() -> VectorStoreRouter:
    """Get or create the singleton vector store router."""
    global _router
    if _router is None:
        chroma = get_chroma_store()
        clickhouse = get_clickhouse_store()  # Returns None if not configured
        _router = VectorStoreRouter(chroma=chroma, clickhouse=clickhouse)

        if clickhouse:
            logger.info("Vector store router: ClickHouse (primary) + ChromaDB (backup)")
        else:
            logger.info("Vector store router: ChromaDB only (ClickHouse not configured)")

    return _router
