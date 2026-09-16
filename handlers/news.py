import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from generator import generate_absurd_news, generate_image, ImageResult
from models import StoredNews
from storage import save_news
from telegram_utils import send_photo_or_text


logger = logging.getLogger(__name__)

router = Router()


async def send_news_with_image(
    bot: Bot,
    chat_id: int,
    news: str,
    edit_message: Message | None = None,
    *,
    reuse_prompt: str | None = None,
):
    """
    Генерирует картинку и отправляет новость.
    """

    image = ImageResult()

    try:
        image = await generate_image(
            news,
            reuse_prompt=reuse_prompt,
        )
    except Exception:
        logger.exception("Не удалось сгенерировать картинку")

    sent = await send_photo_or_text(
        bot=bot,
        chat_id=chat_id,
        news=news,
        image=image,
        edit_message=edit_message,
    )

    if sent:
        save_news(
            sent.message_id,
            StoredNews(
                text=news,
                image_url=image.image_url,
                image_bytes=image.image_bytes,
                image_prompt=image.image_prompt or reuse_prompt,
            ),
        )

        logger.info(
            "Saved news for message_id=%s provider=%s has_url=%s has_bytes=%s",
            sent.message_id,
            image.provider,
            bool(image.image_url),
            bool(image.image_bytes),
        )

    return sent


@router.message(Command("new"))
async def cmd_new(message: Message, bot: Bot):
    wait_msg = await message.answer(
        "⏳ Генерирую абсурдную новость и картинку..."
    )

    try:
        news = await generate_absurd_news()

        if not news or not news.strip():
            raise ValueError("Пустой текст от модели")

        await send_news_with_image(
            bot=bot,
            chat_id=message.chat.id,
            news=news,
            edit_message=wait_msg,
        )

    except Exception:
        logger.exception("Ошибка генерации")

        try:
            await wait_msg.edit_text(
                "😔 Не удалось сгенерировать новость. "
                "Попробуй ещё раз чуть позже."
            )
        except Exception:
            await message.answer(
                "😔 Не удалось сгенерировать новость. "
                "Попробуй ещё раз чуть позже."
            )