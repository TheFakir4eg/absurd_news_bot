import logging

from openai import AsyncOpenAI

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL
from prompts import SYSTEM_PROMPT, USER_PROMPT


logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url=GROQ_BASE_URL,
)


async def generate_absurd_news() -> str:
    """Генерирует одну абсурдную новость через Groq."""

    response = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        temperature=0.9,
        max_tokens=800,
        extra_body={
            "reasoning_effort": "low",
            "include_reasoning": False,
        },
    )

    choice = response.choices[0]
    message = choice.message
    content = (message.content or "").strip()

    if not content:
        reasoning = getattr(message, "reasoning", None) or ""

        logger.warning(
            "Пустой content. finish_reason=%s, reasoning_preview=%s",
            choice.finish_reason,
            (reasoning[:300] + "...") if reasoning else None,
        )

        if reasoning:
            content = reasoning.strip()

    if not content:
        raise ValueError("Модель вернула пустой текст")

    return content