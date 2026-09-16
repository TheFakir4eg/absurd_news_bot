absurd-news-bot/
├── bot.py                 # только запуск + регистрация handlers
├── config.py
├── generator.py           # генерация текста и изображений
├── publisher.py           # публикация на FNN
│
├── models.py              # StoredNews
├── keyboards.py           # inline-клавиатуры
├── storage.py             # _store
├── telegram_utils.py      # отправка новости / caption
│
└── handlers/
    ├── __init__.py
    ├── start.py           # /start
    ├── news.py            # /new
    └── callbacks.py       # again / edit_image / done