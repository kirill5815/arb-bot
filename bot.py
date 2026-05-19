import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from config import BOT_TOKEN, CHAT_ID, POLL_SEC
from scanner import Scanner
from state import state

scanner = Scanner()

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Включить мониторинг", callback_data="on"),
         InlineKeyboardButton("Выключить мониторинг", callback_data="off")],
        [InlineKeyboardButton("Статус", callback_data="status"),
         InlineKeyboardButton("Порог прибыли", callback_data="profit")],
        [InlineKeyboardButton("Фильтр монет", callback_data="symbols"),
         InlineKeyboardButton("Сбросить фильтр", callback_data="clear_symbols")],
    ])

def symbols_menu():
    pairs = scanner.common_symbols[:12]
    rows = []
    row = []
    for i, sym in enumerate(pairs, 1):
        row.append(InlineKeyboardButton(sym, callback_data=f"sym:{sym}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Бот для мониторинга межбиржевых спотовых спредов.\n"
        "Выберите действие в меню."
    )
    await update.message.reply_text(text, reply_markup=main_menu())

async def status_text():
    filt = ", ".join(sorted(state.symbol_filter)) if state.symbol_filter else "без фильтра"
    return (
        f"Monitoring: {state.monitoring}\n"
        f"Min profit: {state.min_profit_pct if state.min_profit_pct is not None else 'default'}\n"
        f"Filter: {filt}\n"
        f"Common pairs: {len(scanner.common_symbols)}"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "on":
        state.monitoring = True
        await query.edit_message_text("Мониторинг включён.", reply_markup=main_menu())

    elif data == "off":
        state.monitoring = False
        await query.edit_message_text("Мониторинг выключён.", reply_markup=main_menu())

    elif data == "status":
        await query.edit_message_text(await status_text(), reply_markup=main_menu())

    elif data == "profit":
        state.awaiting_profit_input = True
        await query.edit_message_text("Отправьте новое значение порога прибыли сообщением, например: 0.5", reply_markup=main_menu())

    elif data == "symbols":
        await query.edit_message_text("Выберите монету для фильтра.", reply_markup=symbols_menu())

    elif data == "clear_symbols":
        state.symbol_filter = set()
        await query.edit_message_text("Фильтр монет очищен.", reply_markup=main_menu())

    elif data == "back":
        await query.edit_message_text("Главное меню.", reply_markup=main_menu())

    elif data.startswith("sym:"):
        sym = data.split("sym:", 1)[1]
        if sym in state.symbol_filter:
            state.symbol_filter.remove(sym)
        else:
            state.symbol_filter.add(sym)
        await query.edit_message_text(
            f"Фильтр обновлён.\nТекущие монеты: {', '.join(sorted(state.symbol_filter)) if state.symbol_filter else 'нет'}",
            reply_markup=symbols_menu()
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if state.awaiting_profit_input:
        try:
            state.min_profit_pct = float(update.message.text.strip())
            state.awaiting_profit_input = False
            await update.message.reply_text(f"Порог прибыли установлен: {state.min_profit_pct:.3f}%", reply_markup=main_menu())
        except ValueError:
            await update.message.reply_text("Введите число, например 0.5")
    else:
        await update.message.reply_text("Используйте меню.", reply_markup=main_menu())

async def notify_signal(app, signal):


= (
        f"Сигнал\n"
        f"Пара: {signal['symbol']}\n"
        f"BUY {signal['buy_ex']} @ {signal['buy_price']}\n"
        f"SELL {signal['sell_ex']} @ {signal['sell_price']}\n"
        f"Профит ≈ {signal['profit']:.3f}%"
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=text)

async def scan_loop(app):
    while True:
        try:
            if state.monitoring:
                min_profit = state.min_profit_pct if state.min_profit_pct is not None else 0.30
                results = scanner.scan(min_profit, state.symbol_filter)
                for signal in results[:10]:
                    key = (signal["symbol"], signal["buy_ex"], signal["sell_ex"])
                    sig = round(signal["profit"], 3)
                    if state.last_signals.get(key) != sig:
                        await notify_signal(app, signal)
                        state.last_signals[key] = sig
            await asyncio.sleep(POLL_SEC)
        except Exception as e:
            await app.bot.send_message(chat_id=CHAT_ID, text=f"Ошибка: {e}")
            await asyncio.sleep(5)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    async def post_init(application):
        application.create_task(scan_loop(application))

    app.post_init = post_init
    app.run_polling()

if __name__ == "__main__":
    main() text