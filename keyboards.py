from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_result_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🖼 Новая картинка", callback_data="edit_image")
    builder.button(text="🔄 Ещё раз", callback_data="again")
    builder.button(text="✅ Готово", callback_data="done")
    builder.adjust(1, 2)
    return builder.as_markup()