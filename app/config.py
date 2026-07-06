from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM
    anthropic_api_key: str = ""
    router_model: str = "claude-haiku-4-5-20251001"
    sql_model: str = "claude-sonnet-5"
    synthesis_model: str = "claude-sonnet-5"

    # Database
    database_url: str = "sqlite:///./data/northwind_retail.db"
    database_url: str = "sqlite:///./data/northwind_retail.db"

    # Vector store
    chroma_persist_dir: str = "./vector_store"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Auth
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    demo_username: str = "analyst"
    demo_password: str = "changeme123"

    # SQL safety limits
    sql_max_rows: int = 500
    sql_timeout_seconds: int = 10


settings = Settings()

print("Anthropic key loaded:", bool(settings.anthropic_api_key))
print("Key length:", len(settings.anthropic_api_key))
