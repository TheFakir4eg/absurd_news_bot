from dataclasses import dataclass


@dataclass
class StoredNews:
    """Данные новости, привязанные к message_id в Telegram."""

    text: str
    image_url: str | None = None
    image_bytes: bytes | None = None
    image_prompt: str | None = None