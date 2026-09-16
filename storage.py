from models import StoredNews


# message_id -> StoredNews
_store: dict[int, StoredNews] = {}


def save_news(message_id: int, news: StoredNews):
    _store[message_id] = news


def get_news(message_id: int) -> StoredNews | None:
    return _store.get(message_id)


def remove_news(message_id: int) -> StoredNews | None:
    return _store.pop(message_id, None)