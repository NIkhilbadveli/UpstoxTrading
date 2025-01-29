from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    filters,
    Application,
    ContextTypes,
    CallbackQueryHandler,
)
import pytz
from live_trading import do_live_trading
from upstox_utils import exit_all_positions, login_to_upstox_using_code
from datetime import datetime
from telegram import Bot

IST = pytz.timezone("Asia/Kolkata")

# Global variable to store the entered code
entered_code = None
bot_token = "7519201187:AAEiyULX9beIGpCTUbOQQWHqrtEE_5-qpYg"
script_running = False

# Upstox API Key
API_KEY = "c0147464-89c2-4b2c-9f8a-132f9e105027"


async def send_telegram_alert(message):
    chat_id = "5206375205"

    bot = Bot(token=bot_token)
    await bot.send_message(chat_id=chat_id, text=message)


async def get_upstox_login_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = "https://api.upstox.com/v2/login/authorization/dialog"

    # put the payload as query params
    payload = {
        "client_id": API_KEY,
        "redirect_uri": "https://google.co.in/",
        "response_type": "code",
    }
    url += "?"
    for key, value in payload.items():
        url += f"{key}={value}&"

    await update.message.reply_text(
        f"Click [here]({url}) to login to Upstox and then send the code.",
        parse_mode="Markdown",
    )


async def start_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global script_running
    today = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        with open("login_data.txt", "r") as f:
            last_login_date, access_token = f.read().strip().split(",")
    except (FileNotFoundError, ValueError):
        last_login_date, access_token = "", ""

    if last_login_date == today:
        print("Already logged in today.")
    
    if entered_code or last_login_date == today:
        # Ask for confirmation before starting the script
        keyboard = [
            [
                InlineKeyboardButton("Yes", callback_data="confirm_yes"),
                InlineKeyboardButton("No", callback_data="confirm_no"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Are you sure you want to exit all positions and start the script?",
            reply_markup=reply_markup,
        )
    else:
        await update.message.reply_text(
            "No code received. Use /send_code <code> to send the code."
        )


async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global entered_code
    if len(update.message.text.split(" ", 1)) < 2:
        await update.message.reply_text(
            "No code provided. Please use the command as /send_code <code>."
        )
    else:
        entered_code = update.message.text.split(" ", 1)[1]
        login_to_upstox_using_code(entered_code)
        await update.message.reply_text(
            f"Code received: {entered_code}. Now logging in. Use /start_trading to do live trading."
        )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_message = f"Code: {entered_code}\nScript running: {script_running}"
    await update.message.reply_text(status_message)


async def run_script(update: Update):
    global script_running, entered_code
    script_running = True
    print(f"Script started with code: {entered_code}")
    do_live_trading()
    print("Script stopped automatically.")
    # await update.message.reply_text("Script stopped automatically.")
    script_running = False
    entered_code = None


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global script_running
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    if query.data == "confirm_yes":
        await query.edit_message_text(
            "Exiting all positions and starting the script..."
        )
        exit_all_positions()
        await run_script(update)
    elif query.data == "confirm_no":
        await query.edit_message_text(
            "Not exiting positions but starting the script..."
        )
        await run_script(update)


def main():
    # Create the application with your bot's token
    application = Application.builder().token(bot_token).build()

    # Add command and message handlers
    application.add_handler(CommandHandler("login_to_upstox", get_upstox_login_url))
    application.add_handler(CommandHandler("send_code", receive_code))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("start_trading", start_script))

    application.add_handler(CallbackQueryHandler(handle_confirmation))

    print("Bot started. Now listening for commands...")
    # Start the bot
    application.run_polling()


send_telegram_alert("🚨 Bot is restarting...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        send_telegram_alert(f"⚠️ Bot crashed! Error: {str(e)}")
        raise e
