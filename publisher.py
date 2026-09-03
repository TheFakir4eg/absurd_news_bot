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


async def publish_news(text: str) -> dict:
    """
    Парсит новость и отправляет POST на сайт.
    Возвращает JSON-ответ сервера или поднимает исключение.
    """
    payload = parse_news(text)
    logger.info("Публикация: title=%s", payload["title"][:80])

    async with httpx.AsyncClient(timeout=30.0, verify=_ssl_verify()) as client:
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