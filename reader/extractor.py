from typing import Any
from pydantic import BaseModel
import instructor
from openai import AsyncOpenAI
from config import LLMConfig


class MarkdownExtraction(BaseModel):
    title: str
    summary: str
    key_points: list[str]
    tags: list[str]
    metadata: dict[str, Any]


class LLMExtractor:
    def __init__(self, config: LLMConfig):
        self.config = config
        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )
        self.client = instructor.from_openai(client, mode=instructor.Mode.JSON)

    async def extract_from_markdown(self, markdown_content: str) -> MarkdownExtraction:
        return await self.client.chat.completions.create(
            model=self.config.model,
            response_model=MarkdownExtraction,
            messages=[
                {
                    "role": "system",
                    "content": "Extract structured information from the provided markdown content.",
                },
                {
                    "role": "user",
                    "content": markdown_content,
                },
            ],
            temperature=self.config.temperature,
            max_retries=3,
        )
