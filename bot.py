# bot.py
import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your AI Meal Logger.\n\n"
        "Send me a photo of any meal and I'll identify it and log the nutrition.\n\n"
        "Use /goals to set your daily targets first."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available commands:\n"
        "/start — Introduction\n"
        "/goals — Set calorie and protein targets\n"
        "/today — Today's nutrition summary\n"
        "/week — Weekly summary\n"
        "/help — This message\n\n"
        "Or just send me a photo of your meal!"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message_id = update.message.message_id

    # Telegram sends multiple resolutions — take the largest
    photo_file = await update.message.photo[-1].get_file()
    local_path = DOWNLOADS_DIR / f"{user_id}_{message_id}.jpg"
    await photo_file.download_to_drive(str(local_path))

    logger.info("Photo saved: %s", local_path)

    await update.message.reply_text("Got your photo! Analyzing... 🔍")

    # TODO: hand local_path to the ReAct agent (week 1 day 3+)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Placeholder — will handle portion confirmations and corrections later
    await update.message.reply_text(
        "Send me a photo to log a meal, or use /help for commands."
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Update caused error: %s", context.error, exc_info=context.error)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in .env")

    app = (
        ApplicationBuilder()
        .token(token)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()