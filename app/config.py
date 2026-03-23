from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    openrouter_api_key: str
    model: str = "deepseek/deepseek-chat"
    chroma_path: str = "./data/chroma"
    embedding_model: str = "BAAI/bge-m3"
    top_k_chunks: int = 3
    similarity_threshold: float = 1.0   # L2 distance cutoff; lower = stricter
    chunk_overlap: int = 1              # paragraphs to overlap between chunks
    max_history_turns: int = 6
    prompt_version: str = "v1"
    postgres_dsn: str = "postgresql://user:password@localhost:5432/skyview"
    log_to_file: bool = False


settings = Settings()
