# bot.py
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from config import BOT_TOKEN
from generator import generate_absurd_news
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


@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "👋 Привет!\n\n"
        "Я — генератор **абсурдных новостей**.\n"
        "Нажми /new, и я придумаю совершенно нелепую, но очень «серьёзную» новость.\n\n"
        "Готов? Жми /new 🚀"
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("new"))
async def cmd_new(message: Message):
    wait_msg = await message.answer("⏳ Генерирую абсурдную новость...")

    try:
        news = await generate_absurd_news()
        if not news or not news.strip():
            raise ValueError("Пустой текст от модели")

        await wait_msg.edit_text(
            news,
            reply_markup=get_result_keyboard(),
            parse_mode="Markdown",
        )
    except TelegramBadRequest as e:
        logger.exception("Ошибка Telegram при отправке")
        # Если Markdown сломался — пробуем без разметки
        try:
            news = await generate_absurd_news()
            await wait_msg.edit_text(
                news or "😔 Не удалось сгенерировать новость.",
                reply_markup=get_result_keyboard(),
            )
        except Exception:
            await wait_msg.edit_text(
                "😔 Не удалось сгенерировать новость. Попробуй ещё раз чуть позже."
            )
    except Exception as e:
        logger.exception("Ошибка генерации")
        await wait_msg.edit_text(
            "😔 Не удалось сгенерировать новость. Попробуй ещё раз чуть позже."
        )


@dp.callback_query(F.data == "again")
async def callback_again(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("⏳ Генерирую новую абсурдную новость...")

    try:
        news = await generate_absurd_news()
        if not news or not news.strip():
            raise ValueError("Пустой текст от модели")

        await callback.message.edit_text(
            news,
            reply_markup=get_result_keyboard(),
            parse_mode="Markdown",
        )
    except TelegramBadRequest:
        try:
            news = await generate_absurd_news()
            await callback.message.edit_text(
                news or "😔 Не удалось сгенерировать новость.",
                reply_markup=get_result_keyboard(),
            )
        except Exception:
            await callback.message.edit_text(
                "😔 Не удалось сгенерировать новость. Попробуй ещё раз чуть позже."
            )
    except Exception as e:
        logger.exception("Ошибка генерации")
        await callback.message.edit_text(
            "😔 Не удалось сгенерировать новость. Попробуй ещё раз чуть позже."
        )


@dp.callback_query(F.data == "done")
async def callback_done(callback: CallbackQuery):
    await callback.answer("Публикую…")

    news_text = callback.message.text or callback.message.caption or ""
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
