"""
Parallel API wrapper tool for the Research Agent.

Uses the Parallel Search/Task APIs to perform live web research,
fact-checking, and citation retrieval.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Parallel API configuration
PARALLEL_API_BASE = "https://api.parallel.ai/v1"


def _get_api_key() -> str:
    """Get the Parallel API key from environment."""
    key = os.environ.get("PARALLEL_API_KEY", "")
    if not key:
        from config import settings
        key = settings.parallel_api_key
    return key


async def research_fact(query: str) -> str:
    """
    Research a factual claim using the Parallel Search API.
    Returns verified information with citations.
    
    Use this to fact-check historical details, technical claims,
    period-accurate information, or any verifiable statement in a scene.
    
    Args:
        query: The factual question or claim to research.
              Example: "Would a 1920s Chicago detective carry a Colt M1911?"
    
    Returns:
        JSON with research findings, citations, and confidence level.
    """
    api_key = _get_api_key()

    if not api_key:
        # Fallback: return a simulated response for demo purposes
        return json.dumps({
            "status": "simulated",
            "query": query,
            "findings": (
                f"[Parallel API key not configured] "
                f"Unable to perform live research for: '{query}'. "
                "Please configure PARALLEL_API_KEY in your .env file."
            ),
            "citations": [],
            "note": "This is a placeholder response. Configure PARALLEL_API_KEY for live research.",
        })

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{PARALLEL_API_BASE}/search",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "num_results": 5,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract and format results
            results = data.get("results", [])
            findings = []
            citations = []

            for r in results:
                findings.append(r.get("snippet", r.get("text", "")))
                if r.get("url"):
                    citations.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("snippet", "")[:200],
                    })

            return json.dumps({
                "status": "success",
                "query": query,
                "findings": "\n\n".join(findings) if findings else "No relevant results found.",
                "citations": citations,
                "result_count": len(results),
            }, indent=2)

    except httpx.HTTPStatusError as e:
        logger.error(f"Parallel API HTTP error: {e.response.status_code} - {e.response.text}")
        return json.dumps({
            "status": "error",
            "query": query,
            "error": f"API error: {e.response.status_code}",
        })
    except Exception as e:
        logger.error(f"Parallel API error: {e}")
        return json.dumps({
            "status": "error",
            "query": query,
            "error": str(e),
        })


async def deep_research(topic: str, context: str = "") -> str:
    """
    Perform deep, multi-step research using the Parallel Task API.
    Use this for complex research that requires multiple search queries
    and synthesis of information from multiple sources.
    
    Args:
        topic: The research topic.
        context: Additional context about what the research is for.
    
    Returns:
        JSON with comprehensive research findings.
    """
    api_key = _get_api_key()

    if not api_key:
        return json.dumps({
            "status": "simulated",
            "topic": topic,
            "findings": (
                f"[Parallel API key not configured] "
                f"Unable to perform deep research for: '{topic}'. "
                "Please configure PARALLEL_API_KEY in your .env file."
            ),
        })

    try:
        research_input = f"Research topic: {topic}"
        if context:
            research_input += f"\nContext: {context}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{PARALLEL_API_BASE}/task",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": research_input,
                    "processor": "standard",
                },
            )
            response.raise_for_status()
            data = response.json()

            return json.dumps({
                "status": "success",
                "topic": topic,
                "findings": data.get("output", data.get("result", "No findings returned.")),
                "interaction_id": data.get("interaction_id", ""),
            }, indent=2)

    except Exception as e:
        logger.error(f"Parallel deep research error: {e}")
        return json.dumps({
            "status": "error",
            "topic": topic,
            "error": str(e),
        })
