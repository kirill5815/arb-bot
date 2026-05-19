import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8971526974:AAGe8NolD-gB-iTvaVE8T3cFqOWu3DDEAmI")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))

EX1_NAME = os.getenv("EX1", "bybit")
EX2_NAME = os.getenv("EX2", "htx")

QUOTE = os.getenv("QUOTE", "USDT")
POLL_SEC = int(os.getenv("POLL_SEC", "10"))
MIN_PROFIT_PCT = float(os.getenv("MIN_PROFIT_PCT", "0.30"))
FEE1 = float(os.getenv("FEE1", "0.001"))
FEE2 = float(os.getenv("FEE2", "0.001"))
MIN_NOTIONAL_QUOTE = float(os.getenv("MIN_NOTIONAL_QUOTE", "50"))
OB_LIMIT = int(os.getenv("OB_LIMIT", "5"))

