from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "👋 Привет!\n\n"
        "Я — генератор **абсурдных новостей**.\n"
        "Нажми /new — получу новость и картинку.\n"
        "Кнопка **Новая картинка** перерисует иллюстрацию, не меняя текст.\n\n"
        "Готов? Жми /new 🚀"
    )

    await message.answer(
        text,
        parse_mode="Markdown",
    )