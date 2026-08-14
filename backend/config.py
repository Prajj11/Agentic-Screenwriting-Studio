"""
Central configuration for the Agentic Screenwriting Studio backend.
Loads settings from environment variables / .env file.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file from the backend directory
_backend_dir = Path(__file__).parent
load_dotenv(_backend_dir / ".env")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── API Keys & GCP Credentials ──────────────────────────────────────────────────────
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    parallel_api_key: str = ""

    # ── Grafana ───────────────────────────────────────────────────────
    grafana_api_key: str = ""
    grafana_url: str = ""

    # ── ClickHouse (Partner Integration) ──────────────────────────────
    clickhouse_host: str = ""
    clickhouse_port: int = 8443
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "default"

    @property
    def clickhouse_enabled(self) -> bool:
        """True when ClickHouse is configured with a real hostname."""
        return bool(
            self.clickhouse_host
            and self.clickhouse_host != "your-clickhouse-host.clickhouse.cloud"
            and self.clickhouse_password
        )

    # ── Model Names ───────────────────────────────────────────────────
    gemini_main_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"
    gemini_tts_model: str = "gemini-2.5-flash-tts"
    gemini_image_model: str = "imagen-3.0-generate-002"
    gemini_image_gen_model: str = "gemini-2.0-flash-exp"
    gemini_embedding_model: str = "text-embedding-004"
    lyria_music_model: str = "lyria-3-pro-preview"
    lyria_music_clip_model: str = "lyria-3-clip-preview"

    # ── Server ────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:3000"

    # ── Database ──────────────────────────────────────────────────────
    sqlite_db_path: str = str(_backend_dir / "data" / "scriptwriter.db")
    chroma_persist_dir: str = str(_backend_dir / "data" / "chroma_db")

    # ── Output Directories ────────────────────────────────────────────
    output_images_dir: str = str(_backend_dir / "output" / "images")
    output_audio_dir: str = str(_backend_dir / "output" / "audio")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def ensure_directories(self):
        """Create all required output and data directories."""
        for dir_path in [
            self.sqlite_db_path.rsplit("/", 1)[0] if "/" in self.sqlite_db_path else "data",
            self.output_images_dir,
            self.output_audio_dir,
        ]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)


# ── Gemini Safety Settings ────────────────────────────────────────────
# Configured to allow creative content while blocking genuinely harmful output.
SAFETY_SETTINGS = {
    "HARM_CATEGORY_HARASSMENT": "BLOCK_ONLY_HIGH",
    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_ONLY_HIGH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_ONLY_HIGH",
}

# ── Singleton ─────────────────────────────────────────────────────────
settings = Settings()
settings.ensure_directories()
