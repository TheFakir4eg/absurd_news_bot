import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from generator import generate_absurd_news
from storage import get_news, remove_news

from handlers.news import send_news_with_image


logger = logging.getLogger(__name__)

router = Router()


async def delete_callback_message(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


@router.callback_query(F.data == "again")
async def callback_again(callback: CallbackQuery, bot: Bot):
    await callback.answer()

    chat_id = callback.message.chat.id

    remove_news(callback.message.message_id)

    await delete_callback_message(callback)

    wait_msg = await bot.send_message(
        chat_id=chat_id,
        text="⏳ Генерирую новую абсурдную новость и картинку...",
    )

    try:
        news = await generate_absurd_news()

        if not news or not news.strip():
            raise ValueError("Пустой текст от модели")

        await send_news_with_image(
            bot=bot,
            chat_id=chat_id,
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
            await bot.send_message(
                chat_id=chat_id,
                text="😔 Не удалось сгенерировать новость. "
                "Попробуй ещё раз чуть позже.",
            )


@router.callback_query(F.data == "edit_image")
async def callback_edit_image(callback: CallbackQuery, bot: Bot):
    """Та же новость, новая картинка."""

    await callback.answer("Генерирую новую картинку…")

    chat_id = callback.message.chat.id
    message_id = callback.message.message_id

    stored = get_news(message_id)

    news = (
        stored.text
        if stored
        else callback.message.caption or callback.message.text
    )

    if not news or not news.strip():
        await callback.message.answer(
            "😔 Не нашёл текст новости для новой картинки."
        )
        return

    reuse_prompt = stored.image_prompt if stored else None

    remove_news(message_id)

    await delete_callback_message(callback)

    wait_msg = await bot.send_message(
        chat_id=chat_id,
        text="⏳ Рисую новую картинку к той же новости...",
    )

    try:
        await send_news_with_image(
            bot=bot,
            chat_id=chat_id,
            news=news,
            edit_message=wait_msg,
            reuse_prompt=reuse_prompt,
        )

    except Exception:
        logger.exception("Ошибка генерации картинки")

        try:
            await wait_msg.edit_text(
                "😔 Не удалось сгенерировать картинку. "
                "Попробуй ещё раз."
            )
        except Exception:
            await bot.send_message(
                chat_id=chat_id,
                text="😔 Не удалось сгенерировать картинку. "
                "Попробуй ещё раз.",
            )


@router.callback_query(F.data == "done")
async def callback_done(callback: CallbackQuery, bot: Bot):
    await callback.answer("Публикую…")

    news_text = (
        callback.message.caption
        or callback.message.text
        or ""
    )

    stored = remove_news(callback.message.message_id)

    if stored and stored.text:
        news_text = stored.text

    if not news_text.strip():
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "😔 Нечего публиковать — текст новости пустой."
        )
        return

    image_url = (stored.image_url if stored else None) or ""
    image_bytes = stored.image_bytes if stored else None

    try:
        from publisher import publish_news

        result = await publish_news(
            news_text,
            image_url=image_url,
            image_bytes=image_bytes,
        )

        logger.info(
            "Опубликовано: %s (url=%s, bytes=%s)",
            result,
            bool(image_url),
            bool(image_bytes),
        )

        await callback.message.edit_reply_markup(
            reply_markup=None
        )

        await callback.message.answer(
            "✅ Новость опубликована на сайте!"
        )

    except Exception:
        logger.exception("Ошибка публикации")

        await callback.message.edit_reply_markup(
            reply_markup=None
        )

        await callback.message.answer(
            "😔 Не удалось опубликовать новость. "
            "Попробуй ещё раз или проверь сайт."
        )