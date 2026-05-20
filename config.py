import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8880570485:AAFS1jsaclCy5EIkLoRYGZBTRgHHA45IbQk")
ADMIN_IDS = [5452533555]
CHECK_INTERVAL_MINUTES = 30
DATABASE_PATH = "data/airdrops.db"

# ===== Cerebras API — БЕСПЛАТНО, работает из РФ =====
# 1. Иди на https://cloud.cerebras.ai/platform
# 2. Sign up (email, без карты)
# 3. API Keys → Generate API Key
# 4. Скопируй ключ (начинается с csk-)
# 5. Вставь сюда:
OPENAI_API_KEY = os.getenv("CEREBRAS_API_KEY", "csk-8kpd9nmcr8h9986p3rw999h4cftvehxwwt9pkvrkkv5rvj5k")
AI_API_URL = "https://api.cerebras.ai/v1/chat/completions"
AI_MODEL = "llama3.1-70b"  # или "llama-3.1-8b" (быстрее, но проще)
