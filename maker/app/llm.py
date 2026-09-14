import os
from typing import Optional

import instructor
import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from .extracter import QUESTION_MODELS, route_function

load_dotenv()

# OpenAI-compatible API base URLs, keyed by model provider name.
PROVIDER_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "openai": "https://api.openai.com/v1",
    "claude": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "kimi": "https://api.moonshot.cn/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "minimax": "https://api.minimax.chat/v1",
    "baichuan": "https://api.baichuan-ai.com/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "mistral": "https://api.mistral.ai/v1",
}

# Default model per provider, used when neither an explicit ``model`` argument
# nor ``LLM_MODEL_NAME`` is given.  Providers not listed fall back to
# ``<provider>-flash``.
PROVIDER_MODELS: dict[str, str] = {
    "deepseek": "deepseek-flash",
    "qwen": "qwen-flash",
}


def get_provider_url(provider: str) -> Optional[str]:
    """Return the OpenAI-compatible base URL for a model provider.

    Provider names are matched case-insensitively.  ``None`` is returned
    when the provider is unknown.
    """
    if not provider:
        return None
    return PROVIDER_URLS.get(provider.strip().lower())


def get_model_name(provider: str, model: Optional[str] = None) -> str:
    """Resolve the model name for a provider.

    Precedence: explicit ``model`` argument, then ``LLM_MODEL_NAME``, then the
    provider's entry in :data:`PROVIDER_MODELS`, then ``<provider>-flash``.
    """
    return (
        model
        or os.getenv("LLM_MODEL_NAME")
        or PROVIDER_MODELS.get(provider.strip().lower(), f"{provider.strip().lower()}-flash")
    )


def understand(
    provider: str, question_key: str, markdown: str, model: Optional[str] = None
) -> BaseModel:
    """Extract structured data from a markdown report via the LLM.

    Args:
        provider: model provider, must be a key of ``PROVIDER_URLS``.
        question_key: question name, must be a key of ``QUESTION_MODELS``.
        markdown: the report content parsed to markdown.
        model: model name override.  When omitted, ``LLM_MODEL_NAME`` is used,
            then the provider's entry in :data:`PROVIDER_MODELS`
            (e.g. ``deepseek-flash``, ``qwen-flash``), then ``<provider>-flash``.

    The role and pydantic model registered for ``question_key`` are used:
    the role (e.g. 债券簿记人) is injected as the extraction persona, and the
    model's field descriptions embed the extraction rules from the
    corresponding question.  The API key is read from ``<PROVIDER>_API_KEY``
    (e.g. ``DEEPSEEK_API_KEY``) falling back to ``LLM_API_KEY``.
    """
    url = get_provider_url(provider)
    if url is None:
        raise ValueError(f"Unknown provider: {provider!r}")

    role, model_class = QUESTION_MODELS.get(question_key, (None, None))
    if model_class is None:
        raise ValueError(f"Unknown question key: {question_key!r}")

    api_key = os.getenv(f"{provider.strip().upper()}_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        raise ValueError(
            f"Missing API key for provider {provider!r}: set "
            f"{provider.upper()}_API_KEY or LLM_API_KEY"
        )

    model_name = get_model_name(provider, model)

    client = instructor.from_openai(OpenAI(base_url=url, api_key=api_key))

    return client.chat.completions.create(
        model=model_name,
        response_model=model_class,
        messages=[
            {
                "role": "system",
                "content": (
                    f"你是一名{role}，擅长解读资产证券化报告。"
                    "严格按照给定的字段定义提取结构化数据，"
                    "不要添加额外说明，找不到的信息填入null。"
                ),
            },
            {
                "role": "user",
                "content": "下面是需要分析的报告内容：\n\n" + markdown,
            },
        ],
    )


def understand_report(
    report_name: str,
    provider: str = "qwen",
    question: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseModel:
    """Extract structured data from a report stored in the ``mineru`` table.

    Looks the report up by name in the local ``deal-library`` PostgreSQL
    database (``public.mineru``), routes it to the matching question model via
    :func:`app.extracter.route_function`, and extracts structured data with
    :func:`understand`.

    Args:
        report_name: report key in ``mineru`` (with or without the ``.pdf``
            extension).
        provider: LLM provider, a key of :data:`PROVIDER_URLS`; defaults to
            ``"qwen"`` (Aliyun DashScope), whose default model is
            ``qwen-flash``.  Use ``"deepseek"`` for ``deepseek-flash``.
        question: question key (a key of ``QUESTION_MODELS``).  When provided
            it is used directly and the report name is *not* routed via
            :func:`app.extracter.route_function`.
        model: model name override, forwarded to :func:`understand`.

    Returns:
        An instance of the pydantic model registered for the routed question.

    Raises:
        ValueError: if the report has no markdown in ``mineru`` or its name
            matches no known question type.
    """
    candidates = {report_name}
    if report_name.lower().endswith(".pdf"):
        candidates.add(report_name[:-4])
    else:
        candidates.add(report_name + ".pdf")

    with psycopg.connect(
        host=os.getenv("DATABASE_HOST", "localhost"),
        port=int(os.getenv("DATABASE_PORT", "5432")),
        user=os.getenv("DATABASE_USER"),
        password=os.getenv("DATABASE_PASSWORD"),
        dbname=os.getenv("DATABASE_NAME", "deal-library"),
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT markdown FROM public.mineru "
                "WHERE key = ANY(%s) AND markdown IS NOT NULL LIMIT 1",
                (list(candidates),),
            )
            row = cur.fetchone()

    if row is None or not row[0]:
        raise ValueError(f"No mineru markdown found for report {report_name!r}")

    question_key = question or route_function(report_name)
    if question_key is None:
        raise ValueError(
            f"No question route matched report {report_name!r}; "
            "pass an explicit question"
        )

    return understand(provider, question_key, row[0], model=model)
