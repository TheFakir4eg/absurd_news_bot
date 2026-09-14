import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile, URLInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from config import BOT_TOKEN
from generator import generate_absurd_news, generate_image_url, download_image_bytes
from publisher import publish_news

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_result_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Ещё раз", callback_data="again")
    builder.button(text="✅ Готово", callback_data="done")
    builder.adjust(2)
    return builder.as_markup()


async def _send_news_with_image(chat_id: int, news: str, edit_message: Message | None = None):
    """
    Генерирует картинку по новости и отправляет/редактирует сообщение.
    Если edit_message передан — пытаемся отредактировать, иначе шлём новое.
    """
    try:
        image_url = await generate_image_url(news)
    except Exception:
        logger.exception("Не удалось сгенерировать промпт/URL картинки")
        image_url = None

    caption = news
    # Telegram caption limit ~1024
    if len(caption) > 1000:
        caption = caption[:997] + "..."

    if image_url:
        try:
            # Сначала пробуем отправить по URL (Telegram сам скачает)
            photo = URLInputFile(image_url)
            if edit_message:
                # edit_media сложнее, проще удалить старое и отправить новое
                try:
                    await edit_message.delete()
                except Exception:
                    pass
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=get_result_keyboard(),
                    parse_mode="Markdown",
                )
            else:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=get_result_keyboard(),
                    parse_mode="Markdown",
                )
            return
        except Exception:
            logger.exception("Не удалось отправить фото по URL, пробуем скачать")

        # Fallback: скачиваем байты и отправляем как файл
        try:
            img_bytes = await download_image_bytes(image_url)
            photo = BufferedInputFile(img_bytes, filename="news.jpg")
            if edit_message:
                try:
                    await edit_message.delete()
                except Exception:
                    pass
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=get_result_keyboard(),
                parse_mode="Markdown",
            )
            return
        except Exception:
            logger.exception("Не удалось скачать/отправить картинку")

    # Если картинка совсем не получилась — просто текст
    if edit_message:
        try:
            await edit_message.edit_text(
                news,
                reply_markup=get_result_keyboard(),
                parse_mode="Markdown",
            )
            return
        except TelegramBadRequest:
            pass

    await bot.send_message(
        chat_id=chat_id,
        text=news,
        reply_markup=get_result_keyboard(),
        parse_mode="Markdown",
    )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "👋 Привет!\n\n"
        "Я — генератор **абсурдных новостей**.\n"
        "Нажми /new, и я придумаю совершенно нелепую, но очень «серьёзную» новость "
        "и сразу сгенерирую к ней картинку.\n\n"
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
    wait_msg = await callback.message.edit_text("⏳ Генерирую новую абсурдную новость и картинку...")

    try:
        news = await generate_absurd_news()
        if not news or not news.strip():
            raise ValueError("Пустой текст от модели")

        await _send_news_with_image(
            chat_id=callback.message.chat.id,
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
            await callback.message.answer(
                "😔 Не удалось сгенерировать новость. Попробуй ещё раз чуть позже."
            )


@dp.callback_query(F.data == "done")
async def callback_done(callback: CallbackQuery):
    await callback.answer("Публикую…")

    # Берём текст из caption (если было фото) или из text
    news_text = callback.message.caption or callback.message.text or ""
    if not news_text.strip():
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("😔 Нечего публиковать — текст новости пустой.")
        return

    try:
        result = await publish_news(news_text)
        logger.info("Опубликовано: %s", result)
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