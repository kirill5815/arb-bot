import asyncio
import json
import logging
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
from ai_filter import analyze_airdrop

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CATEGORIES = ["DeFi", "NFT", "Testnet", "Gaming", "Layer2", "Other"]

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
    "3. Регистрация на проектах, выполнение заданий (Discord, Twitter, тестовые транзакции)\n"
    "4. Ожидание 3–12 месяцев до раздачи токенов\n"
    "5. Продажа токенов сразу после листинга (часто падают на 50–80% за неделю)\n\n"
    "⚠️ Риски:\n"
    "• Потеря времени: 30 мин – 2 часа на 1 аирдроп\n"
    "• Потеря денег на газе, если проект не раздаёт\n"
    "• Скам-проекты крадут приватные ключи\n"
    "• Мультиаккаунты (10+ кошельков) увеличивают доход, но требуют больше времени и средств\n\n"
    "💡 Совет: делай 10–20 качественных аирдропов в месяц. "
    "Диверсифицируй по категориям (DeFi, Layer2, Gaming). "
    "Не гонись за каждой раздачей — фильтруй через бота."
)


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎯 Аирдропы"), KeyboardButton("⚙️ Категории")],
            [KeyboardButton("💰 Как заработать"), KeyboardButton("🔍 Анализ ссылки")],
            [KeyboardButton("❓ Помощь"), KeyboardButton("🏠 Главное меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎯 Аирдропы"), KeyboardButton("⚙️ Категории")],
            [KeyboardButton("💰 Как заработать"), KeyboardButton("🔍 Анализ ссылки")],
            [KeyboardButton("❓ Помощь"), KeyboardButton("🏠 Главное меню")],
            [KeyboardButton("🔧 Добавить аирдроп"), KeyboardButton("🔄 Запустить парсинг")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )


def _scam_emoji(score: int) -> str:
    if score >= 70:
        return "🔴"
    elif score >= 40:
        return "🟡"
    return "🟢"


def _diff_stars(d: int) -> str:
    return "⭐" * d + "☆" * (5 - d)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_user(user.id, user.username)
    is_admin = user.id in ADMIN_IDS
    keyboard = get_admin_keyboard() if is_admin else get_main_keyboard()
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для мониторинга крипто-аирдропов с ИИ-фильтром. "
        "Проверяю скам-риски, сложность и доходность автоматически.",
        reply_markup=keyboard
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 Команды бота:\n\n"
        "🎯 Аирдропы — список с ИИ-оценками\n"
        "⚙️ Категории — настройка уведомлений\n"
        "💰 Как заработать — инструкция и доходы\n"
        "🔍 Анализ ссылки — ИИ-проверка любого аирдропа\n"
        "❓ Помощь — это сообщение\n"
        "🏠 Главное меню — вернуться в начало\n\n"
        "Или используй команды:\n"
        "/start /list /categories /earn /analyze /help\n\n"
        f"🔔 Автопроверка каждые {CHECK_INTERVAL_MINUTES} минут."
    )
    await update.message.reply_text(text)


async def earn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(EARN_TEXT)


async def analyze_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🔍 Отправь ссылку на аирдроп для ИИ-анализа:\n"
            "Пример: /analyze https://example.com/airdrop\n\n"
            "Или просто отправь ссылку в чат, начинающуюся с http"
        )
        return
    link = context.args[0]
    await update.message.reply_text("🤖 Анализирую ссылку через ИИ...")
    analysis = await analyze_airdrop("Пользовательская ссылка", "", link)
    text = (
        f"🔍 ИИ-анализ: {link}\n\n"
        f"{_scam_emoji(analysis['scam_probability'])} Скам-риск: {analysis['scam_probability']}%\n"
        f"{_diff_stars(analysis['difficulty'])} Сложность: {analysis['difficulty']}/5\n"
        f"💰 Ожидаемый доход: ${analysis['expected_profit_usd']}\n"
        f"⏱ Время: ~{analysis['time_required_minutes']} мин\n\n"
        f"📝 Вывод: {analysis['summary']}\n\n"
        f"🚩 Флаги: {', '.join(analysis['red_flags'])}"
    )
    await update.message.reply_text(text, disable_web_page_preview=True)


