"""
Rights & Clearance tool.

Uses Gemini with a specialized legal-analysis prompt to flag:
- Real brand names
- Quoted song lyrics
- References to real public figures
- Potential trademark issues

Designed as a swappable interface.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


CLEARANCE_SYSTEM_PROMPT = """You are an expert entertainment industry legal clearance analyst. 
Your job is to review screenplay scene text and identify potential legal/clearance issues 
that a real studio legal department would flag before production.

Analyze the following scene text and identify ALL instances of:

1. **BRAND NAMES**: Any real company, product, or brand names mentioned (e.g., "Coca-Cola", "iPhone", "BMW")
2. **SONG LYRICS**: Any quoted song lyrics, even partial lines
3. **PUBLIC FIGURES**: References to real, identifiable public figures (living or deceased)
4. **TRADEMARKED PHRASES**: Slogans, catchphrases, or trademarked terms
5. **COPYRIGHTED WORKS**: References to specific books, movies, TV shows, or artworks
6. **SENSITIVE CONTENT**: Content that could be defamatory or invade privacy of real persons

For EACH issue found, provide:
- The exact text flagged
- The type of issue (brand_name, song_lyrics, public_figure, trademark, copyright, defamation)
- Severity: low (minor, easily fixable), medium (needs legal review), high (likely requires clearance), critical (must be removed or changed)
- A brief explanation of the risk
- A suggested safe rewrite that preserves the scene's intent

If NO issues are found, respond with an empty array.

Respond ONLY with a valid JSON array of objects with these keys:
flagged_text, issue_type, severity, explanation, suggested_rewrite

Example response:
[
  {
    "flagged_text": "She sipped her Coca-Cola",
    "issue_type": "brand_name",
    "severity": "medium",
    "explanation": "Real brand name used without clearance. Could imply endorsement.",
    "suggested_rewrite": "She sipped her cola"
  }
]
"""


async def check_clearance(scene_text: str) -> str:
    """
    Analyze a scene for rights/clearance issues.
    
    This uses Gemini with a specialized prompt to identify:
    - Real brand names
    - Song lyrics
    - Public figures
    - Trademark issues
    
    Args:
        scene_text: The full text of the scene to analyze.
    
    Returns:
        JSON with a list of clearance flags and their suggested rewrites.
    """
    from config import settings

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location
        )

        response = client.models.generate_content(
            model=settings.gemini_main_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"Analyze this screenplay scene for clearance issues:\n\n{scene_text}")]
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=CLEARANCE_SYSTEM_PROMPT,
                temperature=0.1,  # Low temperature for analytical precision
                response_mime_type="application/json",
            ),
        )

        # Parse the response
        response_text = response.text.strip()

        # Try to parse as JSON
        try:
            flags = json.loads(response_text)
            if not isinstance(flags, list):
                flags = [flags]
        except json.JSONDecodeError:
            # If the model didn't return valid JSON, wrap it
            flags = [{
                "flagged_text": "Parse error",
                "issue_type": "unknown",
                "severity": "low",
                "explanation": response_text,
                "suggested_rewrite": "",
            }]

        return json.dumps({
            "success": True,
            "scene_analyzed": True,
            "flags": flags,
            "total_issues": len(flags),
            "has_critical": any(f.get("severity") == "critical" for f in flags),
            "has_high": any(f.get("severity") == "high" for f in flags),
            "integration": "gemini",
        }, indent=2)

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "google-genai SDK not installed. Run: pip install google-genai",
        })
    except Exception as e:
        logger.error(f"Clearance check error: {e}")
        return json.dumps({
            "success": False,
            "error": str(e),
        })
