import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    Message,
    URLInputFile,
)

from generator import ImageResult
from keyboards import get_result_keyboard

logger = logging.getLogger(__name__)


def caption(news: str) -> str:
    if len(news) > 1000:
        return news[:997] + "..."
    return news


async def send_photo_or_text(
    bot: Bot,
    chat_id: int,
    news: str,
    image: ImageResult,
    edit_message: Message | None = None,
) -> Message | None:
    """Отправляет фото или текст и возвращает сообщение."""

    if edit_message:
        try:
            await edit_message.delete()
        except Exception:
            pass

    message_caption = caption(news)

    # 1. Готовые bytes
    if image.image_bytes:
        try:
            photo = BufferedInputFile(
                image.image_bytes,
                filename="news.jpg",
            )

            return await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=message_caption,
                reply_markup=get_result_keyboard(),
                parse_mode="Markdown",
            )
        except Exception:
            logger.exception("Не удалось отправить photo из bytes")

    # 2. URL
    if image.image_url:
        try:
            photo = URLInputFile(image.image_url)

            return await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=message_caption,
                reply_markup=get_result_keyboard(),
                parse_mode="Markdown",
            )
        except Exception:
            logger.exception("Не удалось отправить photo по URL")

    # 3. Только текст
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=news,
            reply_markup=get_result_keyboard(),
            parse_mode="Markdown",
        )
    except TelegramBadRequest:
        return await bot.send_message(
            chat_id=chat_id,
            text=news,
            reply_markup=get_result_keyboard(),
        )