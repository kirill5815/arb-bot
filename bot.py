import asyncio
import json
import logging
import httpx
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from config import BOT_TOKEN, ADMIN_IDS, CHECK_INTERVAL_MINUTES
from database import (
    init_db, add_user, toggle_subscription, get_user_categories,
    get_active_airdrops, add_airdrop, get_not_notified_airdrops,
    mark_as_notified, get_all_active_users, get_users_by_category,
    get_airdrop_analysis, save_airdrop_analysis
)
from parser import fetch_and_save_airdrops

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CATEGORIES = ["DeFi", "NFT", "Testnet", "Gaming", "Layer2", "Other"]

# ===== ВПИШИ СВОЙ КЛЮЧ CEREBRAS СЮДА =====
CEREBRAS_KEY = "csk-2cn93hr48ktj5c6hyt8nc4rd3rpcwd95mxypnmknecnvxnd9"
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODEL = "llama3.1-70b"


def _extract_json(text: str) -> str:
    import re
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```json\s*|^```\s*|```$", "", text, flags=re.MULTILINE).strip()
    return text


def _scam_emoji(score: int) -> str:
    if score >= 70: return "🔴"
    elif score >= 40: return "🟡"
    return "🟢"


def _diff_stars(d: int) -> str:
    return "⭐" * d + "☆" * (5 - d)


async def cerebras_analyze(title: str, description: str, link: str) -> dict:
    """Вызов Cerebras API через httpx."""
    logger.info(f"[CEREBRAS] KEY length={len(CEREBRAS_KEY)}, prefix={CEREBRAS_KEY[:8]}...")

    if not CEREBRAS_KEY or "ВАШ" in CEREBRAS_KEY or len(CEREBRAS_KEY) < 20:
        logger.warning("[CEREBRAS] KEY invalid, fallback")
        return _fallback_analysis(title, description, link)

    prompt = f"""Analyze crypto airdrop, return ONLY JSON:
{{"scam_probability":0-100,"difficulty":1-5,"expected_profit_usd":"10-50","time_required_minutes":30,"summary":"brief Russian conclusion","red_flags":["list or empty"]}}
Title:{title} Desc:{description or 'none'} Link:{link}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                CEREBRAS_URL,
                headers={"Authorization": f"Bearer {CEREBRAS_KEY}", "Content-Type": "application/json"},
                json={"model": CEREBRAS_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 400}
            )
            logger.info(f"[CEREBRAS] HTTP {resp.status_code}")
            if resp.status_code != 200:
                logger.error(f"[CEREBRAS] Error: {resp.text[:200]}")
                return _fallback_analysis(title, description, link)

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info(f"[CEREBRAS] Response: {content[:80]}...")
            clean = _extract_json(content)
            result = json.loads(clean)
            result["scam_probability"] = max(0, min(100, int(result.get("scam_probability", 50))))
            result["difficulty"] = max(1, min(5, int(result.get("difficulty", 3))))
            logger.info(f"[CEREBRAS] Success: risk={result['scam_probability']}%")
            return result
    except Exception as e:
        logger.error(f"[CEREBRAS] Exception: {e}")
        return _fallback_analysis(title, description, link)


def _fallback_analysis(title: str, description: str, link: str) -> dict:
    text = (title + " " + (description or "") + " " + link).lower()
    score = 0
    flags = []
    if "connect wallet" in text and ("private key" in text or "seed phrase" in text):
        score += 60
        flags.append("Запрос приватного ключа")
    if "guaranteed" in text or "100%" in text or "instant withdraw" in text:
        score += 40
        flags.append("Гарантированная прибыль")
    if "send eth" in text or "send bnb" in text:
        score += 30
        flags.append("Требуется отправка крипты")
    if score > 80:
        diff, profit = 1, "0 (скам)"
    elif score > 40:
        diff, profit = 2, "10-30"
    else:
        diff, profit = 3, "30-200"
    return {"scam_probability": min(score, 100), "difficulty": diff, "expected_profit_usd": profit,
            "time_required_minutes": 30, "summary": "Базовая эвристика" if flags else "Стандартный аирдроп",
            "red_flags": flags if flags else ["Нет флагов"]}


EARN_TEXT = (
    "💰 Как заработать на аирдропах (реалистичный взгляд)\n\n"
    "📊 Средний доход:\n"
    "• Простые соц. активности: $10–50\n"
    "• Тестнеты / DeFi активности: $100–500\n"
    "• Крупные ранние проекты (Arbitrum, Optimism): $1 000–10 000+\n"
    "• Но: 90% аирдропов дают $0 или оказываются скамом\n\n"
    "🛠 Пошаговая инструкция:\n"
    "1. Кошелёк MetaMask + сети ETH, Polygon, Arbitrum, Base\n"
    "2. Небольшой баланс для газа ($20–50 в ETH/MATIC)\n"
    "3. Регистрация на проектах, выполнение заданий\n"
    "4. Ожидание 3–12 месяцев до раздачи токенов\n"
    "5. Продажа токенов сразу после листинга\n\n"
    "⚠️ Риски:\n"
    "• Потеря времени: 30 мин – 2 часа на 1 аирдроп\n"
    "• Потеря денег на газе\n"
    "• Скам-проекты крадут приватные ключи\n\n"
    "💡 Совет: делай 10–20 качественных аирдропов в месяц."
)


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🎯 Аирдропы"), KeyboardButton("⚙️ Категории")],
         [KeyboardButton("💰 Как заработать"), KeyboardButton("🔍 Анализ ссылки")],
         [KeyboardButton("❓ Помощь"), KeyboardButton("🏠 Главное меню")]],
        resize_keyboard=True, one_time_keyboard=False)


def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🎯 Аирдропы"), KeyboardButton("⚙️ Категории")],
         [KeyboardButton("💰 Как заработать"), KeyboardButton("🔍 Анализ ссылки")],
         [KeyboardButton("❓ Помощь"), KeyboardButton("🏠 Главное меню")],
         [KeyboardButton("🔧 Добавить аирдроп"), KeyboardButton("🔄 Запустить парсинг")]],
        resize_keyboard=True, one_time_keyboard=False)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_user(user.id, user.username)
    is_admin = user.id in ADMIN_IDS
    keyboard = get_admin_keyboard() if is_admin else get_main_keyboard()
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для мониторинга крипто-аирдропов с ИИ-фильтром Cerebras. "
        "Проверяю скам-риски, сложность и доходность автоматически — бесплатно.",
        reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Команды:\n"
        "🎯 Аирдропы — список с ИИ-оценками\n"
        "⚙️ Категории — настройка уведомлений\n"
        "💰 Как заработать — инструкция и доходы\n"
        "🔍 Анализ ссылки — ИИ-проверка аирдропа\n"
        "❓ Помощь — это сообщение\n"
        "🏠 Главное меню — вернуться в начало\n\n"
        "🤖 ИИ: Cerebras llama3.1-70b (бесплатно)\n"
        f"🔔 Автопроверка каждые {CHECK_INTERVAL_MINUTES} минут.")


async def earn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(EARN_TEXT)


async def analyze_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🔍 Отправь ссылку на аирдроп для ИИ-анализа:\n"
            "Пример: /analyze https://example.com/airdrop\n\n"
            "Или просто отправь ссылку в чат, начинающуюся с http")
        return
    link = context.args[0]
    await update.message.reply_text("🤖 Cerebras анализирует ссылку...")
    analysis = await cerebras_analyze("Пользовательская ссылка", "", link)
    text = (
        f"🔍 ИИ-анализ Cerebras: {link}\n\n"
        f"{_scam_emoji(analysis['scam_probability'])} Скам-риск: {analysis['scam_probability']}%\n"
        f"{_diff_stars(analysis['difficulty'])} Сложность: {analysis['difficulty']}/5\n"
        f"💰 Ожидаемый доход: ${analysis['expected_profit_usd']}\n"
        f"⏱ Время: ~{analysis['time_required_minutes']} мин\n\n"
        f"📝 Вывод: {analysis['summary']}\n\n"
        f"🚩 Флаги: {', '.join(analysis['red_flags'])}")
    await update.message.reply_text(text, disable_web_page_preview=True)


async def list_airdrops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    airdrops = await get_active_airdrops(limit=10)
    if not airdrops:
        await update.message.reply_text("😕 Пока нет активных аирдропов.")
        return
    text = "🎯 Активные аирдропы (с ИИ-оценками Cerebras):\n\n"
    for airdrop in airdrops:
        a_id = airdrop[0]
        title = airdrop[1]
        category = airdrop[4]
        link = airdrop[3]
        desc = airdrop[2] or ""
        analysis = await get_airdrop_analysis(a_id)
        if analysis:
            scam = analysis["scam_probability"]
            diff = analysis["difficulty"]
            profit = analysis["expected_profit_usd"]
            ai_line = f"\n{_scam_emoji(scam)} Риск: {scam}% | ⭐{diff}/5 | 💰~${profit}"
        else:
            ai_line = "\n🤖 Cerebras: в обработке..."
        text += f"*{title}* ({category}){ai_line}\n🔗 {link}\n_{desc[:80]}_\n\n"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_cats = await get_user_categories(user_id)
    keyboard = []
    for cat in CATEGORIES:
        icon = "✅" if cat in user_cats else "⬜"
        keyboard.append([InlineKeyboardButton(f"{icon} {cat}", callback_data=f"cat_{cat}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="menu")])
    await update.message.reply_text(
        "⚙️ Выбери категории для уведомлений:",
        reply_markup=InlineKeyboardMarkup(keyboard))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "list":
        airdrops = await get_active_airdrops(limit=10)
        if not airdrops:
            await query.edit_message_text("😕 Пока нет активных аирдропов.")
            return
        text = "🎯 Активные аирдропы:\n\n"
        for airdrop in airdrops:
            a_id = airdrop[0]
            analysis = await get_airdrop_analysis(a_id)
            if analysis:
                ai_line = f"\n{_scam_emoji(analysis['scam_probability'])} Риск: {analysis['scam_probability']}% | ⭐{analysis['difficulty']}/5 | 💰~${analysis['expected_profit_usd']}"
            else:
                ai_line = ""
            text += f"*{airdrop[1]}* ({airdrop[4]}){ai_line}\n🔗 {airdrop[3]}\n\n"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown", disable_web_page_preview=True)

    elif data == "categories":
        user_cats = await get_user_categories(user_id)
        keyboard = []
        for cat in CATEGORIES:
            icon = "✅" if cat in user_cats else "⬜"
            keyboard.append([InlineKeyboardButton(f"{icon} {cat}", callback_data=f"cat_{cat}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="menu")])
        await query.edit_message_text("⚙️ Выбери категории:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("cat_"):
        category = data.replace("cat_", "")
        is_subscribed = await toggle_subscription(user_id, category)
        status = "подписался" if is_subscribed else "отписался"
        await query.answer(f"Вы {status} от {category}")
        user_cats = await get_user_categories(user_id)
        keyboard = []
        for cat in CATEGORIES:
            icon = "✅" if cat in user_cats else "⬜"
            keyboard.append([InlineKeyboardButton(f"{icon} {cat}", callback_data=f"cat_{cat}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="menu")])
        await query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))

    elif data == "menu":
        await query.edit_message_text(
            "👋 Главное меню\n\nИспользуй кнопки ниже:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎯 Аирдропы", callback_data="list")],
                [InlineKeyboardButton("⚙️ Категории", callback_data="categories")],
                [InlineKeyboardButton("💰 Как заработать", callback_data="earn")],
                [InlineKeyboardButton("❓ Помощь", callback_data="help")]
            ]))

    elif data == "earn":
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
        await query.edit_message_text(EARN_TEXT, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "help":
        text = "📖 Помощь\n\nБот присылает уведомления об аирдропах с ИИ-оценками Cerebras.\nКоманды: /start /list /categories /earn /analyze /help"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🎯 Аирдропы":
        await list_airdrops(update, context)
    elif text == "⚙️ Категории":
        await categories_command(update, context)
    elif text == "💰 Как заработать":
        await earn_command(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "🏠 Главное меню":
        await start(update, context)
    elif text == "🔍 Анализ ссылки":
        await analyze_link_command(update, context)
    elif text == "🔧 Добавить аирдроп" and user.id in ADMIN_IDS:
        await update.message.reply_text("Используй команду:\n/add <категория> <название> <ссылка> [описание]")
    elif text == "🔄 Запустить парсинг" and user.id in ADMIN_IDS:
        await admin_parse(update, context)
    elif text.startswith("http"):
        await update.message.reply_text("🤖 Cerebras анализирует ссылку...")
        analysis = await cerebras_analyze("Пользовательская ссылка", "", text)
        result = (
            f"🔍 ИИ-анализ Cerebras\n\n"
            f"{_scam_emoji(analysis['scam_probability'])} Скам-риск: {analysis['scam_probability']}%\n"
            f"{_diff_stars(analysis['difficulty'])} Сложность: {analysis['difficulty']}/5\n"
            f"💰 Ожидаемый доход: ${analysis['expected_profit_usd']}\n"
            f"⏱ Время: ~{analysis['time_required_minutes']} мин\n\n"
            f"📝 Вывод: {analysis['summary']}\n\n"
            f"🚩 Флаги: {', '.join(analysis['red_flags'])}")
        await update.message.reply_text(result, disable_web_page_preview=True)
    else:
        await update.message.reply_text("Используй кнопки меню 👇")


async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if len(context.args) < 3:
        await update.message.reply_text("Использование:\n/add <категория> <название> <ссылка> [описание]")
        return
    category = context.args[0]
    title = context.args[1]
    link = context.args[2]
    description = " ".join(context.args[3:]) if len(context.args) > 3 else ""
    airdrop_id = await add_airdrop(title, description, link, category)
    await update.message.reply_text("🤖 Cerebras анализирует...")
    analysis = await cerebras_analyze(title, description, link)
    await save_airdrop_analysis(
        airdrop_id=airdrop_id,
        scam=analysis["scam_probability"],
        difficulty=analysis["difficulty"],
        profit=analysis["expected_profit_usd"],
        time_req=analysis["time_required_minutes"],
        summary=analysis["summary"],
        red_flags=json.dumps(analysis["red_flags"], ensure_ascii=False))
    await update.message.reply_text(
        f"✅ Аирдроп добавлен! ID: {airdrop_id}\n"
        f"{_scam_emoji(analysis['scam_probability'])} Скам-риск: {analysis['scam_probability']}%\n"
        f"⭐ Сложность: {analysis['difficulty']}/5\n"
        f"💰 Доход: ${analysis['expected_profit_usd']}")


async def admin_parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text("🔄 Запускаю парсинг + Cerebras анализ...")
    count = await fetch_and_save_airdrops()
    await update.message.reply_text(f"✅ Добавлено и проанализировано {count} аирдропов.")


async def check_new_airdrops(application: Application):
    while True:
        try:
            await fetch_and_save_airdrops()
            new_airdrops = await get_not_notified_airdrops()
            for airdrop in new_airdrops:
                airdrop_id = airdrop[0]
                title = airdrop[1]
                description = airdrop[2] or ""
                link = airdrop[3]
                category = airdrop[4]
                analysis = await get_airdrop_analysis(airdrop_id)
                subscribers = await get_users_by_category(category)
                if not subscribers:
                    subscribers = await get_all_active_users()

                ai_block = ""
                if analysis:
                    ai_block = (
                        f"\n\n{_scam_emoji(analysis['scam_probability'])} Скам-риск: {analysis['scam_probability']}%"
                        f"\n⭐ Сложность: {analysis['difficulty']}/5 | 💰 ~${analysis['expected_profit_usd']}"
                        f"\n📝 {analysis['summary']}")

                text = f"🆕 Новый аирдроп!\n\n*{title}*\nКатегория: {category}\n\n🔗 {link}{ai_block}"
                sent_count = 0
                for user_id in subscribers:
                    try:
                        await application.bot.send_message(
                            chat_id=user_id, text=text,
                            parse_mode="Markdown", disable_web_page_preview=True)
                        sent_count += 1
                        await asyncio.sleep(0.05)
                    except Exception as e:
                        logger.warning(f"Не удалось отправить {user_id}: {e}")
                await mark_as_notified(airdrop_id)
                logger.info(f"Аирдроп {title} разослан {sent_count} пользователям")
        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче: {e}")
        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)


async def post_init(application: Application):
    await init_db()
    # ТЕСТ: вызываем ИИ при старте, чтобы проверить ключ
    logger.info("[TEST] Проверяем Cerebras API при старте...")
    test_result = await cerebras_analyze("Test", "test desc", "https://example.com")
    logger.info(f"[TEST] Результат: риск={test_result['scam_probability']}%, ключ работает={test_result['scam_probability'] != 0 or test_result['summary'] != 'Базовая эвристика'}")

    asyncio.create_task(check_new_airdrops(application))
    logger.info("Бот запущен. Cerebras ИИ-фильтр активен.")


def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_airdrops))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("latest", list_airdrops))
    application.add_handler(CommandHandler("earn", earn_command))
    application.add_handler(CommandHandler("analyze", analyze_link_command))
    application.add_handler(CommandHandler("add", admin_add))
    application.add_handler(CommandHandler("parse", admin_parse))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    application.run_polling()


if __name__ == "__main__":
    main()
