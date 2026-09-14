from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from config import MongoDBConfig


class MongoStore:
    def __init__(self, config: MongoDBConfig):
        self.config = config
        self.client = AsyncIOMotorClient(config.uri)
        self.collection = self.client[config.database][config.collection]

    async def store_extraction(self, postgres_id, extracted: dict) -> None:
        document = {
            "postgres_id": postgres_id,
            "extracted_at": datetime.now(timezone.utc),
            "data": extracted,
        }
        await self.collection.update_one(
            {"postgres_id": postgres_id},
            {"$set": document},
            upsert=True,
        )

    async def close(self) -> None:
        self.client.close()