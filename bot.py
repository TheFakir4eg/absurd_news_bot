import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile, URLInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from config import BOT_TOKEN
from generator import generate_absurd_news, generate_image, ImageResult
from publisher import publish_news

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dataclass
class StoredNews:
    """Данные новости, привязанные к message_id в Telegram."""

    text: str
    image_url: str | None = None  # Pollinations URL (если есть)
    image_bytes: bytes | None = None  # JPEG от Cloudflare / скачанный файл
    image_prompt: str | None = None  # чтобы «новая картинка» не перегенерировала промпт


# message_id -> StoredNews
_store: dict[int, StoredNews] = {}


def get_result_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🖼 Новая картинка", callback_data="edit_image")
    builder.button(text="🔄 Ещё раз", callback_data="again")
    builder.button(text="✅ Готово", callback_data="done")
    builder.adjust(1, 2)
    return builder.as_markup()


def _caption(news: str) -> str:
    if len(news) > 1000:
        return news[:997] + "..."
    return news


async def _send_photo_or_text(
    chat_id: int,
    news: str,
    image: ImageResult,
    edit_message: Message | None = None,
) -> Message | None:
    """Отправляет фото (bytes или URL) или текст. Возвращает отправленное сообщение."""
    caption = _caption(news)
    sent: Message | None = None

    if edit_message:
        try:
            await edit_message.delete()
        except Exception:
            pass

    # 1) bytes (Cloudflare или скачанный Pollinations)
    if image.image_bytes:
        try:
            photo = BufferedInputFile(image.image_bytes, filename="news.jpg")
            sent = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=get_result_keyboard(),
                parse_mode="Markdown",
            )
            return sent
        except Exception:
            logger.exception("Не удалось отправить photo из bytes")

    # 2) URL (Pollinations)
    if image.image_url:
        try:
            photo = URLInputFile(image.image_url)
            sent = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=get_result_keyboard(),
                parse_mode="Markdown",
            )
            return sent
        except Exception:
            logger.exception("Не удалось отправить photo по URL")

    # 3) Только текст
    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=news,
            reply_markup=get_result_keyboard(),
            parse_mode="Markdown",
        )
    except TelegramBadRequest:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=news,
            reply_markup=get_result_keyboard(),
        )
    return sent


async def _send_news_with_image(
    chat_id: int,
    news: str,
    edit_message: Message | None = None,
    *,
    reuse_prompt: str | None = None,
):
    """
    Генерирует картинку и отправляет новость.
    Сохраняет текст + image_url + prompt в _store по message_id.
    """
    image = ImageResult()
    try:
        image = await generate_image(news, reuse_prompt=reuse_prompt)
    except Exception:
        logger.exception("Не удалось сгенерировать картинку")

    sent = await _send_photo_or_text(chat_id, news, image, edit_message=edit_message)

    if sent:
        _store[sent.message_id] = StoredNews(
            text=news,
            image_url=image.image_url,
            image_bytes=image.image_bytes,
            image_prompt=image.image_prompt or reuse_prompt,
        )
        logger.info(
            "Saved news for message_id=%s provider=%s has_url=%s has_bytes=%s",
            sent.message_id,
            image.provider,
            bool(image.image_url),
            bool(image.image_bytes),
        )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "👋 Привет!\n\n"
        "Я — генератор **абсурдных новостей**.\n"
        "Нажми /new — получу новость и картинку.\n"
        "Кнопка **Новая картинка** перерисует иллюстрацию, не меняя текст.\n\n"
        "Готов? Жми /new 🚀"
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("new"))
async def cmd_new(message: Message):
    wait_msg = await message.answer("⏳ Генерирую абсурдную новость и картинку...")

    try:
        news = await generate_absurd_news()
        if not news or not news.strip():
            raise ValueError("Пустой текст от модели")

        await _send_news_with_image(
            chat_id=message.chat.id,
            news=news,
            edit_message=wait_msg,
        )
    except Exception:
        logger.exception("Ошибка генерации")
        try:
            await wait_msg.edit_text(
                "😔 Не удалось сгенерировать новость. Попробуй ещё раз чуть позже."
            )
        except Exception:
            await message.answer(
                "😔 Не удалось сгенерировать новость. Попробуй ещё раз чуть позже."
            )


@dp.callback_query(F.data == "again")
async def callback_again(callback: CallbackQuery):
    await callback.answer()
    chat_id = callback.message.chat.id
    _store.pop(callback.message.message_id, None)

    try:
        await callback.message.delete()
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    wait_msg = await bot.send_message(
        chat_id=chat_id,
        text="⏳ Генерирую новую абсурдную новость и картинку...",
    )

    try:
        news = await generate_absurd_news()
        if not news or not news.strip():
            raise ValueError("Пустой текст от модели")

        await _send_news_with_image(
            chat_id=chat_id,
            news=news,
            edit_message=wait_msg,
        )
    except Exception:
        logger.exception("Ошибка генерации")
        try:
            await wait_msg.edit_text(
                "😔 Не удалось сгенерировать новость. Попробуй ещё раз чуть позже."
            )
        except Exception:
            await bot.send_message(
                chat_id=chat_id,
                text="😔 Не удалось сгенерировать новость. Попробуй ещё раз чуть позже.",
            )


@dp.callback_query(F.data == "edit_image")
async def callback_edit_image(callback: CallbackQuery):
    """Та же новость, новая картинка."""
    await callback.answer("Генерирую новую картинку…")
    chat_id = callback.message.chat.id
    msg_id = callback.message.message_id

    stored = _store.get(msg_id)
    news = (stored.text if stored else None) or callback.message.caption or callback.message.text
    if not news or not news.strip():
        await callback.message.answer("😔 Не нашёл текст новости для новой картинки.")
        return

    reuse_prompt = stored.image_prompt if stored else None
    _store.pop(msg_id, None)

    try:
        await callback.message.delete()
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    wait_msg = await bot.send_message(
        chat_id=chat_id,
        text="⏳ Рисую новую картинку к той же новости...",
    )

    try:
        await _send_news_with_image(
            chat_id=chat_id,
            news=news,
            edit_message=wait_msg,
            reuse_prompt=reuse_prompt,
        )
    except Exception:
        logger.exception("Ошибка генерации картинки")
        try:
            await wait_msg.edit_text(
                "😔 Не удалось сгенерировать картинку. Попробуй ещё раз."
            )
        except Exception:
            await bot.send_message(
                chat_id=chat_id,
                text="😔 Не удалось сгенерировать картинку. Попробуй ещё раз.",
            )


@dp.callback_query(F.data == "done")
async def callback_done(callback: CallbackQuery):
    await callback.answer("Публикую…")

    news_text = callback.message.caption or callback.message.text or ""
    stored = _store.pop(callback.message.message_id, None)
    if stored and stored.text:
        news_text = stored.text

    if not news_text.strip():
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("😔 Нечего публиковать — текст новости пустой.")
        return

    image_url = (stored.image_url if stored else None) or ""
    image_bytes = stored.image_bytes if stored else None

    try:
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
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Новость опубликована на сайте!")
    except Exception:
        logger.exception("Ошибка публикации")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "😔 Не удалось опубликовать новость. Попробуй ещё раз или проверь сайт."
        )


async def main():
    logger.info("Бот запускается...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())