import base64
import logging
import random
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from openai import AsyncOpenAI

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_BASE_URL,
    IMAGE_PROVIDER,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
    CLOUDFLARE_STEPS,
    CLOUDFLARE_MODEL,
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


@dataclass
class ImageResult:
    """Результат генерации картинки."""

    image_bytes: bytes | None = None  # для отправки в Telegram
    image_url: str | None = None  # для сайта (если есть публичный URL)
    provider: str = ""
    image_prompt: str | None = None  # чтобы «новая картинка» могла переиспользовать


async def _call_groq(
    system: str,
    user: str,
    temperature: float = 0.9,
    max_tokens: int = 800,
) -> str:
    """Асинхронный вызов Groq (gpt-oss)."""
    response = await client.chat.completions.create(
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
    return await _call_groq(
        SYSTEM_PROMPT,
        USER_PROMPT,
        temperature=0.9,
        max_tokens=800,
    )


async def generate_image_prompt(news: str) -> str:
    """По тексту новости генерирует короткий английский промпт для картинки."""
    user = IMAGE_PROMPT_USER.format(news=news.strip())
    prompt = await _call_groq(
        IMAGE_PROMPT_SYSTEM,
        user,
        temperature=0.7,
        max_tokens=200,
    )
    prompt = prompt.strip().strip('"').strip("'").strip()
    logger.info("Image prompt: %s", prompt[:200])
    return prompt


# ---------------------------------------------------------------------------
# Cloudflare Workers AI — FLUX.1 Schnell
# ---------------------------------------------------------------------------


async def generate_image_cloudflare(prompt: str) -> bytes:
    """Генерирует картинку через Cloudflare Workers AI. Возвращает JPEG bytes."""
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise ValueError("Cloudflare credentials not configured")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CLOUDFLARE_MODEL}"
    )
    payload = {
        "prompt": prompt[:2048],
        "steps": max(1, min(CLOUDFLARE_STEPS, 8)),
        "seed": random.randint(1, 2_147_483_647),
    }

    async with httpx.AsyncClient(timeout=120.0) as http:
        resp = await http.post(
            url,
            headers={
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    if not data.get("success"):
        errors = data.get("errors") or data.get("messages") or data
        raise RuntimeError(f"Cloudflare AI error: {errors}")

    image_b64 = (data.get("result") or {}).get("image")
    if not image_b64:
        raise RuntimeError("Cloudflare returned empty image")

    img_bytes = base64.b64decode(image_b64)
    if len(img_bytes) < 500:
        raise RuntimeError("Cloudflare image too small")

    logger.info("Cloudflare image ok, size=%d bytes", len(img_bytes))
    return img_bytes


# ---------------------------------------------------------------------------
# Pollinations (fallback)
# ---------------------------------------------------------------------------


def build_pollinations_url(prompt: str) -> str:
    """Собирает URL картинки Pollinations (legacy endpoint)."""
    encoded = quote(prompt, safe="")
    # random seed, чтобы «новая картинка» реально отличалась
    seed = random.randint(1, 999_999_999)
    params = [
        f"width={POLLINATIONS_WIDTH}",
        f"height={POLLINATIONS_HEIGHT}",
        f"model={POLLINATIONS_MODEL}",
        f"seed={seed}",
        "nologo=true",
        "private=true",
    ]
    if POLLINATIONS_API_KEY:
        params.append(f"key={POLLINATIONS_API_KEY}")

    return f"https://image.pollinations.ai/prompt/{encoded}?{'&'.join(params)}"


async def download_image_bytes(url: str, timeout: float = 90.0) -> bytes:
    """Скачивает картинку по URL."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http:
        resp = await http.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type and len(resp.content) < 1000:
            raise ValueError(f"Не похоже на картинку: content-type={content_type}")
        return resp.content


async def generate_image_pollinations(prompt: str) -> ImageResult:
    """Генерирует через Pollinations: URL + bytes (скачиваем)."""
    url = build_pollinations_url(prompt)
    logger.info("Pollinations URL ready (len=%d)", len(url))
    try:
        img_bytes = await download_image_bytes(url)
        return ImageResult(image_bytes=img_bytes, image_url=url, provider="pollinations")
    except Exception:
        logger.exception("Не удалось скачать Pollinations, отдаём только URL")
        return ImageResult(image_bytes=None, image_url=url, provider="pollinations")


# ---------------------------------------------------------------------------
# Unified entry: Cloudflare primary + Pollinations fallback
# ---------------------------------------------------------------------------


async def generate_image(news: str, *, reuse_prompt: str | None = None) -> ImageResult:
    """
    Полный пайплайн картинки.
    reuse_prompt — если уже есть image-prompt (кнопка «новая картинка»),
    не ходим снова в Groq (но seed/steps всё равно новые → другая картинка).
    """
    image_prompt = reuse_prompt or await generate_image_prompt(news)

    # 1) Cloudflare (если выбран и настроен)
    if IMAGE_PROVIDER == "cloudflare" and CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN:
        try:
            img_bytes = await generate_image_cloudflare(image_prompt)
            return ImageResult(
                image_bytes=img_bytes,
                image_url=None,
                provider="cloudflare",
                image_prompt=image_prompt,
            )
        except Exception:
            logger.exception("Cloudflare failed, falling back to Pollinations")

    # 2) Pollinations
    try:
        result = await generate_image_pollinations(image_prompt)
        result.image_prompt = image_prompt
        return result
    except Exception:
        logger.exception("Pollinations also failed")
        return ImageResult(
            image_bytes=None,
            image_url=None,
            provider="none",
            image_prompt=image_prompt,
        )
