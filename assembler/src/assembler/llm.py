"""LLM helpers used by the two fill steps that need a model.

``fillWaterfall`` merges the waterfall extracts of two rating reports, and
``calibrateTheName`` maps trustee-report bond names onto the ``Bond`` rows.
Both used to live in ``flow/dags/datasource`` and call OpenAI-compatible
endpoints; they are isolated here so the rest of the package is pure database
work.

``openai`` is an optional dependency (``uv sync --extra llm``).  Credentials and
endpoints are read from the environment — never hard-coded:

* DeepSeek (waterfall merge): ``DEEPSEEK_API_KEY`` (or ``LLM_API_KEY``),
  ``DEEPSEEK_BASE_URL``, ``WATERFALL_LLM_MODEL``.
* Qwen / DashScope (name calibration): ``QWEN_API_KEY`` (or
  ``DASHSCOPE_API_KEY`` / ``LLM_API_KEY``), ``QWEN_BASE_URL``, ``QWEN_MODEL``.
"""

from __future__ import annotations

import json
import os

__all__ = ["LlmNotInstalled", "merge_two_waterfalls", "ask"]


class LlmNotInstalled(RuntimeError):
    """Raised when an LLM step is used without the ``llm`` extra installed."""


def _client(kind: str):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise LlmNotInstalled(
            "The 'openai' package is required for the LLM fill steps; "
            "install the optional extra, e.g. `uv sync --extra llm`."
        ) from exc

    if kind == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("WATERFALL_LLM_MODEL", "deepseek-v4-flash")
    else:  # qwen / dashscope
        api_key = (
            os.getenv("QWEN_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("LLM_API_KEY")
        )
        base_url = os.getenv(
            "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        model = os.getenv("QWEN_MODEL", "qwen-flash")

    if not api_key:
        raise RuntimeError(
            f"No API key configured for the {kind} LLM fill step "
            "(set DEEPSEEK_API_KEY / QWEN_API_KEY or LLM_API_KEY)."
        )
    return OpenAI(api_key=api_key, base_url=base_url), model


def merge_two_waterfalls(w1, w2) -> str:
    """Merge two waterfall extracts into one JSON list (DeepSeek).

    Port of ``flow/dags/datasource/LLM_ds_sync.py::mergeTwoWaterfalls``.
    """
    client, model = _client("deepseek")
    prompt = f"""
        这是一个<合并现金流分配顺序任务>:现在有描述现金流分配顺序的两个列表,摘录于同一个资产证券化的产品说明书,他们描述是同一个对象/分配规则:
        一个是 {w1}
        另外一个是 {w2}
        注意,上述两个分配顺序可能互相缺少/遗漏步骤,而且两个列表顺序可能存在错位.
        请查漏补缺,将每个对应步骤合并,保留每个步骤尽可能详细的信息,去除重复的信息.
        把结果返回成一个列表即可,列表中不能包含顺序性前缀(例如: Step1, 步骤1,step,步骤)字样,列表每个元素都是文字描述语句也就是String,不要包含其他无用信息.返回结果是一个json格式的列表,不是map/字典.如: [.....] 
    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "在ABS/资产证券化领域,你是具备丰富财务和投资知识人士,熟悉各项ABS的风险和收益指标,"
                    "同时具备计算机知识,能够回答问题时候把内容回复成json格式.同时你也是一个ABS投资分析师"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        stream=False,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def ask(q, r, model: str | None = None, toJson: bool = True):
    """Ask a Qwen/DashScope question, returning parsed JSON by default.

    Port of ``flow/dags/datasource/LLM_model.py::ask``.
    """
    client, default_model = _client("qwen")
    completion = client.chat.completions.create(
        model=model or default_model,
        messages=[
            {"role": "system", "content": r},
            {"role": "user", "content": q},
        ],
    )
    content = completion.choices[0].message.content
    if toJson:
        return json.loads(content)
    return content
