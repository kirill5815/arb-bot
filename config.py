
BOT_TOKEN = os.getenv("BOT_TOKEN", "8880570485:AAFS1jsaclCy5EIkLoRYGZBTRgHHA45IbQk")
ADMIN_IDS = [5452533555]
CHECK_INTERVAL_MINUTES = 30
DATABASE_PATH = "data/airdrops.db"

# AI-фильтр (опционально). Если пусто — ИИ-анализ отключён.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_API_URL = os.getenv("AI_API_URL", "https://api.openai.com/v1/chat/completions")
AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo")
