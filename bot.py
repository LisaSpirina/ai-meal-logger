# bot.py
import os
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from db.init_db import init_db
from agent.react_loop import run_meal_logging, run_text_logging, _format_reply_from_collected
import tools.db as db
from tools.nutrition import lookup_nutrition
from tools.portion import estimate_portion
from jobs.weekly_insight import format_week_insights

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

GOALS_KCAL, GOALS_PROTEIN = range(2)
_pending_meals: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your AI Meal Logger.\n\n"
        "Send me a photo of any meal and I'll identify it and log the nutrition.\n\n"
        "Use /goals to set your daily calorie and protein targets first."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available commands:\n"
        "/start — Introduction\n"
        "/goals — Set calorie and protein targets\n"
        "/today — Today's nutrition summary\n"
        "/week — Weekly summary and insights\n"
        "/history — Your last 10 meals\n"
        "/log — Manually log a meal by name\n"
        "/discard — Cancel pending meal confirmation\n"
        "/help — This message\n\n"
        "Or just send me a photo of your meal!"
    )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)
    summary = db.get_today_summary(user.id)

    if summary["meals_count"] == 0:
        await update.message.reply_text(
            "No meals logged today yet. Send me a photo to get started! 📸"
        )
        return

    await update.message.reply_text(
        f"📊 *Today's Summary*\n\n"
        f"Meals logged: {summary['meals_count']}\n\n"
        f"*Calories*\n"
        f"  Eaten: {summary['total_kcal']:.0f} kcal\n"
        f"  Goal:  {summary['daily_kcal']:.0f} kcal\n"
        f"  Left:  {summary['kcal_remaining']:.0f} kcal\n\n"
        f"*Protein*\n"
        f"  Eaten: {summary['total_protein_g']:.1f}g\n"
        f"  Goal:  {summary['daily_protein_g']:.0f}g\n"
        f"  Left:  {summary['protein_remaining']:.1f}g\n\n"
        f"*Fat:*   {summary['total_fat_g']:.1f}g\n"
        f"*Carbs:* {summary['total_carbs_g']:.1f}g",
        parse_mode="Markdown",
    )


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)
    message = format_week_insights(user.id)
    await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)
    meals = db.get_meal_history(user.id, limit=10)

    if not meals:
        await update.message.reply_text(
            "No meals logged yet. Send me a photo to get started! 📸"
        )
        return

    lines = ["🗂 *Meal History*\n"]
    for meal in meals:
        dt = meal["timestamp"][:16]
        lines.append(
            f"📅 {dt}\n"
            f"  {meal['total_kcal']:.0f} kcal | {meal['total_protein_g']:.1f}g protein\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_discard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id in _pending_meals:
        _pending_meals.pop(user_id)
        await update.message.reply_text("Discarded. Send a new photo when ready.")
    else:
        await update.message.reply_text("Nothing pending to discard.")


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)

    meal_text = " ".join(context.args)
    if not meal_text:
        await update.message.reply_text(
            "Please describe your meal after the command.\n"
            "Example: /log chicken rice and broccoli"
        )
        return

    await update.message.reply_text(
        f"Got it! Looking up nutrition for: {meal_text}... 🔍"
    )

    try:
        loop = asyncio.get_event_loop()
        reply, items = await loop.run_in_executor(
            None, run_text_logging, user.id, meal_text
        )
        db.save_meal(user.id, None, reply, items)
    except Exception as exc:
        logger.error("cmd_log failed: %s", exc, exc_info=True)
        reply = "Sorry, something went wrong. Please try again."

    await update.message.reply_text(reply)


# ---------------------------------------------------------------------------
# /goals conversation
# ---------------------------------------------------------------------------

async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)
    goals = db.get_goals(user.id)
    await update.message.reply_text(
        f"Let's set your daily targets.\n\n"
        f"Current calorie goal: {goals['daily_kcal']:.0f} kcal\n\n"
        "What's your daily calorie target? (e.g. 2000)"
    )
    return GOALS_KCAL


async def goals_set_kcal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        kcal = float(update.message.text.strip())
        if kcal < 500 or kcal > 10000:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number between 500 and 10000."
        )
        return GOALS_KCAL

    context.user_data["new_kcal"] = kcal
    goals = db.get_goals(update.effective_user.id)
    await update.message.reply_text(
        f"Got it — {kcal:.0f} kcal/day.\n\n"
        f"Current protein goal: {goals['daily_protein_g']:.0f}g\n\n"
        "What's your daily protein target in grams? (e.g. 150)"
    )
    return GOALS_PROTEIN


