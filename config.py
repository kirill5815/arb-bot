import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8880570485:AAFS1jsaclCy5EIkLoRYGZBTRgHHA45IbQk")
ADMIN_IDS = [5452533555]
CHECK_INTERVAL_MINUTES = 30
DATABASE_PATH = "data/airdrops.db"

# ===== Google AI Studio (Gemini) — БЕСПЛАТНО =====
# 1. Иди на https://aistudio.google.com/app/apikey
# 2. Создай ключ (без карты, через Gmail)
# 3. Вставь сюда:
OPENAI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyCsZiHifvIRLEBdakV1QZSkkUeeh68WXdk")
AI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
AI_MODEL = "gemini-2.5-flash"  # или "gemini-2.5-flash-lite" (ещё быстрее)
