# jobs/weekly_insight.py
import logging
import tools.db as db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def get_week_insights(user_id: int) -> dict:
    days  = db.get_week_summary(user_id)
    goals = db.get_goals(user_id)

    if not days:
        return {"has_data": False}

    daily_kcal    = goals["daily_kcal"]
    daily_protein = goals["daily_protein_g"]
    KCAL_TOLERANCE = 200

    avg_kcal    = sum(d["total_kcal"]      for d in days) / len(days)
    avg_protein = sum(d["total_protein_g"] for d in days) / len(days)
    avg_meals   = sum(d["meals_count"]     for d in days) / len(days)

    days_on_goal = sum(1 for d in days if abs(d["total_kcal"] - daily_kcal) <= KCAL_TOLERANCE)
    days_over    = sum(1 for d in days if d["total_kcal"] > daily_kcal + KCAL_TOLERANCE)
    days_under   = sum(1 for d in days if d["total_kcal"] < daily_kcal - KCAL_TOLERANCE)

    best_protein_day  = max(days, key=lambda d: d["total_protein_g"])
    worst_protein_day = min(days, key=lambda d: d["total_protein_g"])

    mid = len(days) // 2
    if mid > 0:
        first_avg  = sum(d["total_kcal"] for d in days[:mid]) / mid
        second_avg = sum(d["total_kcal"] for d in days[mid:]) / max(len(days) - mid, 1)
        diff = second_avg - first_avg
        kcal_trend = (
            "stable" if abs(diff) < 100
            else ("increasing" if diff > 0 else "decreasing")
        )
    else:
        kcal_trend = "stable"

    return {
        "has_data":             True,
        "logged_days":          len(days),
        "missed_days":          7 - len(days),
        "avg_kcal":             round(avg_kcal, 1),
        "avg_protein_g":        round(avg_protein, 1),
        "daily_kcal":           daily_kcal,
        "daily_protein_g":      daily_protein,
        "days_on_kcal_goal":    days_on_goal,
        "days_over_kcal_goal":  days_over,
        "days_under_kcal_goal": days_under,
        "kcal_trend":           kcal_trend,
        "best_protein_day":     best_protein_day["date"],
        "worst_protein_day":    worst_protein_day["date"],
        "avg_meals_per_day":    round(avg_meals, 1),
        "daily_breakdown":      days,
    }


def get_most_logged_foods(user_id: int, days: int = 7, limit: int = 5) -> list[dict]:
    import sqlite3
    from pathlib import Path
    from contextlib import contextmanager

    @contextmanager
    def _conn():
        conn = sqlite3.connect(Path("data/meals.db"))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT
                mi.name,
                COUNT(*)      AS times_logged,
                AVG(mi.grams) AS avg_grams
            FROM meal_items mi
            JOIN meal_log m ON mi.meal_id = m.id
            WHERE m.user_id = ?
              AND DATE(m.timestamp) >= DATE('now', ?)
            GROUP BY LOWER(mi.name)
            ORDER BY times_logged DESC, avg_grams DESC
            LIMIT ?
            """,
            (user_id, f"-{days - 1} days", limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_week_insights(user_id: int) -> str:
    insights = get_week_insights(user_id)

    if not insights["has_data"]:
        return "No meals logged this week yet. Send me a photo to get started! 📸"

    top_foods    = get_most_logged_foods(user_id)
    kcal_vs_goal = insights["avg_kcal"] - insights["daily_kcal"]
    kcal_diff    = f"+{kcal_vs_goal:.0f}" if kcal_vs_goal > 0 else f"{kcal_vs_goal:.0f}"
    protein_pct  = (
        insights["avg_protein_g"] / insights["daily_protein_g"] * 100
        if insights["daily_protein_g"] else 0
    )
    trend_emoji = {
        "increasing": "📈",
        "decreasing": "📉",
        "stable":     "➡️",
    }.get(insights["kcal_trend"], "➡️")

    lines = [
        "📊 *Weekly Insights*\n",
        f"🗓 Days logged: {insights['logged_days']}/7"
        + (f" ({insights['missed_days']} missed)" if insights["missed_days"] else ""),
        f"🍽 Avg meals/day: {insights['avg_meals_per_day']}",
        "",
        "*Calories*",
        f"  Avg: {insights['avg_kcal']:.0f} kcal/day "
        f"(goal: {insights['daily_kcal']:.0f}, {kcal_diff})",
        f"  On goal: {insights['days_on_kcal_goal']} days | "
        f"Over: {insights['days_over_kcal_goal']} | "
        f"Under: {insights['days_under_kcal_goal']}",
        f"  Trend: {trend_emoji} {insights['kcal_trend'].capitalize()}",
        "",
        "*Protein*",
        f"  Avg: {insights['avg_protein_g']:.1f}g/day "
        f"({protein_pct:.0f}% of {insights['daily_protein_g']:.0f}g goal)",
        f"  Best day:  {insights['best_protein_day']}",
        f"  Worst day: {insights['worst_protein_day']}",
    ]

    if insights["missed_days"] > 0:
        lines += [
            "",
            f"⚠️ You missed logging on {insights['missed_days']} day(s) "
            "— totals may be understated.",
        ]

    if top_foods:
        lines += ["", "*Your go-to foods this week*"]
        for food in top_foods:
            lines.append(
                f"  • {food['name']} — {food['times_logged']}x "
                f"(~{food['avg_grams']:.0f}g avg)"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram job
# ---------------------------------------------------------------------------

async def send_weekly_insight(context) -> None:
    """
    Scheduled job — sends weekly report to all users.
    Register in bot.py:

        from jobs.weekly_insight import send_weekly_insight
        import datetime

        app.job_queue.run_repeating(
            send_weekly_insight,
            interval=datetime.timedelta(weeks=1),
            first=datetime.time(hour=18, minute=0),
        )
    """
    user_ids = db.get_all_user_ids()
    logger.info("Weekly insight job running for %d users", len(user_ids))

    for user_id in user_ids:
        try:
            message = format_week_insights(user_id)
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="Markdown",
            )
            logger.info("Sent weekly insight to user %d", user_id)
        except Exception as exc:
            logger.error("Failed to send weekly insight to user %d: %s", user_id, exc)