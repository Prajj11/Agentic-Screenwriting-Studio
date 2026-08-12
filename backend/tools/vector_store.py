"""
Vector store tool functions for the Continuity Checker agent.

Wraps the VectorStoreRouter (ClickHouse + ChromaDB) for RAG-based
retrieval of relevant prior scenes and continuity facts.
"""

from __future__ import annotations

import json
import logging

from db.vector_router import get_vector_store

logger = logging.getLogger(__name__)


async def query_relevant_context(project_id: str, query: str, top_k: int = 5) -> str:
    """
    Query the vector store for scenes and facts relevant to the given text.
    Used by the Continuity Checker to find potential conflicts.
    
    Returns a JSON object with 'relevant_scenes' and 'relevant_facts'.
    """
    store = get_vector_store()

    scenes = await store.query_relevant_scenes(project_id, query, top_k=top_k)
    facts = await store.query_relevant_facts(project_id, query, top_k=top_k * 2)

    return json.dumps({
        "relevant_scenes": scenes,
        "relevant_facts": facts,
        "query": query,
        "total_results": len(scenes) + len(facts),
        "backend": store.backend_name,
    }, indent=2)


async def get_scene_context_for_continuity(project_id: str, scene_text: str) -> str:
    """
    Get all relevant prior context for a continuity check on a new/updated scene.
    This is the main entry point the Continuity Checker uses.
    
    Returns prior scenes and facts that might conflict with the given scene text.
    """
    store = get_vector_store()

    # Query for relevant scenes
    scenes = await store.query_relevant_scenes(project_id, scene_text, top_k=8)

    # Query for relevant facts
    facts = await store.query_relevant_facts(project_id, scene_text, top_k=15)

    # Also extract key entities from the scene text for targeted fact lookup
    # (character names, locations, props mentioned)
    # This is a simple heuristic — the LLM agent will do deeper analysis
    context = {
        "prior_scenes": scenes,
        "established_facts": facts,
        "backend": store.backend_name,
        "advice": (
            "Cross-reference the new scene against ALL prior scenes and facts above. "
            "Check for contradictions in: character locations, timeline consistency, "
            "character knowledge (what they should/shouldn't know), prop continuity, "
            "established world rules, and character personality/voice consistency."
        ),
    }

    return json.dumps(context, indent=2)


async def execute_clickhouse_mcp_query(project_id: str, query: str) -> str:
    """
    Execute an analytical search or vector query against ClickHouse Cloud via the 
    ClickHouse MCP Server (mcp-clickhouse) integration.
    
    Used by Continuity Checker and Showrunner for real-time script canon search.
    """
    store = get_vector_store()
    if not store._clickhouse or not store._ch_healthy:
        return json.dumps({
            "status": "not_configured",
            "message": "ClickHouse is not configured or unreachable. Using local ChromaDB fallback.",
            "backend": store.backend_name,
        })
    try:
        scenes = store._clickhouse.query_relevant_scenes(project_id, query, top_k=5)
        facts = store._clickhouse.query_relevant_facts(project_id, query, top_k=5)
        return json.dumps({
            "status": "success",
            "mcp_server": "mcp-clickhouse",
            "relevant_scenes": scenes,
            "relevant_facts": facts,
            "backend": "clickhouse",
        }, indent=2)
    except Exception as e:
        logger.error(f"ClickHouse MCP query failed: {e}")
        return json.dumps({
            "status": "error",
            "mcp_server": "mcp-clickhouse",
            "error": str(e),
            "backend": store.backend_name,
        })

