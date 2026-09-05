"""Centralized settings, shared by the ingestion pipeline and the MCP server.

Values are loaded from environment variables / a local .env file so secrets
(e.g. DB_PASSWORD) never need to be hard-coded.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Source documents ---
    source_documents_dir: Path = PROJECT_ROOT / "UC Davis AI"

    # --- Embeddings ---
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Semantic chunking (ingestion only) ---
    semantic_chunker_breakpoint_threshold_type: str = "percentile"
    semantic_chunker_buffer_size: int = 1
    semantic_chunker_min_chunk_size: int = 100

    # --- Vector store (Postgres / pgvector) ---
    # Kept identical to the sibling "UAC" project's default so this MCP server
    # can be pointed at that project's existing Cloud SQL instance and reuse
    # the already-built collection instead of re-ingesting.
    vector_collection_name: str = "uc_davis_ai"

    # --- Retrieval / reranking ---
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    retrieval_top_k: int = 20
    rerank_top_n: int = 5

    # --- MCP server ---
    mcp_server_host: str = "127.0.0.1"
    mcp_server_port: int = 8080
    # Run the bulk ingestion of the bundled PDFs at startup if the collection
    # is empty. Set false when the DB is seeded out-of-band (e.g. a one-off
    # job, or a shared collection that's already populated).
    seed_on_startup: bool = True

    # --- Web search ---
    web_search_region: str = "us-en"
    web_search_max_results: int = 5

    # --- Database (Cloud SQL Postgres) ---
    # Set DATABASE_URL directly for local dev. In production,
    # CLOUD_SQL_CONNECTION_NAME is set instead and the URL is built to use the
    # Unix socket Cloud Run mounts at /cloudsql/<connection-name>.
    database_url: str = ""
    cloud_sql_connection_name: str = ""
    db_user: str = "mcp-app"
    db_password: str = ""
    db_name: str = "mcp"

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.cloud_sql_connection_name:
            socket_dir = f"/cloudsql/{self.cloud_sql_connection_name}"
            return (
                f"postgresql+psycopg://{self.db_user}:{self.db_password}@/"
                f"{self.db_name}?host={socket_dir}"
            )
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}@localhost:5432/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide Settings instance."""
    return Settings()
