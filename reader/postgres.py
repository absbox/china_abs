from typing import Optional
import asyncpg
from config import PostgreSQLConfig


class PostgreSQLClient:
    def __init__(self, config: PostgreSQLConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None

    def _resolve_ssl(self):
        mode = (self.config.sslmode or "disable").lower()
        if mode in ("require", "verify-full", "verify-ca"):
            return "require"
        return False

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password or None,
            ssl=self._resolve_ssl(),
            timeout=self.config.connect_timeout,
        )

    async def fetch_markdown_files(self, limit: Optional[int] = None) -> list[dict]:
        query = (
            f"SELECT {self.config.id_column}, {self.config.column_name} "
            f"FROM {self.config.table_name}"
        )
        if limit:
            query += f" LIMIT {limit}"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        return [dict(row) for row in rows]

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()