async def list_airdrops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    airdrops = await get_active_airdrops(limit=10)
    if not airdrops:
        await update.message.reply_text("😕 Пока нет активных аирдропов.")
        return
    text = "🎯 Активные аирдропы (с ИИ-оценками):\n\n"
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
            ai_line = "\n🤖 ИИ-анализ: в обработке..."
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
        "⚙️ Выбери категории для уведомлений:\n"
        "(Нажми на категорию, чтобы подписаться/отписаться)",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


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
                scam = analysis["scam_probability"]
                diff = analysis["difficulty"]
                profit = analysis["expected_profit_usd"]
                ai_line = f"\n{_scam_emoji(scam)} Риск: {scam}% | ⭐{diff}/5 | 💰~${profit}"
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
            ])
        )

    elif data == "earn":
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
        await query.edit_message_text(EARN_TEXT, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "help":
        text = (
            "📖 Помощь\n\n"
            "Бот присылает уведомления об аирдропах с ИИ-оценками.\n"
            "Если не выбрано ни одной категории — приходят все уведомления.\n\n"
            "Команды: /start /list /categories /earn /analyze /help"
        )
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
        await update.message.reply_text(
            "Используй команду:\n"
            "/add <категория> <название> <ссылка> [описание]"
        )
    elif text == "🔄 Запустить парсинг" and user.id in ADMIN_IDS:
        await admin_parse(update, context)
    elif text.startswith("http"):
        # Авто-анализ ссылок
        await update.message.reply_text("🤖 Анализирую ссылку через ИИ...")
        analysis = await analyze_airdrop("Пользовательская ссылка", "", text)
        result = (
            f"🔍 ИИ-анализ\n\n"
            f"{_scam_emoji(analysis['scam_probability'])} Скам-риск: {analysis['scam_probability']}%\n"
            f"{_diff_stars(analysis['difficulty'])} Сложность: {analysis['difficulty']}/5\n"
            f"💰 Ожидаемый доход: ${analysis['expected_profit_usd']}\n"
            f"⏱ Время: ~{analysis['time_required_minutes']} мин\n\n"
            f"📝 Вывод: {analysis['summary']}\n\n"
            f"🚩 Флаги: {', '.join(analysis['red_flags'])}"
        )
        await update.message.reply_text(result, disable_web_page_preview=True)
    else:
        await update.message.reply_text("Используй кнопки меню 👇")


async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "Использование:\n/add <категория> <название> <ссылка> [описание]"
        )
        return
    category = context.args[0]
    title = context.args[1]
    link = context.args[2]
    description = " ".join(context.args[3:]) if len(context.args) > 3 else ""
    airdrop_id = await add_airdrop(title, description, link, category)
    # AI анализ при ручном добавлении
    await update.message.reply_text("🤖 Запускаю ИИ-анализ...")
    analysis = await analyze_airdrop(title, description, link)
    await save_airdrop_analysis(
        airdrop_id=airdrop_id,
        scam=analysis["scam_probability"],
        difficulty=analysis["difficulty"],
        profit=analysis["expected_profit_usd"],
        time_req=analysis["time_required_minutes"],
        summary=analysis["summary"],
        red_flags=json.dumps(analysis["red_flags"], ensure_ascii=False)
    )
    await update.message.reply_text(
        f"✅ Аирдроп добавлен! ID: {airdrop_id}\n"
        f"{_scam_emoji(analysis['scam_probability'])} Скам-риск: {analysis['scam_probability']}%\n"
        f"⭐ Сложность: {analysis['difficulty']}/5\n"
        f"💰 Доход: ${analysis['expected_profit_usd']}"
    )


async def admin_parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text("🔄 Запускаю парсинг + ИИ-анализ...")
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
                        f"\n📝 {analysis['summary']}"
                    )

                text = f"🆕 Новый аирдроп!\n\n*{title}*\nКатегория: {category}\n\n🔗 {link}{ai_block}"
                sent_count = 0
                for user_id in subscribers:
                    try:
                        await application.bot.send_message(
                            chat_id=user_id, text=text,
                            parse_mode="Markdown", disable_web_page_preview=True
                        )
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
    asyncio.create_task(check_new_airdrops(application))
    logger.info("Бот запущен. Фоновая задача, парсер и ИИ-фильтр активны.")


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
