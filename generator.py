# generator.py
import logging
import httpx
from openai import AsyncOpenAI
from urllib.parse import quote

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_BASE_URL,
    POLLINATIONS_API_KEY,
    POLLINATIONS_MODEL,
    POLLINATIONS_WIDTH,
    POLLINATIONS_HEIGHT,
)
from prompts import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    IMAGE_PROMPT_SYSTEM,
    IMAGE_PROMPT_USER,
)


logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url=GROQ_BASE_URL,
)


# async def generate_absurd_news() -> str:
#     """Генерирует одну абсурдную новость через Groq."""

#     response = await client.chat.completions.create(
#         model=GROQ_MODEL,
#         messages=[
#             {"role": "system", "content": SYSTEM_PROMPT},
#             {"role": "user", "content": USER_PROMPT},
#         ],
#         temperature=0.9,
#         max_tokens=800,
#         extra_body={
#             "reasoning_effort": "low",
#             "include_reasoning": False,
#         },
#     )

#     choice = response.choices[0]
#     message = choice.message
#     content = (message.content or "").strip()

#     if not content:
#         reasoning = getattr(message, "reasoning", None) or ""

#         logger.warning(
#             "Пустой content. finish_reason=%s, reasoning_preview=%s",
#             choice.finish_reason,
#             (reasoning[:300] + "...") if reasoning else None,
#         )

#         if reasoning:
#             content = reasoning.strip()

#     if not content:
#         raise ValueError("Модель вернула пустой текст")

#     return content
def _call_groq(system: str, user: str, temperature: float = 0.9, max_tokens: int = 800) -> str:
    """Синхронный вызов Groq (gpt-oss)."""
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
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


async def generate_absurd_news() -> str:
    """Генерирует одну абсурдную новость через Groq."""
    return _call_groq(SYSTEM_PROMPT, USER_PROMPT, temperature=0.9, max_tokens=800)

def build_pollinations_url(prompt: str) -> str:
    """
    Собирает URL картинки Pollinations (legacy endpoint).
    Без ключа тоже работает. С ключом — nologo + выше приоритет.
    """
    encoded = quote(prompt, safe="")
    params = [
        f"width={POLLINATIONS_WIDTH}",
        f"height={POLLINATIONS_HEIGHT}",
        f"model={POLLINATIONS_MODEL}",
        "nologo=true",
        "private=true",
    ]
    if POLLINATIONS_API_KEY:
        params.append(f"key={POLLINATIONS_API_KEY}")

    return f"https://image.pollinations.ai/prompt/{encoded}?{'&'.join(params)}"

async def generate_image_prompt(news: str) -> str:
    """По тексту новости генерирует короткий английский промпт для картинки."""
    user = IMAGE_PROMPT_USER.format(news=news.strip())
    prompt = _call_groq(
        IMAGE_PROMPT_SYSTEM,
        user,
        temperature=0.7,
        max_tokens=200,
    )
    # На всякий случай убираем кавычки и лишние переносы
    prompt = prompt.strip().strip('"').strip("'").strip()
    logger.info("Image prompt: %s", prompt[:200])
    return prompt

async def generate_image_url(news: str) -> str:
    """
    Полный пайплайн: новость → промпт для картинки → URL картинки.
    Возвращает готовый URL, который можно сразу отдавать в Telegram.
    """
    image_prompt = await generate_image_prompt(news)
    url = build_pollinations_url(image_prompt)
    logger.info("Pollinations URL ready (len=%d)", len(url))
    return url


async def download_image_bytes(url: str, timeout: float = 90.0) -> bytes:
    """Скачивает картинку по URL (на случай, если нужно отправить как файл)."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http:
        resp = await http.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type and len(resp.content) < 1000:
            raise ValueError(f"Не похоже на картинку: content-type={content_type}")
        return resp.content