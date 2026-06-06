from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    data_dir: str = "/data/sessions"

    idle_ttl_seconds: int = 1800
    max_session_age_seconds: int = 0
    sweeper_interval_seconds: int = 45

    redis_url: str = "redis://localhost:6379/0"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "documents"

    ollama_url: str = "http://localhost:11434"
    ollama_gen_model: str = "llama3.1"
    ollama_embed_model: str = "nomic-embed-text"

    top_k: int = 5
    chunk_overlap: int = 80

    max_upload_mb: int = 50

    class Config:
        env_file = ".env"


settings = Settings()
