# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL")

# OpenAI-compatible endpoint Groq
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Публикация на сайт
PUBLISH_TOKEN = os.getenv("PUBLISH_TOKEN")
PUBLISH_BASE = os.getenv("PUBLISH_BASE")
PUBLISH_URL = f"{PUBLISH_BASE}?token={PUBLISH_TOKEN}"

# SSL: true/1 — проверять сертификат (через certifi), false/0 — отключить проверку
_ssl = os.getenv("PUBLISH_SSL_VERIFY", "true").strip().lower()
PUBLISH_SSL_VERIFY = _ssl not in ("0", "false", "no", "off")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY не найден в .env")
