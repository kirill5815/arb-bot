import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from config import BOT_TOKEN, ADMIN_IDS, CHECK_INTERVAL_MINUTES
from database import (
    init_db, add_user, toggle_subscription, get_user_categories,
    get_active_airdrops, add_airdrop, get_not_notified_airdrops,
    mark_as_notified, get_all_active_users, get_users_by_category
)
from parser import fetch_and_save_airdrops

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CATEGORIES = ["DeFi", "NFT", "Testnet", "Gaming", "Layer2", "Other"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_user(user.id, user.username)
    keyboard = [
        [InlineKeyboardButton("Текущие аирдропы", callback_data="list")],
        [InlineKeyboardButton("Настроить категории", callback_data="categories")],
        [InlineKeyboardButton("Помощь", callback_data="help")]
    ]
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n\n"
        "Я бот для мониторинга крипто-аирдропов. "
        "Буду присылать уведомления о новых раздачах.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Команды бота:\n\n"
        "/start — Главное меню\n"
        "/list — Активные аирдропы\n"
        "/categories — Категории уведомлений\n"
        "/latest — Последние аирдропы\n"
        "/parse — Принудительный парсинг (админ)\n\n"
        f"Проверка новых аирдропов каждые {CHECK_INTERVAL_MINUTES} минут."
    )
    await update.message.reply_text(text)


async def list_airdrops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    airdrops = await get_active_airdrops(limit=10)
    if not airdrops:
        await update.message.reply_text("Пока нет активных аирдропов.")
        return
    text = "Активные аирдропы:\n\n"
    for airdrop in airdrops:
        title = airdrop[1]
        category = airdrop[4]
        link = airdrop[3]
        desc = airdrop[2] or ""
        text += f"{title} ({category})\n{link}\n{desc[:100]}\n\n"
    await update.message.reply_text(text, disable_web_page_preview=True)


async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_cats = await get_user_categories(user_id)
    keyboard = []
    for cat in CATEGORIES:
        icon = "✅" if cat in user_cats else "⬜"
        keyboard.append([InlineKeyboardButton(f"{icon} {cat}", callback_data=f"cat_{cat}")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data="menu")])
    await update.message.reply_text(
        "Выбери категории для уведомлений:",
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
            await query.edit_message_text("Пока нет активных аирдропов.")
            return
        text = "Активные аирдропы:\n\n"
        for airdrop in airdrops:
            text += f"{airdrop[1]} ({airdrop[4]})\n{airdrop[3]}\n\n"
        keyboard = [[InlineKeyboardButton("Назад", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

    elif data == "categories":
        user_cats = await get_user_categories(user_id)
        keyboard = []
        for cat in CATEGORIES:
            icon = "✅" if cat in user_cats else "⬜"
            keyboard.append([InlineKeyboardButton(f"{icon} {cat}", callback_data=f"cat_{cat}")])
        keyboard.append([InlineKeyboardButton("Назад", callback_data="menu")])
        await query.edit_message_text("Выбери категории:", reply_markup=InlineKeyboardMarkup(keyboard))

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
        keyboard.append([InlineKeyboardButton("Назад", callback_data="menu")])
        await query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))

    elif data == "menu":
        keyboard = [
            [InlineKeyboardButton("Текущие аирдропы", callback_data="list")],
            [InlineKeyboardButton("Настроить категории", callback_data="categories")],
            [InlineKeyboardButton("Помощь", callback_data="help")]
        ]
        await query.edit_message_text("Главное меню\n\nВыбери действие:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "help":
        text = (
            "Помощь\n\n"
            "Бот присылает уведомления об аирдропах по выбранным категориям.\n"
            "Если не выбрано ни одной категории — приходят все уведомления."
        )
        keyboard = [[InlineKeyboardButton("Назад", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Нет доступа.")
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
    await update.message.reply_text(f"Аирдроп добавлен! ID: {airdrop_id}")


async def admin_parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Нет доступа.")
        return
    await update.message.reply_text("Запускаю парсинг...")
    count = await fetch_and_save_airdrops()
    await update.message.reply_text(f"Добавлено {count} аирдропов из внешних источников.")


async def check_new_airdrops(application: Application):
    """Фоновая задача: парсит сайты и рассылает уведомления."""
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
                subscribers = await get_users_by_category(category)
                if not subscribers:
                    subscribers = await get_all_active_users()
                text = f"Новый аирдроп!\n\n{title}\nКатегория: {category}\n\n{link}\n\n{description[:200]}"
                sent_count = 0
                for user_id in subscribers:
                    try:
                        await application.bot.send_message(chat_id=user_id, text=text, disable_web_page_preview=True)
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
    logger.info("Бот запущен. Фоновая задача и парсер активны.")


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
    application.add_handler(CommandHandler("add", admin_add))
    application.add_handler(CommandHandler("parse", admin_parse))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling()


if __name__ == "__main__":
    main()
