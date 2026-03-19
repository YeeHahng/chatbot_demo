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
    embedding_model: str = "paraphrase-multilingual-mpnet-base-v2"
    top_k_chunks: int = 3
    max_history_turns: int = 6
    prompt_version: str = "v1"


settings = Settings()
