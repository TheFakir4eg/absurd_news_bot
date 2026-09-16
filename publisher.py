import base64
import logging
import re

import httpx

from config import PUBLISH_URL, PUBLISH_SSL_VERIFY

logger = logging.getLogger(__name__)


def _ssl_verify():
    """Путь к CA-бандлу (certifi) или False, если проверка отключена."""
    if not PUBLISH_SSL_VERIFY:
        return False
    try:
        import certifi

        return certifi.where()
    except ImportError:
        return True  # системные сертификаты


def parse_news(text: str) -> dict:
    """
    Разбирает текст новости на title, subtitle и content.
    Ожидаемый формат:
      **Заголовок**

      Текст...
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Пустой текст новости")

    title = ""
    body = text

    # Вариант 1: **Заголовок**
    m = re.search(r"\*\*(.+?)\*\*", text, re.DOTALL)
    if m:
        title = m.group(1).strip()
        body = text[m.end() :].strip()
    else:
        # Вариант 2: первая непустая строка — заголовок
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            title = lines[0].lstrip("#").strip()
            body = "\n".join(lines[1:]).strip() if len(lines) > 1 else title

    if not title:
        title = "Абсурдная новость"

    if not body:
        body = title

    # subtitle = короткая тема (очищенный заголовок)
    subtitle = re.sub(r"[*_`#]", "", title).strip()
    if len(subtitle) > 120:
        subtitle = subtitle[:117] + "..."

    # content в markdown
    content = body
    if not content.startswith("**") and title:
        content = f"**{title}**\n\n{body}"

    return {
        "title": title,
        "subtitle": subtitle,
        "content": content,
        "image_url": "",
    }


async def publish_news(
    text: str,
    image_url: str = "",
    image_bytes: bytes | None = None,
) -> dict:
    """
    Парсит новость и отправляет POST на сайт.
    image_url — публичная ссылка (Pollinations и т.п.).
    image_bytes — JPEG от Cloudflare; уйдёт как image_base64.
    """
    payload = parse_news(text)
    if image_url:
        payload["image_url"] = image_url
    if image_bytes:
        payload["image_base64"] = base64.b64encode(image_bytes).decode("ascii")

    logger.info(
        "Публикация: title=%s, has_url=%s, has_base64=%s",
        payload["title"][:80],
        bool(image_url),
        bool(image_bytes),
    )

    async with httpx.AsyncClient(timeout=60.0, verify=_ssl_verify()) as client:
        response = await client.post(
            PUBLISH_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return {"status": "ok", "raw": response.text}