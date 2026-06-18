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
from tools.vision import identify_food
from tools.nutrition import lookup_nutrition

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

    photo_file = await update.message.photo[-1].get_file()
    local_path = DOWNLOADS_DIR / f"{user_id}_{message_id}.jpg"
    await photo_file.download_to_drive(str(local_path))

    logger.info("Photo saved: %s", local_path)
    await update.message.reply_text("Got your photo! Analyzing... 🔍")

    try:
        # Step 1: identify food items from image
        foods = identify_food(str(local_path))
        logger.info("Identified foods: %s", foods)

        # Step 2: look up nutrition for each item
        lines = []
        total_kcal = 0.0
        total_protein = 0.0
        total_fat = 0.0
        total_carbs = 0.0

        for item in foods:
            try:
                nutrition = lookup_nutrition(item["name"])
                total_kcal += nutrition["kcal_per_100g"]
                total_protein += nutrition["protein_g"]
                total_fat += nutrition["fat_g"]
                total_carbs += nutrition["carbs_g"]
                lines.append(
                    f"• {item['name']}\n"
                    f"  {nutrition['kcal_per_100g']} kcal | "
                    f"{nutrition['protein_g']}g protein | "
                    f"{nutrition['fat_g']}g fat | "
                    f"{nutrition['carbs_g']}g carbs"
                )
            except ValueError:
                lines.append(f"• {item['name']} — nutrition not found")

        reply = (
            "🍽 *Meal Analysis*\n\n"
            + "\n".join(lines)
            + f"\n\n📊 *Total (per 100g each)*\n"
            f"Calories: {total_kcal:.1f} kcal\n"
            f"Protein: {total_protein:.1f}g\n"
            f"Fat: {total_fat:.1f}g\n"
            f"Carbs: {total_carbs:.1f}g"
        )
        await update.message.reply_text(reply, parse_mode="Markdown")

    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        await update.message.reply_text(f"Sorry, something went wrong: {str(e)}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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