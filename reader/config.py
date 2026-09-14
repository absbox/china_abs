from typing import Optional
from pydantic_settings import BaseSettings


class PostgreSQLConfig(BaseSettings):
    host: str = "localhost"
    port: int = 5432
    database: str = "reader"
    user: str = "postgres"
    password: str = ""
    sslmode: str = "disable"
    connect_timeout: int = 10
    table_name: str = "markdown_files"
    column_name: str = "content"
    id_column: str = "id"


class MongoDBConfig(BaseSettings):
    uri: str = "mongodb://localhost:27017"
    database: str = "reader"
    collection: str = "extracted_documents"


class LLMConfig(BaseSettings):
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.0
    max_tokens: Optional[int] = None


class AppConfig(BaseSettings):
    postgresql: PostgreSQLConfig = PostgreSQLConfig()
    mongodb: MongoDBConfig = MongoDBConfig()
    llm: LLMConfig = LLMConfig()
    log_level: str = "INFO"

    fetch_limit: Optional[int] = None

    model_config = {"env_prefix": "APP_", "env_nested_delimiter": "__"}


def load_config() -> AppConfig:
    return AppConfig()