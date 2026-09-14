import asyncio
import logging
from config import load_config
from postgres import PostgreSQLClient
from mongo import MongoStore
from extractor import LLMExtractor

logger = logging.getLogger(__name__)


async def main():
    config = load_config()
    logging.basicConfig(level=getattr(logging, config.log_level))

    pg = PostgreSQLClient(config.postgresql)
    mongo = MongoStore(config.mongodb)
    extractor = LLMExtractor(config.llm)

    await pg.connect()

    try:
        files = await pg.fetch_markdown_files(config.fetch_limit)
        logger.info(f"Fetched {len(files)} markdown files from PostgreSQL")

        for file in files:
            record_id = file[config.postgresql.id_column]
            content = file[config.postgresql.column_name]
            logger.info(f"Processing record ID: {record_id}")

            try:
                result = await extractor.extract_from_markdown(content)
                await mongo.store_extraction(record_id, result.model_dump())
                logger.info(f"Stored extraction for record ID: {record_id} in MongoDB")
            except Exception as e:
                logger.error(f"Failed to process record ID {record_id}: {e}")

    finally:
        await pg.close()
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(main())