async def goals_set_protein(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        protein = float(update.message.text.strip())
        if protein < 10 or protein > 500:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number between 10 and 500."
        )
        return GOALS_PROTEIN

    user_id = update.effective_user.id
    kcal = context.user_data["new_kcal"]
    db.set_goals(user_id, kcal, protein)
    await update.message.reply_text(
        f"✅ Goals updated!\n\n"
        f"Daily calories: {kcal:.0f} kcal\n"
        f"Daily protein:  {protein:.0f}g"
    )
    return ConversationHandler.END


async def goals_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Goal setting cancelled.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Photo handler
# ---------------------------------------------------------------------------

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)
    message_id = update.message.message_id

    if user.id in _pending_meals:
        await update.message.reply_text(
            "You still have a meal waiting to be confirmed! "
            "Please save it first or send /discard to start fresh."
        )
        return

    photo_file = await update.message.photo[-1].get_file()
    local_path = DOWNLOADS_DIR / f"{user.id}_{message_id}.jpg"
    await photo_file.download_to_drive(str(local_path))

    logger.info("Photo saved: %s", local_path)
    await update.message.reply_text(
        "Got your photo! Analyzing your meal... 🔍\n"
        "_(This takes about 2 minutes for complex meals)_",
        parse_mode="Markdown"
    )

    try:
        loop = asyncio.get_event_loop()
        reply, items = await loop.run_in_executor(
            None, run_meal_logging, user.id, str(local_path)
        )
    except Exception as exc:
        logger.error("handle_photo failed: %s", exc, exc_info=True)
        await update.message.reply_text(
            "Sorry, something went wrong analyzing your photo. Please try again."
        )
        return

    if not items:
        await update.message.reply_text(reply)
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Looks right, save it!", callback_data="confirm"),
            InlineKeyboardButton("✏️ Edit portions", callback_data="edit"),
            InlineKeyboardButton("➕ Add item", callback_data="add"),
        ]
    ]

    _pending_meals[user.id] = {
        "items": items,
        "summary": reply,
        "image_path": str(local_path),
    }

    sent = await update.message.reply_text(
        reply + "\n\nDoes this look right?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    _pending_meals[user.id]["message_id"] = sent.message_id
    _pending_meals[user.id]["chat_id"] = update.effective_chat.id


# ---------------------------------------------------------------------------
# Confirmation keyboard handler
# ---------------------------------------------------------------------------

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "confirm":
        pending = _pending_meals.pop(user_id, None)
        if not pending:
            await query.edit_message_text("Session expired. Please send the photo again.")
            return

        try:
            db.save_meal(
                user_id,
                pending.get("image_path"),
                pending["summary"],
                pending["items"],
            )
            logger.info("Meal saved to DB for user %s", user_id)
        except Exception as exc:
            logger.error("Failed to save meal: %s", exc, exc_info=True)

        breakdown_message_id = pending.get("message_id")
        current_message_id = query.message.message_id

        try:
            await context.bot.edit_message_text(
                chat_id=pending["chat_id"],
                message_id=breakdown_message_id,
                text=pending["summary"] + "\n\n✅ Meal logged!",
                parse_mode="Markdown"
            )
        except Exception as exc:
            logger.warning("Could not edit original message: %s", exc)

        if current_message_id != breakdown_message_id:
            try:
                await query.delete_message()
            except Exception as exc:
                logger.warning("Could not delete button message: %s", exc)

    elif query.data == "edit":
        await query.message.reply_text(
            "Which item would you like to correct?\n"
            "Reply with: *food name, actual grams*\n"
            "Example: _chicken breast, 200_",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_correction"] = True
        context.user_data["awaiting_addition"] = False

    elif query.data == "add":
        await query.message.reply_text(
            "What would you like to add?\n"
            "Reply with: *food name, grams*\n"
            "Example: _brown rice, 150_",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_addition"] = True
        context.user_data["awaiting_correction"] = False


# ---------------------------------------------------------------------------
# Text handler
# ---------------------------------------------------------------------------

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if context.user_data.get("awaiting_addition") and context.user_data.get("awaiting_correction"):
        context.user_data["awaiting_addition"] = False
        context.user_data["awaiting_correction"] = False

    if context.user_data.get("awaiting_correction"):
        text = update.message.text.strip()
        try:
            parts = [p.strip() for p in text.split(",")]
            if len(parts) != 2:
                raise ValueError
            food_name, grams_str = parts
            grams = int(grams_str.replace("g", "").strip())
        except ValueError:
            await update.message.reply_text(
                "Couldn't parse that. Try one item at a time: _chicken breast, 200_",
                parse_mode="Markdown"
            )
            return

        context.user_data["awaiting_correction"] = False

        pending = _pending_meals.get(user_id)
        if not pending:
            await update.message.reply_text("Session expired. Please send the photo again.")
            return

        matched = False
        for item in pending["items"]:
            if food_name.lower() in item.get("name", "").lower():
                item["grams"] = grams
                item["user_corrected"] = True
                matched = True
                if item.get("kcal_per_100g", 0) == 0:
                    try:
                        nutrition = lookup_nutrition(food_name)
                        item.update(nutrition)
                        item["name"] = food_name  # keep user's name
                        logger.info("Re-fetched nutrition for '%s'", food_name)
                    except (ValueError, RuntimeError) as exc:
                        logger.warning(
                            "Could not re-fetch nutrition for '%s': %s",
                            food_name, exc
                        )
                break

        if not matched:
            item_names = [i.get("name", "unknown") for i in pending["items"]]
            await update.message.reply_text(
                f"Couldn't find '{food_name}'. Logged items are:\n"
                + "\n".join(f"• {n}" for n in item_names)
                + "\n\nTry using one of these names exactly."
            )
            context.user_data["awaiting_correction"] = True
            return

        updated_reply = _format_reply_from_collected("Meal logged.", pending["items"])
        pending["summary"] = updated_reply

        keyboard = [[
            InlineKeyboardButton("✅ Save", callback_data="confirm"),
            InlineKeyboardButton("✏️ Edit more", callback_data="edit"),
            InlineKeyboardButton("➕ Add item", callback_data="add"),
        ]]
        sent = await update.message.reply_text(
            f"✏️ Updated {food_name} to {grams}g.\n\nAnything else, or save?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        pending["message_id"] = sent.message_id
        pending["chat_id"] = update.effective_chat.id
        return

    if context.user_data.get("awaiting_addition"):
        text = update.message.text.strip()
        try:
            parts = [p.strip() for p in text.split(",")]
            if len(parts) != 2:
                raise ValueError
            food_name, grams_str = parts
            grams = int(grams_str.replace("g", "").strip())
        except ValueError:
            await update.message.reply_text(
                "Couldn't parse that. Try: _brown rice, 150_",
                parse_mode="Markdown"
            )
            return

        context.user_data["awaiting_addition"] = False

        pending = _pending_meals.get(user_id)
        if not pending:
            await update.message.reply_text("Session expired. Please send the photo again.")
            return

        try:
            nutrition = lookup_nutrition(food_name)
            portion = estimate_portion(food_name)
            new_item = {**nutrition, **portion, "grams": grams, "user_added": True}
            pending["items"].append(new_item)
        except ValueError:
            await update.message.reply_text(
                f"Couldn't find '{food_name}' in the nutrition database. "
                f"Try a simpler name like 'brown rice'."
            )
            context.user_data["awaiting_addition"] = True
            return
        except RuntimeError as exc:
            logger.error("Nutrition lookup failed for added item: %s", exc)
            await update.message.reply_text("Nutrition lookup failed. Please try again.")
            return

        updated_reply = _format_reply_from_collected("Meal logged.", pending["items"])
        pending["summary"] = updated_reply

        keyboard = [[
            InlineKeyboardButton("✅ Save", callback_data="confirm"),
            InlineKeyboardButton("✏️ Edit more", callback_data="edit"),
            InlineKeyboardButton("➕ Add item", callback_data="add"),
        ]]
        sent = await update.message.reply_text(
            updated_reply + "\n\nDoes this look right?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        pending["message_id"] = sent.message_id
        pending["chat_id"] = update.effective_chat.id
        return

    await update.message.reply_text(
        "Send me a photo to log a meal, or use /help for commands."
    )


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Update caused error: %s", context.error, exc_info=context.error)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in .env")

    init_db()

    app = ApplicationBuilder().token(token).build()

    goals_handler = ConversationHandler(
        entry_points=[CommandHandler("goals", cmd_goals)],
        states={
            GOALS_KCAL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, goals_set_kcal)],
            GOALS_PROTEIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, goals_set_protein)],
        },
        fallbacks=[CommandHandler("cancel", goals_cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("log", cmd_log))
    app.add_handler(CommandHandler("discard", cmd_discard))
    app.add_handler(goals_handler)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_confirmation))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()